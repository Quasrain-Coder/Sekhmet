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
