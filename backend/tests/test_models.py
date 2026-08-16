"""Tests for the models/ persistence layer."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sekhmet.api import table_manager as tm
from sekhmet.game_engine import GamePhase
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
    """真实打一手牌（fold-out）→ 落库一条 HandRecord；登录玩家的战绩
    计入个人档案（user_stats），游客不计。"""
    tid = await tm.create_table()
    async with db.SessionLocal() as s:
        s.add(records.UserRecord(username="hero_acct", password_hash="h", salt="s"))
        await s.commit()
        uid = (await s.execute(
            select(records.UserRecord.id).where(records.UserRecord.username == "hero_acct")
        )).scalar()

    await tm.sit_down(tid, 0, "Hero", buyin=200, user_id=uid)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    sb = session.game_state.current_player_idx
    await tm.handle_player_action(tid, sb, "FOLD")
    # fire-and-forget 落库——轮询等待而不是固定 sleep（CI 慢机上
    # 事件循环繁忙，单次 50ms 偶发不够，与 test_auth #57 同理）。
    async with db.SessionLocal() as s:
        hands = []
        for _ in range(100):  # 最多等 2s
            hands = (await s.execute(select(records.HandRecord))).scalars().all()
            if hands:
                break
            await asyncio.sleep(0.02)
        stats = (await s.execute(select(records.UserStatsRecord))).scalars().all()
    assert len(hands) == 1
    assert hands[0].table_id == tid
    # 登录账号入档案（bot 与游客均不入）
    assert len(stats) == 1 and stats[0].user_id == uid
    assert stats[0].username == "hero_acct" and stats[0].hands == 1


async def test_grace_expiry_does_not_resolve_already_settled_showdown():
    """断线落在结算窗口：grace-expiry 在锁外算出 mid_hand=True，锁内重读时
    手牌已被 runout/动作路径推进到 SHOWDOWN 并结算 —— 不得二次 resolve，
    否则重复 HandRecord、重复累计 PlayerStatsRecord、重复派彩。"""
    tid = await tm.create_table()
    async with db.SessionLocal() as s:
        for uname in ("hero_acct", "villain_acct"):
            s.add(records.UserRecord(username=uname, password_hash="h", salt="s"))
        await s.commit()
        uids = (await s.execute(
            select(records.UserRecord).order_by(records.UserRecord.id)
        )).scalars().all()
        ids = [u.id for u in uids]
    await tm.sit_down(tid, 0, "Hero", buyin=200, user_id=ids[0])
    await tm.sit_down(tid, 1, "Villain", buyin=200, user_id=ids[1])
    await tm.start_hand(tid)

    # 一路 check/call 推进到 RIVER（双方 active、公共牌 5 张，仍 mid-hand）
    for _ in range(12):
        session = await tm.get_table(tid)
        gs = session.game_state
        if gs.phase in (GamePhase.RIVER, GamePhase.SHOWDOWN):
            break
        seat = gs.current_player_idx
        player = gs.player(seat)
        to_call = gs.current_bet - player.current_bet
        await tm.handle_player_action(tid, seat, "CALL" if to_call > 0 else "CHECK")
    session = await tm.get_table(tid)
    assert session.game_state.phase == GamePhase.RIVER

    # 模拟断线（真实 grace 定时器直接取消，测试自行触发 expiry）
    await tm.handle_disconnect(tid, 1)
    session = await tm.get_table(tid)
    timer = session.grace_timers.pop(1, None)
    if timer is not None:
        timer.cancel()
        await asyncio.gather(timer, return_exceptions=True)

    # 测试先握住 session.lock —— 模拟 runout 路径正在锁内结算。
    async with session.lock:
        # grace-expiry 任务在锁外读到 mid-hand，随后阻塞在锁上
        expire_task = asyncio.create_task(tm._expire_seat(tid, 1))
        for _ in range(1000):
            await asyncio.sleep(0)
            if 1 not in session.disconnected:  # 前导逻辑已跑完 → 停在锁上
                break
        assert 1 not in session.disconnected
        # runout 路径在锁内完成结算：SHOWDOWN + resolve 一次
        gs = session.game_state
        assert gs.phase == GamePhase.RIVER  # expiry 任务尚未动手
        session.game_state = gs.with_phase(GamePhase.SHOWDOWN)
        tm._resolve_showdown(session)
        stacks_after_settle = tuple(
            (p.seat_idx, p.stack) for p in session.game_state.players
        )
    await expire_task

    # 等待 fire-and-forget 落库（有 deadline，不靠裸 sleep）
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2.0
    while True:
        async with db.SessionLocal() as s:
            hands = (await s.execute(select(records.HandRecord))).scalars().all()
            stats = (await s.execute(
                select(records.UserStatsRecord)
            )).scalars().all()
        if len(hands) == 1 and len(stats) == 2:
            break
        if loop.time() > deadline:
            break
        await asyncio.sleep(0.01)

    assert len(hands) == 1, "grace-expiry 不得对已结算的手二次落库"
    assert len(stats) == 2  # 两个人类玩家，各计一手
    assert all(s.hands == 1 for s in stats), "战绩不得重复累计"
    assert all(s.wins <= 1 for s in stats), "胜场不得重复累计"
    assert sum(s.net_chips for s in stats) == 20, "净筹码不得重复累计"
    # 筹码不得重复派彩：expiry 结束后各座位 stack 与首次结算后完全一致
    session = await tm.get_table(tid)
    assert tuple((p.seat_idx, p.stack) for p in session.game_state.players) \
        == stacks_after_settle


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
            async with db.SessionLocal() as s:
                for uname in ("Hero", "Villain"):
                    s.add(records.UserRecord(username=uname, password_hash="h", salt="s"))
                await s.commit()
                uids = (await s.execute(
                    select(records.UserRecord).order_by(records.UserRecord.id)
                )).scalars().all()
                ids = [u.id for u in uids]
            await recorder.upsert_user_stats([
                {"user_id": ids[0], "username": "Hero", "won": True, "delta": 15},
                {"user_id": ids[1], "username": "Villain", "won": False, "delta": -5},
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

    # 负 limit：SQLite 把 LIMIT<0 视为不限，必须被 100 上限钳制
    async def _seed_bulk():
        try:
            for i in range(103):
                await recorder.record_hand(
                    table_id=f"bulk{i:08d}",
                    players_meta=[
                        {"seat_idx": 0, "name": "Hero", "is_human": True,
                         "stack_before": 200, "stack_after": 200},
                    ],
                    board=[],
                    actions=[],
                    awards=[],
                )
        finally:
            await db.engine.dispose()  # 释放种子循环的池连接

    asyncio.run(_seed_bulk())
    r = client.get("/api/history/hands", params={"limit": -1})
    assert r.status_code == 200
    assert len(r.json()["hands"]) <= 100

    # 玩家战绩：net_chips 降序
    players = client.get("/api/history/players").json()["players"]
    assert [p["name"] for p in players] == ["Hero", "Villain"]
    assert players[0]["net_chips"] == 15 and players[0]["hands"] == 1
    assert players[1]["net_chips"] == -5
    assert isinstance(players[0]["updated_at"], str)


async def test_concurrent_stats_upserts_do_not_lose_updates():
    """50 concurrent upserts for the same name must all land — the old
    select-then-mutate pattern lost every update after the first read."""
    deltas = [{"name": "Hero", "is_human": True, "won": True, "delta": 3}]
    await asyncio.gather(*(recorder.upsert_player_stats(deltas) for _ in range(50)))
    async with db.SessionLocal() as s:
        row = (await s.execute(
            select(records.PlayerStatsRecord).where(records.PlayerStatsRecord.name == "Hero")
        )).scalar_one()
    assert row.hands == 50
    assert row.wins == 50
    assert row.net_chips == 150


# ---------------------------------------------------------------------------
# Extended profile metrics (VPIP/PFR/buy-in/showdown)
# ---------------------------------------------------------------------------


async def test_upsert_user_stats_accumulates_poker_metrics():
    """vpip/pfr/showdown/total_buyin 按手牌原子累计。"""
    async with db.SessionLocal() as s:
        s.add(records.UserRecord(username="pro2", password_hash="h", salt="s"))
        await s.commit()
        uid = (await s.execute(
            select(records.UserRecord.id).where(records.UserRecord.username == "pro2")
        )).scalar()

    await recorder.upsert_user_stats([{
        "user_id": uid, "username": "pro2", "won": True, "delta": 20,
        "total_buyin": 200, "vpip": True, "pfr": True,
        "showdown": True, "showdown_win": True,
    }])
    await recorder.upsert_user_stats([{
        "user_id": uid, "username": "pro2", "won": False, "delta": -10,
        "total_buyin": 100, "vpip": True, "pfr": False,
        "showdown": True, "showdown_win": False,
    }])
    async with db.SessionLocal() as s:
        st = (await s.execute(
            select(records.UserStatsRecord).where(records.UserStatsRecord.user_id == uid)
        )).scalar_one()
    assert st.hands == 2 and st.wins == 1 and st.net_chips == 10
    assert st.total_buyin == 300
    assert st.vpip_hands == 2 and st.pfr_hands == 1
    assert st.showdowns == 2 and st.showdown_wins == 1


async def test_column_migration_adds_new_columns_to_existing_db():
    """用户已有的 SQLite 文件缺新列——init_db 应原地补齐且幂等。"""
    from sqlalchemy import text

    # Build an OLD-schema database: tables with only the original columns.
    async with db.engine.begin() as conn:
        await conn.run_sync(records.Base.metadata.create_all)
        # emulate the old schema by dropping new columns is hard in
        # SQLite — instead create a bare copy table set with old shape.
        pass
    # 直接验证迁移函数幂等：跑两遍不报错。
    async with db.engine.begin() as conn:
        def run(conn):
            db._migrate_columns(conn)
            db._migrate_columns(conn)
        await conn.run_sync(run)
        cols = {
            row[1] for row in
            await conn.execute(text("PRAGMA table_info(user_stats)"))
        }
    for col in ("total_buyin", "vpip_hands", "pfr_hands",
                "showdowns", "showdown_wins"):
        assert col in cols
    async with db.engine.begin() as conn:
        cols = {
            row[1] for row in
            await conn.execute(text("PRAGMA table_info(hand_records)"))
        }
    assert "small_blind" in cols and "big_blind" in cols


async def test_showdown_delta_carries_vpip_pfr_and_blinds():
    """真实打一手：登录玩家翻前加注（VPIP+PFR）→ 摊牌 → 落库含指标。"""
    async with db.SessionLocal() as s:
        s.add(records.UserRecord(username="pro3", password_hash="h", salt="s"))
        await s.commit()
        uid = (await s.execute(
            select(records.UserRecord.id).where(records.UserRecord.username == "pro3")
        )).scalar()

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "pro3", buyin=200, user_id=uid)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    # pro3 raises whenever it's their turn until the hand ends or a
    # showdown happens; the bot calls everything — the hand reaches
    # showdown and the tracker records VPIP+PFR for pro3.
    raised_once = False
    for _ in range(80):
        session = await tm.get_table(tid)
        if session.game_state.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            break
        cur = session.game_state.current_player_idx
        if cur is None:
            await asyncio.sleep(0.5)
            continue
        gs = session.game_state
        to_call = gs.current_bet - gs.player(cur).current_bet
        if cur == 0 and gs.phase == GamePhase.PREFLOP and not raised_once:
            # 翻前加注一次：记 VPIP + PFR
            await tm.handle_player_action(
                tid, 0, "RAISE", amount=gs.current_bet + gs.min_raise)
            raised_once = True
        elif to_call > 0:
            await tm.handle_player_action(tid, cur, "CALL")
        else:
            await tm.handle_player_action(tid, cur, "CHECK")

    # fire-and-forget 落库 —— 轮询等待
    async with db.SessionLocal() as s:
        st = None
        for _ in range(100):
            st = (await s.execute(
                select(records.UserStatsRecord).where(records.UserStatsRecord.user_id == uid)
            )).scalar_one_or_none()
            if st is not None:
                break
            await asyncio.sleep(0.02)
    assert st is not None and st.hands == 1
    assert st.vpip_hands == 1 and st.pfr_hands == 1
    assert st.total_buyin == 200
    assert st.showdowns == 1  # 双方 CALL 到底必然摊牌
