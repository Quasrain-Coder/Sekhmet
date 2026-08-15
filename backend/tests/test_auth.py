"""Tests for account registration/login and per-account stat recording."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sekhmet.main import app
from sekhmet.api import auth, table_manager as tm
from sekhmet.models import db, records


@pytest.fixture
def client():
    return TestClient(app)


def test_register_login_me_roundtrip(client):
    resp = client.post("/api/auth/register", json={
        "username": "alice", "password": "secret123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "alice"
    assert data["token"]

    # fresh account: zero stats
    me = client.get("/api/auth/me", params={"token": data["token"]})
    assert me.status_code == 200
    assert me.json() == {
        "username": "alice",
        "stats": {"hands": 0, "wins": 0, "net_chips": 0},
    }

    # login again with the password → a new valid token
    resp2 = client.post("/api/auth/login", json={
        "username": "alice", "password": "secret123",
    })
    assert resp2.status_code == 200
    assert client.get("/api/auth/me", params={"token": resp2.json()["token"]}).status_code == 200

    # wrong password rejected
    assert client.post("/api/auth/login", json={
        "username": "alice", "password": "wrong-password",
    }).status_code == 401

    # duplicate username rejected
    assert client.post("/api/auth/register", json={
        "username": "alice", "password": "whatever1",
    }).status_code == 409

    # validation
    assert client.post("/api/auth/register", json={
        "username": "x", "password": "secret123",
    }).status_code == 400
    assert client.post("/api/auth/register", json={
        "username": "bob", "password": "short",
    }).status_code == 400

    # unknown token
    assert client.get("/api/auth/me", params={"token": "nope"}).status_code == 401


def test_resolve_token_maps_valid_tokens_only(client):
    resp = client.post("/api/auth/register", json={
        "username": "carol", "password": "secret123",
    })
    token = resp.json()["token"]
    assert auth.resolve_token(token) is not None
    assert auth.resolve_token("bogus") is None
    assert auth.resolve_token(None) is None


def test_passwords_are_hashed_not_plaintext(client):
    client.post("/api/auth/register", json={
        "username": "dave", "password": "secret123",
    })

    async def check():
        async with db.SessionLocal() as s:
            u = (await s.execute(
                select(records.UserRecord).where(records.UserRecord.username == "dave")
            )).scalar_one()
        assert u.password_hash != "secret123"
        assert u.password_hash == auth.hash_password("secret123", u.salt)

    asyncio.run(check())


async def test_only_logged_in_players_feed_the_profile():
    """一局里同时有登录玩家和游客：只有登录者的战绩入 user_stats。"""
    async with db.SessionLocal() as s:
        s.add(records.UserRecord(username="pro", password_hash="h", salt="s"))
        await s.commit()
        uid = (await s.execute(
            select(records.UserRecord.id).where(records.UserRecord.username == "pro")
        )).scalar()

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Pro", buyin=200, user_id=uid)      # logged in
    await tm.sit_down(tid, 1, "Guest", buyin=200)                  # guest
    await tm.sit_down(tid, 2, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)

    # fold everyone but the guest (fold-out → guest wins the blinds)
    session = await tm.get_table(tid)
    while session.game_state.phase not in (
        tm.GamePhase.WAITING, tm.GamePhase.SHOWDOWN,
    ):
        cur = session.game_state.current_player_idx
        if cur is None:
            await asyncio.sleep(0.9)
            session = await tm.get_table(tid)
            continue
        await tm.handle_player_action(tid, cur, "FOLD")
        session = await tm.get_table(tid)

    # fire-and-forget 落库 — 轮询等待而不是固定 sleep：全量跑时事件
    # 循环里堆着其它测试的挂起任务，单次 50ms 经常不够（偶发 flaky）。
    async with db.SessionLocal() as s:
        rows = []
        for _ in range(100):  # 最多等 2s
            rows = (await s.execute(select(records.UserStatsRecord))).scalars().all()
            if rows:
                break
            await asyncio.sleep(0.02)
        legacy = (await s.execute(select(records.PlayerStatsRecord))).scalars().all()
    # only the logged-in player is recorded — the guest is not counted
    assert len(rows) == 1
    assert rows[0].user_id == uid and rows[0].hands == 1
    assert legacy == []


def test_ws_token_binds_seat_to_account(client):
    resp = client.post("/api/auth/register", json={
        "username": "eve", "password": "secret123",
    })
    token = resp.json()["token"]
    tid = client.post("/api/game/tables").json()["table_id"]

    with client.websocket_connect(f"/ws/{tid}?token={token}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Eve", "buyin": 200})
        for _ in range(10):
            m = ws.receive_json()
            if m["type"] == "reclaim_token":
                break

    async def check():
        session = await tm.get_table(tid)
        assert session.user_ids.get(0) is not None

    asyncio.run(check())
