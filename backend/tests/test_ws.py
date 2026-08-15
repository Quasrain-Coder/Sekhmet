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


def test_broadcasts_carry_min_raise_and_activity_flags():
    """hand_start/game_state_update must include min_raise and per-player
    activity flags — the frontend renders the action slider floor and the
    folded styling from these fields."""
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot",
                      "buyin": 200, "is_human": False})
        ws.send_json({"type": "start_hand"})
        saw_hand_start = saw_update = False
        for _ in range(30):
            msg = ws.receive_json()
            if msg["type"] == "hand_start":
                saw_hand_start = True
                assert msg["min_raise"] > 0
                for p in msg["players"]:
                    assert p["is_active"] is True
                    assert p["is_all_in"] is False
            elif msg["type"] in ("game_state_update", "hand_result"):
                saw_update = True
                assert msg["min_raise"] > 0
                break
        assert saw_hand_start, "never received hand_start"
        assert saw_update, "never received game_state_update"
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
def test_non_owner_cannot_add_bots():
    """Only the table owner may add bot seats — strangers can't spam a room."""
    client = TestClient(app)
    resp = client.post("/api/game/tables")
    tid = resp.json()["table_id"]

    with client.websocket_connect(f"/ws/{tid}") as owner_ws, \
         client.websocket_connect(f"/ws/{tid}") as guest_ws:
        owner_ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Owner", "buyin": 200})
        guest_ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Guest", "buyin": 200})
        _drain(owner_ws, 1)
        _drain(guest_ws, 2)

        guest_ws.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot",
                            "is_human": False})
        err = guest_ws.receive_json()
        assert err["type"] == "error"
        assert "owner" in err["message"]

        # the owner can
        owner_ws.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot",
                            "is_human": False})
        for _ in range(10):
            m = owner_ws.receive_json()
            if m["type"] == "table_state" and len(m["seats"]) == 3:
                break
        else:
            raise AssertionError("owner's bot add never broadcast")


def test_rest_create_returns_owner_token_and_ws_claims_it():
    """Creator's owner_token makes their seat the owner even if they sit late."""
    client = TestClient(app)
    tid, token = None, None
    resp = client.post("/api/game/tables")
    tid = resp.json()["table_id"]
    token = resp.json()["owner_token"]
    assert token and len(token) == 32

    with client.websocket_connect(f"/ws/{tid}") as stranger, \
         client.websocket_connect(f"/ws/{tid}") as creator:
        stranger.send_json({"type": "sit_down", "seat_idx": 0, "name": "Stranger", "buyin": 200})
        _drain(stranger, 2)
        creator.send_json({"type": "sit_down", "seat_idx": 5, "name": "Creator",
                           "buyin": 200, "owner_token": token})
        _drain(creator, 2)
        # token holder owns the room despite the higher seat index
        creator.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot",
                           "is_human": False})
        msg = creator.receive_json()
        assert msg["type"] == "table_state"
        owner = [s for s in msg["seats"] if s["is_owner"]]
        assert owner[0]["seat_idx"] == 5


async def test_table_info_exposes_live_public_state():
    """REST detail (join panel) carries the public in-hand state: community
    cards, pot, position tags and per-seat in-hand flags."""
    from sekhmet.api import table_manager as tm
    from sekhmet.game_engine import GamePhase

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)

    # Between hands: empty board, no pot, no one to act (the dealer button
    # is already assigned)
    info = tm.table_info(await tm.get_table(tid))
    assert info["community_cards"] == []
    assert info["pot"] == 0
    assert info["current_player_idx"] is None
    assert info["dealer_idx"] == 0

    # Check/call down to the flop (drives bots directly — the engine's
    # after_action cascade handles their turns too)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    gs = session.game_state
    while gs.phase == GamePhase.PREFLOP:
        cur = gs.current_player_idx
        p = gs.player(cur)
        await tm.handle_player_action(tid, cur,
                                      "CALL" if gs.current_bet > p.current_bet else "CHECK")
        session = await tm.get_table(tid)
        gs = session.game_state

    info = tm.table_info(session)
    assert info["phase"] == "FLOP"
    assert len(info["community_cards"]) == 3
    assert info["pot"] == 20
    assert info["dealer_idx"] is not None
    assert info["sb_seat"] is not None and info["bb_seat"] is not None
    seat0 = next(s for s in info["seats"] if s["seat_idx"] == 0)
    assert seat0["is_active"] is True
    assert seat0["is_all_in"] is False
    assert seat0["current_bet"] == 0  # fresh street
