"""Tests for the models/ persistence layer."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sekhmet.api import table_manager as tm
from sekhmet.models import db, records, recorder


async def test_record_hand_persists():
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
        rows = (await s.execute(select(records.HandRecord))).scalars().all()
    assert len(rows) == 1
    r = rows[0]
    assert r.table_id == "abc12345"
    assert json.loads(r.board) == ["A♠", "K♥", "10♦", "2♣", "7♠"]
    assert json.loads(r.awards)[0]["seat_idx"] == 0


async def test_upsert_player_stats_accumulates_humans_only():
    deltas = [
        {"name": "Hero", "is_human": True, "won": True, "delta": 15},
        {"name": "Bot L2", "is_human": False, "won": False, "delta": -15},
    ]
    await recorder.upsert_player_stats(deltas)
    await recorder.upsert_player_stats([{"name": "Hero", "is_human": True, "won": False, "delta": -10}])
    async with db.SessionLocal() as s:
        rows = (await s.execute(select(records.PlayerStatsRecord))).scalars().all()
    assert len(rows) == 1  # bot 不入库
    hero = rows[0]
    assert hero.hands == 2 and hero.wins == 1 and hero.net_chips == 5


async def test_recording_failure_does_not_raise():
    """落库异常只记日志，不向上抛。"""
    # 指向父目录不存在的路径 —— 连接必然失败。dispose() 只能暂时关闭连接，
    # 连接池会惰性重建自愈，模拟不了真实故障，所以直接配置一个坏 URL。
    db.configure("sqlite+aiosqlite:///definitely_missing_dir_xyz/t.db")
    await recorder.record_hand("t", [], "[]", "[]", "[]")  # 不应抛出


async def test_hand_recorded_after_showdown():
    """真实打一手牌（fold-out）→ 落库一条 HandRecord，战绩累计。"""
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    sb = session.game_state.current_player_idx
    await tm.handle_player_action(tid, sb, "FOLD")
    await asyncio.sleep(0.05)  # fire-and-forget 落库

    async with db.SessionLocal() as s:
        hands = (await s.execute(select(records.HandRecord))).scalars().all()
        stats = (await s.execute(select(records.PlayerStatsRecord))).scalars().all()
    assert len(hands) == 1
    assert hands[0].table_id == tid
    assert len(stats) == 1 and stats[0].name == "Hero"  # bot 不入库
    assert stats[0].hands == 1


@pytest.fixture
def mem_db_sync_client():
    """TestClient over the real app — lifespan runs init_db on the isolated DB."""
    from sekhmet.main import app
    with TestClient(app) as client:
        yield client


def test_history_endpoints(mem_db_sync_client):
    client = mem_db_sync_client

    async def _seed():
        try:
            await recorder.record_hand(
                table_id="tblAAAAAA",
                players_meta=[
                    {"seat_idx": 0, "name": "Hero", "is_human": True,
                     "stack_before": 200, "stack_after": 215},
                ],
                board=["A♠", "K♥", "10♦", "2♣", "7♠"],
                actions=[{"seat": 0, "action": "CALL", "amount": 5}],
                awards=[{"seat_idx": 0, "amount": 15, "hand": "High Card, Ace"}],
            )
            await recorder.record_hand(
                table_id="tblBBBBBB",
                players_meta=[
                    {"seat_idx": 1, "name": "Bot", "is_human": False,
                     "stack_before": 200, "stack_after": 185},
                ],
                board=[],
                actions=[{"seat": 1, "action": "FOLD", "amount": 0}],
                awards=[{"seat_idx": 0, "amount": 15, "hand": "Won without showdown"}],
            )
            await recorder.upsert_player_stats([
                {"name": "Hero", "is_human": True, "won": True, "delta": 15},
                {"name": "Villain", "is_human": True, "won": False, "delta": -5},
            ])
        finally:
            await db.engine.dispose()  # 释放种子循环的池连接，客户端线程自行重建

    asyncio.run(_seed())

    # 对局历史：倒序（新在前），JSON 字段已解析
    r = client.get("/api/history/hands")
    assert r.status_code == 200
    hands = r.json()["hands"]
    assert [h["table_id"] for h in hands] == ["tblBBBBBB", "tblAAAAAA"]
    assert hands[0]["players"] == [
        {"seat_idx": 1, "name": "Bot", "is_human": False,
         "stack_before": 200, "stack_after": 185},
    ]
    assert hands[0]["board"] == []
    assert hands[0]["awards"][0]["hand"] == "Won without showdown"
    assert hands[1]["board"] == ["A♠", "K♥", "10♦", "2♣", "7♠"]
    assert isinstance(hands[0]["created_at"], str)

    # table_id 过滤与 limit
    only_a = client.get("/api/history/hands", params={"table_id": "tblAAAAAA"}).json()
    assert [h["table_id"] for h in only_a["hands"]] == ["tblAAAAAA"]
    one = client.get("/api/history/hands", params={"limit": 1}).json()
    assert len(one["hands"]) == 1

    # 玩家战绩：net_chips 降序
    players = client.get("/api/history/players").json()["players"]
    assert [p["name"] for p in players] == ["Hero", "Villain"]
    assert players[0]["net_chips"] == 15 and players[0]["hands"] == 1
    assert players[1]["net_chips"] == -5
    assert isinstance(players[0]["updated_at"], str)
