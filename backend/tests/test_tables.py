"""Tests for table creation with room configuration."""

import pytest
from fastapi.testclient import TestClient

from sekhmet.main import app
from sekhmet.api import table_manager as tm
from sekhmet.api.table_manager import TableConfig
from sekhmet.game_engine.deck import Deck
from sekhmet.game_engine.action_processor import deal_new_hand
from sekhmet.game_engine.game_state import Player


async def test_create_table_with_custom_blinds():
    cfg = TableConfig(small_blind=10, big_blind=20, default_buyin=2000, max_seats=6)
    tid = await tm.create_table(cfg)
    session = await tm.get_table(tid)
    assert session is not None
    assert session.config.big_blind == 20
    assert session.n_seats == 6
    assert session.game_state.big_blind == 20


async def test_custom_blinds_reach_dealt_hand():
    cfg = TableConfig(small_blind=10, big_blind=20, default_buyin=2000)
    tid = await tm.create_table(cfg)
    await tm.sit_down(tid, 0, "A", buyin=2000)
    await tm.sit_down(tid, 1, "B", buyin=2000)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    bets = {p.seat_idx: p.total_bet for p in session.game_state.players}
    assert sorted(bets.values()) == [10, 20]  # custom blinds posted


async def test_default_buyin_from_config():
    cfg = TableConfig(default_buyin=500)
    tid = await tm.create_table(cfg)
    await tm.sit_down(tid, 0, "A")  # no explicit buyin
    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.player(0).stack == 500


def test_config_validation():
    with pytest.raises(ValueError, match="small_blind"):
        TableConfig(small_blind=10, big_blind=10)   # sb must be < bb
    with pytest.raises(ValueError, match="max_seats"):
        TableConfig(max_seats=10)
    with pytest.raises(ValueError, match="default_buyin"):
        TableConfig(big_blind=50, small_blind=25, default_buyin=200)  # < 20bb
    with pytest.raises(ValueError, match="Unknown"):
        TableConfig.from_dict({"blinds": 10})


def test_rest_create_table_with_config():
    client = TestClient(app)
    resp = client.post("/api/game/tables",
                       json={"small_blind": 10, "big_blind": 20, "default_buyin": 2000})
    assert resp.status_code == 200
    detail = client.get(f"/api/game/tables/{resp.json()['table_id']}")
    assert detail.json()["config"]["big_blind"] == 20


def test_rest_create_table_invalid_config_400():
    client = TestClient(app)
    resp = client.post("/api/game/tables", json={"small_blind": 20, "big_blind": 10})
    assert resp.status_code == 400


def test_rest_create_table_no_body_still_works():
    client = TestClient(app)
    resp = client.post("/api/game/tables")
    assert resp.status_code == 200


from sekhmet.game_engine.game_state import GamePhase


async def _table_with_bot(level: int) -> str:
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False, bot_level=level)
    return tid


async def test_bot_level_drives_registry(monkeypatch):
    created: list[str] = []
    monkeypatch.setattr(
        "sekhmet.ai_engine.bot_registry.create",
        lambda name: created.append(name) or __import__(
            "sekhmet.ai_engine.rule_bot", fromlist=["RuleBot"]
        ).RuleBot(level=int(name[-1])),
    )
    tid = await _table_with_bot(3)
    await tm.start_hand(tid)
    await tm.auto_bot_actions(tid)
    assert "rule_lv3" in created


async def test_bot_level_default_is_2():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "B", is_human=False)  # no level given
    session = await tm.get_table(tid)
    assert session is not None
    assert session.bot_levels[0] == 2


async def test_bot_level_out_of_range_rejected():
    tid = await tm.create_table()
    from sekhmet.game_engine import GameError
    with pytest.raises(GameError, match="bot_level"):
        await tm.sit_down(tid, 0, "B", is_human=False, bot_level=9)


async def test_table_info_shape():
    tid = await _table_with_bot(1)
    session = await tm.get_table(tid)
    info = tm.table_info(session)
    assert info["config"]["big_blind"] == 10
    seats = {s["seat_idx"]: s for s in info["seats"]}
    assert seats[0]["is_human"] is True and seats[0]["bot_level"] is None
    assert seats[1]["is_human"] is False and seats[1]["bot_level"] == 1
    assert seats[1]["stack"] == 200


def test_ws_kick_bot_and_reject_kicking_human():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero"})
        ws1.receive_json()                      # ws1's join broadcast
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Friend"})
        ws2.receive_json()                      # ws2's join broadcast
        ws1.receive_json()                      # ws2's join, echoed to ws1

        # ws1 adds a bot, then kicks it
        ws1.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot",
                       "is_human": False, "bot_level": 3})
        ws1.receive_json(); ws2.receive_json()  # bot join broadcast
        ws1.send_json({"type": "stand_up", "seat_idx": 2})
        msg = ws1.receive_json()
        assert msg["type"] == "table_state"
        assert all(s["seat_idx"] != 2 for s in msg["seats"])
        ws2.receive_json()                      # drain kick broadcast on ws2

        # ws2 tries to kick the human at seat 0 — rejected
        ws2.send_json({"type": "stand_up", "seat_idx": 0})
        msg = ws2.receive_json()
        assert msg["type"] == "error"


def test_failed_sit_down_does_not_hijack_victim_broadcasts():
    """A rejected sit_down (seat taken) must not overwrite the real
    occupant's clients entry — the victim must keep receiving broadcasts."""
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        # ws1 takes seat 0
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero"})
        ws1.receive_json()                      # ws1's join broadcast

        # ws2 tries the same seat — rejected, must not touch clients
        ws2.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hijacker"})
        msg = ws2.receive_json()
        assert msg["type"] == "error"

        # ws1 seats a bot at seat 1 → table_state broadcast must still
        # reach ws1 (pre-fix, clients[0] was hijacked by ws2's socket).
        ws1.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot",
                       "is_human": False})
        msg = ws1.receive_json()
        assert msg["type"] == "table_state"
        assert any(s["seat_idx"] == 1 for s in msg["seats"])


async def test_sit_down_rejected_mid_hand():
    """Joining mid-hand would corrupt the round-close logic — reject it."""
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "A", buyin=200)
    await tm.sit_down(tid, 1, "B", buyin=200)
    await tm.start_hand(tid)
    with pytest.raises(GameError, match="mid-hand"):
        await tm.sit_down(tid, 2, "Late", buyin=200)
