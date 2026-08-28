"""Tests for the hand-replay endpoint (GET /api/history/hands/{id}/replay)."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sekhmet.models import db, recorder
from sekhmet.models.records import HandRecord

# Heads-up hand: hero raises every street and gets called, bot wins at
# showdown.  Same shape as test_hand_to_scenario's fixture.
HAND = {
    "table_id": "tblRPLAY1",
    "small_blind": 5,
    "big_blind": 10,
    "players_meta": [
        {"seat_idx": 0, "name": "Hero", "is_human": True,
         "stack_before": 200, "stack_after": 170,
         "hole_cards": ["A♠", "K♠"]},
        {"seat_idx": 1, "name": "Bot", "is_human": False,
         "stack_before": 200, "stack_after": 230,
         "hole_cards": ["10♥", "10♦"]},
    ],
    "board": ["10♣", "7♠", "2♥", "4♦", "9♠"],
    "actions": [
        {"seat": 0, "action": "RAISE", "amount": 30},
        {"seat": 1, "action": "CALL", "amount": 0},
        {"seat": 0, "action": "BET", "amount": 25},
        {"seat": 1, "action": "CALL", "amount": 0},
        {"seat": 0, "action": "BET", "amount": 40},
        {"seat": 1, "action": "CALL", "amount": 0},
        {"seat": 0, "action": "BET", "amount": 60},
        {"seat": 1, "action": "CALL", "amount": 0},
    ],
    "awards": [{"seat_idx": 1, "amount": 230, "hand": "Three of a Kind"}],
}


@pytest.fixture
def client():
    from sekhmet.main import app
    with TestClient(app) as c:
        yield c


def _seed(hand_overrides: dict | None = None) -> int:
    """Record one hand; return its id."""

    async def _run() -> int:
        hand = {**HAND, **(hand_overrides or {})}
        try:
            await recorder.record_hand(**hand)
            async with db.SessionLocal() as s:
                row = (await s.execute(
                    select(HandRecord.id).order_by(HandRecord.id.desc()).limit(1)
                )).one()
                return row[0]
        finally:
            await db.engine.dispose()

    return asyncio.run(_run())


def test_replay_frames_match_actions(client):
    hand_id = _seed()
    r = client.get(f"/api/history/hands/{hand_id}/replay")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == hand_id
    assert data["table_id"] == "tblRPLAY1"
    assert data["awards"][0]["hand"] == "Three of a Kind"

    frames = data["frames"]
    assert len(frames) == len(HAND["actions"]) + 1

    # Frame 0: dealt state — blinds posted, no last_action, preflop.
    f0 = frames[0]
    assert f0["last_action"] is None
    assert f0["phase"] == "PREFLOP"
    assert f0["board"] == []
    assert f0["pot"] == 15  # sb 5 + bb 10
    hero, bot = f0["players"]
    assert hero["stack"] == 195 and hero["current_bet"] == 5   # sb seat
    assert bot["stack"] == 190 and bot["current_bet"] == 10    # bb seat
    assert hero["hole_cards"] == ["A♠", "K♠"]

    # last_action aligns: frame i is produced by actions[i-1].
    for i in range(1, len(frames)):
        assert frames[i]["last_action"] == HAND["actions"][i - 1]

    # Board grows by street as the replay proceeds.
    assert frames[2]["phase"] == "FLOP" and len(frames[2]["board"]) == 3
    assert frames[4]["phase"] == "TURN" and len(frames[4]["board"]) == 4
    assert frames[6]["phase"] == "RIVER" and len(frames[6]["board"]) == 5

    # Final frame: hero's last bet called, pot fully collected on award.
    assert frames[-1]["phase"] in ("SHOWDOWN", "HAND_COMPLETE")


def test_replay_truncates_gracefully_on_divergence(client):
    # A corrupted action log (FOLD by a seat not in the hand) must not
    # 500 — frames stop at the last valid state.
    bad = {"actions": HAND["actions"][:2] + [{"seat": 9, "action": "FOLD", "amount": 0}]}
    hand_id = _seed(bad)
    r = client.get(f"/api/history/hands/{hand_id}/replay")
    assert r.status_code == 200
    frames = r.json()["frames"]
    assert 1 < len(frames) < len(bad["actions"]) + 1
    assert frames[-1]["last_action"] == HAND["actions"][1]


def test_replay_unknown_hand_404(client):
    assert client.get("/api/history/hands/424242/replay").status_code == 404
