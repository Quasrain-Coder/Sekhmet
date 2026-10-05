"""Tests for trainer stats persistence — attempts table, stats, mistakes.

Flow under test (design: 2026-10-05-trainer-stats-persistence-design.md):
submit with a valid account token persists a TrainingAttemptRecord;
guests score normally but leave no rows.  /stats aggregates per category,
/mistakes lists scenarios whose *latest* attempt is non-optimal.

The endpoint coroutines are invoked directly (they are plain ``async def``
functions on dicts) so each test shares one event loop with the isolated
per-test database — the same pattern as test_models.py.  A couple of thin
TestClient cases pin the HTTP surface (routing, 401 shape).
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sekhmet.api import auth as auth_api
from sekhmet.api import trainer as trainer_api
from sekhmet.main import app
from sekhmet.models import db
from sekhmet.models.records import TrainingAttemptRecord


SCENARIO = "preflop-btn-premium"      # optimal: RAISE 30, category preflop_range
OPTIMAL = {"type": "RAISE", "amount": 30}
WRONG = {"type": "FOLD", "amount": 0}
POT_ODDS = "pot-odds-draw"


def _reset_timer(scenario: str) -> None:
    """Fresh decision-timer start.  ``_start_times`` is a module-level
    singleton shared with earlier tests that GET the same scenario — a
    stale start bleeds 30s+ into our elapsed time on slow runners and
    shaves the timing score off exact-score assertions."""
    trainer_api._runner.start(scenario)


async def _register(username: str) -> str:
    out = await auth_api.register({"username": username, "password": "secret1"})
    return out["token"]


async def _scored_submit(scenario_id: str, action: dict):
    _reset_timer(scenario_id)
    return await trainer_api.submit_decision(scenario_id, action)


async def _all_attempts() -> list[TrainingAttemptRecord]:
    async with db.SessionLocal() as s:
        return list((await s.execute(
            select(TrainingAttemptRecord).order_by(TrainingAttemptRecord.id)
        )).scalars().all())


# ---------------------------------------------------------------------------
# Persistence on submit
# ---------------------------------------------------------------------------


async def test_submit_with_token_persists_attempt():
    token = await _register("trainer1")

    resp = await _scored_submit(
        SCENARIO, {**OPTIMAL, "token": token, "hints_used": 2})
    assert resp["score"]["is_optimal"] is True

    rows = await _all_attempts()
    assert len(rows) == 1
    r = rows[0]
    assert r.username == "trainer1"
    assert r.scenario_id == SCENARIO
    assert r.category == "preflop_range"
    assert r.difficulty == 1
    assert r.is_optimal is True
    assert r.score_total == 100.0
    assert r.hints_used == 2
    assert r.time_taken_ms >= 0
    assert json.loads(r.action) == {"type": "RAISE", "amount": 30}


async def test_guest_submit_scores_but_not_persisted():
    resp = await _scored_submit(SCENARIO, {**OPTIMAL})
    assert resp["score"]["is_optimal"] is True          # guests still train
    assert await _all_attempts() == []


async def test_submit_with_garbage_token_scores_but_not_persisted():
    resp = await _scored_submit(
        SCENARIO, {**OPTIMAL, "token": "garbage.token"})
    assert resp["score"]["is_optimal"] is True
    assert await _all_attempts() == []


# ---------------------------------------------------------------------------
# /stats aggregate
# ---------------------------------------------------------------------------


async def test_stats_aggregates_totals_and_categories():
    token = await _register("statuser")
    await _scored_submit(SCENARIO, {**OPTIMAL, "token": token})
    await _scored_submit(SCENARIO, {**WRONG, "token": token})
    await _scored_submit(POT_ODDS, {**WRONG, "token": token})

    stats = await trainer_api.training_stats(token=token)
    assert stats["total_attempts"] == 3
    # (100 + 15 + 15) / 3 ≈ 43.3
    assert stats["avg_score"] == pytest.approx(43.3, abs=0.1)
    assert stats["optimal_rate"] == pytest.approx(1 / 3, abs=0.01)

    by_cat = {c["category"]: c for c in stats["categories"]}
    assert by_cat["preflop_range"]["attempts"] == 2
    assert by_cat["preflop_range"]["optimal_rate"] == pytest.approx(0.5, abs=0.01)
    assert by_cat["pot_odds"]["attempts"] == 1

    # Chart source: oldest first
    recent = stats["recent"]
    assert [r["score"] for r in recent] == [100.0, 15.0, 15.0]
    assert recent[0]["scenario_id"] == SCENARIO


async def test_stats_empty_account():
    token = await _register("freshguy")
    stats = await trainer_api.training_stats(token=token)
    assert stats["total_attempts"] == 0
    assert stats["avg_score"] is None
    assert stats["optimal_rate"] is None
    assert stats["categories"] == []
    assert stats["recent"] == []


# ---------------------------------------------------------------------------
# /mistakes wrong-answer book
# ---------------------------------------------------------------------------


async def test_mistake_appears_then_fixed_by_optimal_retry():
    token = await _register("mistaker")
    await _scored_submit(SCENARIO, {**WRONG, "token": token})

    out = await trainer_api.training_mistakes(token=token)
    assert len(out["mistakes"]) == 1
    m = out["mistakes"][0]
    assert m["scenario_id"] == SCENARIO
    assert m["title"] == "翻前 BTN 强牌"          # resolved from the library
    assert m["last_score"] == 15.0
    assert m["attempts"] == 1

    # Retry with the optimal action → latest attempt optimal → drops out
    await _scored_submit(SCENARIO, {**OPTIMAL, "token": token})
    out = await trainer_api.training_mistakes(token=token)
    assert out["mistakes"] == []

    # History keeps both attempts (aggregate/chart unaffected)
    stats = await trainer_api.training_stats(token=token)
    assert stats["total_attempts"] == 2


async def test_mistake_keeps_only_latest_per_scenario():
    token = await _register("mistaker2")
    await _scored_submit(SCENARIO, {**WRONG, "token": token})
    await _scored_submit(POT_ODDS, {**WRONG, "token": token})

    out = await trainer_api.training_mistakes(token=token)
    assert {m["scenario_id"] for m in out["mistakes"]} == {SCENARIO, POT_ODDS}
    assert all(m["attempts"] == 1 for m in out["mistakes"])


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def test_stats_and_mistakes_reject_bad_token_over_http():
    client = TestClient(app)
    assert client.get("/api/trainer/stats",
                      params={"token": "bad.beef"}).status_code == 401
    assert client.get("/api/trainer/mistakes",
                      params={"token": "bad.beef"}).status_code == 401


def test_http_round_trip_persists_and_serves_stats():
    """Full HTTP path: register → submit (token in body) → stats shows it."""
    client = TestClient(app)
    reg = client.post("/api/auth/register",
                      json={"username": "httpper", "password": "secret1"})
    assert reg.status_code == 200
    token = reg.json()["token"]

    sub = client.post(f"/api/trainer/scenarios/{SCENARIO}/submit",
                      json={**WRONG, "token": token})
    assert sub.status_code == 200
    assert sub.json()["elapsed_ms"] >= 0            # new field, additive

    stats = client.get("/api/trainer/stats", params={"token": token})
    assert stats.status_code == 200
    assert stats.json()["total_attempts"] == 1
