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
        # Each human sit_down also gets a private reclaim_token first.
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200})

        # ws1: token + 2 table_state, ws2: token + 1 table_state
        tk1 = ws1.receive_json()
        ts1a = ws1.receive_json()
        ts1b = ws1.receive_json()
        tk2 = ws2.receive_json()
        ts2 = ws2.receive_json()
        assert tk1["type"] == "reclaim_token"
        assert tk1["seat"] == 0
        assert ts1a["type"] == "table_state"
        assert ts1b["type"] == "table_state"
        assert tk2["type"] == "reclaim_token"
        assert tk2["seat"] == 1
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


def test_bot_sitdown_does_not_hijack_human_seat():
    """Auto-added bot (same connection) must not steal the connection's seat.

    Regression: the frontend seats the human and a bot over one WebSocket.
    ``my_seat`` was overwritten by the bot's sit_down, so every
    player_action executed as the bot and failed with NotYourTurnError —
    the game looked frozen when the human clicked anything.
    """
    import random
    random.seed(7)  # deterministic deal: bot calls preflop, human gets a turn

    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]

    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200,
                      "is_human": False})
        ws.send_json({"type": "start_hand"})

        saw_error = None
        acted = False
        for _ in range(30):
            msg = ws.receive_json()
            if msg["type"] == "error":
                saw_error = msg["message"]
                break
            if msg["type"] == "hand_result":
                break
            if msg["type"] == "game_state_update" and msg.get("current_player_idx") == 0:
                if not acted:
                    ws.send_json({"type": "player_action", "action": "FOLD"})
                    acted = True

        assert saw_error is None, f"server error: {saw_error}"
        assert acted, "human never got a turn"


async def test_reclaim_rearms_action_timer():
    """Reclaiming mid-hand restarts the action countdown — the auto-fold
    must not fire on the stale timer from before the disconnect."""
    import random
    from sekhmet.api import table_manager as tm

    random.seed(7)  # deterministic deal: bot calls preflop, hero gets a turn
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]

    with client.websocket_connect(f"/ws/{tid}") as ws1:
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        token = None
        for _ in range(10):
            m = ws1.receive_json()
            if m["type"] == "reclaim_token":
                token = m["token"]
            if m["type"] == "table_state":
                break
        assert token is not None
        ws1.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot",
                       "buyin": 200, "is_human": False})
        ws1.send_json({"type": "start_hand"})
        for _ in range(30):
            m = ws1.receive_json()
            if m["type"] == "game_state_update" and m["current_player_idx"] == 0:
                break

    session = await tm.get_table(tid)
    old_timer = session.action_timer
    assert old_timer is not None  # hero's turn → timer armed

    # TestClient never pumps the server-side close frame, so simulate what
    # the server does when it notices the dead socket.
    await tm.handle_disconnect(tid, 0)
    session = await tm.get_table(tid)
    assert 0 in session.disconnected

    with client.websocket_connect(f"/ws/{tid}") as ws2:
        ws2.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero",
                       "reclaim_token": token})
        for _ in range(10):
            m = ws2.receive_json()
            if m["type"] == "reclaim_token":
                break

    session = await tm.get_table(tid)
    assert session.action_timer is not None
    assert session.action_timer is not old_timer  # re-armed, not the stale one
    session.action_timer.cancel()
