"""Integration tests for WebSocket game flow."""

import pytest
from fastapi.testclient import TestClient

from sekhmet.main import app


@pytest.fixture
def rest_client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


def test_health(rest_client):
    resp = rest_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_table(rest_client):
    resp = rest_client.post("/api/game/tables")
    assert resp.status_code == 200
    data = resp.json()
    assert "table_id" in data
    assert len(data["table_id"]) == 8


def test_get_table_not_found(rest_client):
    resp = rest_client.get("/api/game/tables/nonexistent")
    assert resp.status_code == 404


def test_list_tables(rest_client):
    rest_client.post("/api/game/tables")
    resp = rest_client.get("/api/game/tables")
    assert resp.status_code == 200
    data = resp.json()
    assert "tables" in data
    assert len(data["tables"]) >= 1


def test_get_table(rest_client):
    resp = rest_client.post("/api/game/tables")
    tid = resp.json()["table_id"]
    resp2 = rest_client.get(f"/api/game/tables/{tid}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["table_id"] == tid
    assert data["phase"] == "WAITING"


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


def test_websocket_sit_down_and_start():
    """Two players connect, sit down, deal a hand."""
    client = TestClient(app)

    resp = client.post("/api/game/tables")
    tid = resp.json()["table_id"]

    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        # Sit down: ws1 first → broadcast to {0: ws1}
        #            ws2 second → broadcast to {0: ws1, 1: ws2}
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200})

        # ws1: 2 table_state, ws2: 1 table_state
        ts1a = ws1.receive_json()
        ts1b = ws1.receive_json()
        ts2 = ws2.receive_json()
        assert ts1a["type"] == "table_state"
        assert ts1b["type"] == "table_state"
        assert ts2["type"] == "table_state"

        # Start hand → broadcast hand_start + private hole_cards
        ws1.send_json({"type": "start_hand"})

        hs1 = ws1.receive_json()
        hs2 = ws2.receive_json()
        assert hs1["type"] == "hand_start"
        assert hs2["type"] == "hand_start"

        hc1 = ws1.receive_json()
        hc2 = ws2.receive_json()
        assert hc1["type"] == "hole_cards"
        assert hc2["type"] == "hole_cards"


def test_websocket_unknown_message_type():
    """Unknown message types get an error."""
    client = TestClient(app)
    resp = client.post("/api/game/tables")
    tid = resp.json()["table_id"]

    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "garbage_message"})
        err = ws.receive_json()
        assert err["type"] == "error"


def test_websocket_bad_json():
    """Malformed JSON gets an error."""
    client = TestClient(app)
    resp = client.post("/api/game/tables")
    tid = resp.json()["table_id"]

    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_text("not json{{{")
        err = ws.receive_json()
        assert err["type"] == "error"


def test_websocket_action_before_sit():
    """Sending player_action before sit_down gives error."""
    client = TestClient(app)
    resp = client.post("/api/game/tables")
    tid = resp.json()["table_id"]

    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "player_action", "action": "FOLD"})
        err = ws.receive_json()
        assert err["type"] == "error"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drain(ws, n: int) -> None:
    for _ in range(n):
        ws.receive_json()
