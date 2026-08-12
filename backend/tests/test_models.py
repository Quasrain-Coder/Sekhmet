"""Tests for the models/ persistence layer."""

import pytest
from sekhmet.models import db, records, recorder


@pytest.fixture
async def mem_db(tmp_path):
    """File-backed SQLite per test (in-memory aiosqlite is per-connection)."""
    db.configure(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await db.init_db()
    yield
    await db.engine.dispose()


async def test_record_hand_persists(mem_db):
    await recorder.record_hand(
        table_id="abc12345",
        players_meta=[
            {"seat_idx": 0, "name": "Hero", "is_human": True, "stack_before": 200, "stack_after": 215},
            {"seat_idx": 1, "name": "Bot L2", "is_human": False, "stack_before": 200, "stack_after": 185},
        ],
        board=["A♠", "K♥", "10♦", "2♣", "7♠"],
        actions=[{"seat": 0, "action": "CALL", "amount": 5}],
        awards=[{"seat_idx": 0, "amount": 15, "hand": "High Card, Ace"}],
    )
    async with db.SessionLocal() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(records.HandRecord))).scalars().all()
    assert len(rows) == 1
    r = rows[0]
    assert r.table_id == "abc12345"
    import json
    assert json.loads(r.board) == ["A♠", "K♥", "10♦", "2♣", "7♠"]
    assert json.loads(r.awards)[0]["seat_idx"] == 0


async def test_upsert_player_stats_accumulates_humans_only(mem_db):
    deltas = [
        {"name": "Hero", "is_human": True, "won": True, "delta": 15},
        {"name": "Bot L2", "is_human": False, "won": False, "delta": -15},
    ]
    await recorder.upsert_player_stats(deltas)
    await recorder.upsert_player_stats([{"name": "Hero", "is_human": True, "won": False, "delta": -10}])
    async with db.SessionLocal() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(records.PlayerStatsRecord))).scalars().all()
    assert len(rows) == 1  # bot 不入库
    hero = rows[0]
    assert hero.hands == 2 and hero.wins == 1 and hero.net_chips == 5


async def test_recording_failure_does_not_raise(mem_db):
    """落库异常只记日志，不向上抛。"""
    await db.engine.dispose()  # 弄坏 engine
    await recorder.record_hand("t", [], "[]", "[]", "[]")  # 不应抛出
