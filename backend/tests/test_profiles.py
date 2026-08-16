"""Tests for the in-game player profile endpoint."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from sekhmet.main import app
from sekhmet.api import table_manager as tm
from sekhmet.models import db, records

client = TestClient(app)


async def _seed_user(username: str) -> int:
    async with db.SessionLocal() as s:
        s.add(records.UserRecord(username=username, password_hash="h", salt="s"))
        await s.commit()
        uid = (await s.execute(
            select(records.UserRecord.id)
            .where(records.UserRecord.username == username)
        )).scalar()
        s.add(records.UserStatsRecord(
            user_id=uid, username=username, hands=5, wins=2, net_chips=120,
        ))
        await s.commit()
        return uid


async def test_seat_profile_logged_in_guest_and_bot():
    uid = await _seed_user("pro")

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Pro", buyin=200, user_id=uid)
    await tm.sit_down(tid, 1, "Guest", buyin=200)
    await tm.sit_down(tid, 2, "Bot", buyin=200, is_human=False, bot_level=4)

    # Logged-in player: table stats + account lifetime stats.
    data = client.get(f"/api/game/tables/{tid}/players/0/profile")
    assert data.status_code == 200
    body = data.json()
    assert body["name"] == "Pro" and body["is_human"] is True
    assert body["stack"] == 200 and body["buyin"] == 200
    assert body["account"]["username"] == "pro"
    assert body["account"]["hands"] == 5
    assert body["account"]["wins"] == 2
    assert body["account"]["net_chips"] == 120
    # New poker-tracking fields present (seeded stats have no buy-in).
    assert body["account"]["total_buyin"] == 0
    assert body["account"]["recent_hands"] == []
    assert body["account"]["by_blinds"] == []
    # Table-local tracking present (buy-in count at least 1).
    assert body["buyin_count"] == 1

    # Guest: table-local stats only, no account block.
    guest = client.get(f"/api/game/tables/{tid}/players/1/profile").json()
    assert guest["name"] == "Guest" and guest["account"] is None

    # Bot: level exposed, no account block.
    bot = client.get(f"/api/game/tables/{tid}/players/2/profile").json()
    assert bot["is_human"] is False and bot["bot_level"] == 4

    # Unknown seat / table → 404.
    assert client.get(f"/api/game/tables/{tid}/players/9/profile").status_code == 404
    assert client.get("/api/game/tables/nope/players/0/profile").status_code == 404


async def test_seat_profile_before_any_hand():
    """A parked seat (sat mid-hand) still has a profile."""
    uid = await _seed_user("early")

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Early", buyin=300, user_id=uid)
    data = client.get(f"/api/game/tables/{tid}/players/0/profile").json()
    assert data["stack"] == 300 and data["buyin"] == 300
    assert data["hands"] == 0 and data["wins"] == 0
    assert data["account"]["username"] == "early"


async def test_seat_profile_poker_metrics_and_history():
    """打了牌的账号：VPIP/PFR/W$SD/最近对局/按盲注分组全部就位。"""
    import json as _json

    async with db.SessionLocal() as s:
        s.add(records.UserRecord(username="grinder", password_hash="h", salt="s"))
        await s.commit()
        uid = (await s.execute(
            select(records.UserRecord.id)
            .where(records.UserRecord.username == "grinder")
        )).scalar()
        s.add(records.UserStatsRecord(
            user_id=uid, username="grinder",
            hands=10, wins=4, net_chips=340,
            total_buyin=800, vpip_hands=6, pfr_hands=3,
            showdowns=5, showdown_wins=3,
        ))
        s.add(records.HandRecord(
            table_id="t123", small_blind=5, big_blind=10,
            players=_json.dumps([
                {"seat_idx": 0, "name": "grinder", "is_human": True,
                 "stack_before": 200, "stack_after": 215},
                {"seat_idx": 1, "name": "Bot", "is_human": False,
                 "stack_before": 200, "stack_after": 185},
            ]),
            board=_json.dumps(["A♠", "K♥", "10♦"]),
            actions=_json.dumps([]),
            awards=_json.dumps([{"seat_idx": 0, "amount": 15, "hand": "High Card, Ace"}]),
        ))
        await s.commit()

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "grinder", buyin=200, user_id=uid)

    body = client.get(f"/api/game/tables/{tid}/players/0/profile").json()
    acct = body["account"]
    assert acct["vpip_rate"] == 0.6      # 6/10
    assert acct["pfr_rate"] == 0.3       # 3/10
    assert acct["wtsd"] == 0.6           # 3/5
    assert acct["total_buyin"] == 800
    assert acct["last_active"] is not None
    assert len(acct["recent_hands"]) == 1
    rh = acct["recent_hands"][0]
    assert rh["won"] is True and rh["net"] == 15
    assert rh["small_blind"] == 5 and rh["big_blind"] == 10
    assert len(acct["by_blinds"]) == 1
    g = acct["by_blinds"][0]
    assert (g["small_blind"], g["big_blind"]) == (5, 10)
    assert g["hands"] == 1 and g["wins"] == 1 and g["net_chips"] == 15
