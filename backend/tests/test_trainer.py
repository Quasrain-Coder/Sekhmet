"""Tests for the training module: library, scorer, analyzer, runner."""

import pytest
from fastapi.testclient import TestClient

from sekhmet.main import app
from sekhmet.trainer.scenario_library import (
    Scenario,
    ScenarioCategory,
    ScenarioLibrary,
    BUILTIN_SCENARIOS,
)
from sekhmet.trainer.scorer import score_decision
from sekhmet.trainer.analyzer import analyze
from sekhmet.trainer.scenario_runner import ScenarioRunner
from sekhmet.trainer.scenario_generator import analyze_weaknesses, suggest_next_category


# ---------------------------------------------------------------------------
# Scenario library
# ---------------------------------------------------------------------------


def test_library_loads_builtins():
    lib = ScenarioLibrary(data_dir="/nonexistent")
    for data in BUILTIN_SCENARIOS:
        lib.add(Scenario.from_yaml(data))
    assert len(lib) == 5

    flop = lib.list_by_category(ScenarioCategory.POSTFLOP_VALUE)
    assert len(flop) == 1

    easy = lib.list_by_difficulty(2)
    assert len(easy) >= 2


def test_library_get():
    lib = ScenarioLibrary(data_dir="/nonexistent")
    for data in BUILTIN_SCENARIOS:
        lib.add(Scenario.from_yaml(data))

    s = lib.get("preflop-btn-premium")
    assert s is not None
    assert s.title == "翻前 BTN 强牌"
    assert s.optimal_action == {"type": "RAISE", "amount": 30}


def test_library_empty():
    lib = ScenarioLibrary(data_dir="/nonexistent")
    assert len(lib) == 0
    assert lib.list_all() == []


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def test_scorer_perfect_match():
    s = Scenario.from_yaml(BUILTIN_SCENARIOS[1])  # BTN AKs → RAISE 30
    result = score_decision(s, {"type": "RAISE", "amount": 30})
    assert result.total > 90
    assert result.is_optimal


def test_scorer_wrong_action():
    s = Scenario.from_yaml(BUILTIN_SCENARIOS[0])  # UTG KJo → FOLD
    result = score_decision(s, {"type": "RAISE", "amount": 45})
    assert result.total < 60
    assert not result.is_optimal


def test_scorer_partial_credit():
    s = Scenario.from_yaml(BUILTIN_SCENARIOS[0])  # acceptable: FOLD [0.7, 1.0], RAISE [0.0, 0.3]
    result = score_decision(s, {"type": "RAISE", "amount": 30})
    # Should get partial credit for RAISE (within acceptable range)
    assert result.action_match < 60  # not full credit
    assert result.action_match > 0   # but some credit
    assert result.total > 0


def test_scorer_sizing_penalty():
    s = Scenario.from_yaml(BUILTIN_SCENARIOS[1])  # optimal: RAISE 30
    result = score_decision(s, {"type": "RAISE", "amount": 90})
    assert result.total < 90  # penalty for bad sizing
    assert result.sizing_precision < 25


def test_scorer_timing_bonus():
    s = Scenario.from_yaml(BUILTIN_SCENARIOS[1])
    fast = score_decision(s, {"type": "RAISE", "amount": 30}, time_taken_ms=5000)
    slow = score_decision(s, {"type": "RAISE", "amount": 30}, time_taken_ms=60000)
    assert fast.timing_judgment == 15.0  # full timing credit
    assert slow.timing_judgment < 15.0


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


def test_analyzer_good_score():
    s = Scenario.from_yaml(BUILTIN_SCENARIOS[1])
    a = analyze(s, score_total=95)
    assert not a.is_gto_deviation
    assert a.ev_loss < 0.5


def test_analyzer_poor_score():
    s = Scenario.from_yaml(BUILTIN_SCENARIOS[0])
    a = analyze(s, score_total=25)
    assert len(a.suggestion) > 0
    assert a.equity_player > 0
    # With score 25, EV loss should be significant
    assert a.player_ev < a.optimal_ev or a.player_ev <= 0


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------


def test_runner_flow():
    lib = ScenarioLibrary(data_dir="/nonexistent")
    for data in BUILTIN_SCENARIOS:
        lib.add(Scenario.from_yaml(data))

    runner = ScenarioRunner(lib)

    scenario = runner.next_scenario("preflop_range")
    assert scenario is not None
    assert scenario.category == ScenarioCategory.PREFLOP_RANGE

    result = runner.submit(scenario.id, {"type": "FOLD", "amount": 0})
    assert result is not None
    assert "score" in result
    assert "analysis" in result
    assert result["score"]["total"] > 0

    hint = runner.get_hint(scenario.id, level=0)
    assert hint is not None


def test_runner_unknown_scenario():
    lib = ScenarioLibrary(data_dir="/nonexistent")
    runner = ScenarioRunner(lib)
    assert runner.submit("nonexistent", {"type": "FOLD"}) is None
    assert runner.get_hint("nonexistent") is None


# ---------------------------------------------------------------------------
# Scenario generator
# ---------------------------------------------------------------------------


def test_analyze_weaknesses():
    history = [
        {"category": "preflop_range", "score": 85},
        {"category": "preflop_range", "score": 75},
        {"category": "bluffing", "score": 40},
        {"category": "bluffing", "score": 50},
        {"category": "pot_odds", "score": 90},
    ]
    w = analyze_weaknesses(history)
    assert w["bluffing"] == 45.0
    assert w["preflop_range"] == 80.0
    assert w["pot_odds"] == 90.0


def test_suggest_next_category():
    history = [
        {"category": "preflop_range", "score": 80},
        {"category": "bluffing", "score": 35},
        {"category": "pot_odds", "score": 70},
    ]
    assert suggest_next_category(history) == "bluffing"


def test_suggest_empty_history():
    assert suggest_next_category([]) is None


# ---------------------------------------------------------------------------
# Trainer REST API
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return TestClient(app)


def test_trainer_list_categories(client):
    resp = client.get("/api/trainer/categories")
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    assert "preflop_range" in cats
    assert "bluffing" in cats


def test_trainer_list_scenarios(client):
    resp = client.get("/api/trainer/scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["scenarios"]) >= 5


def test_trainer_get_scenario(client):
    resp = client.get("/api/trainer/scenarios/preflop-btn-premium")
    assert resp.status_code == 200
    assert resp.json()["title"] == "翻前 BTN 强牌"


def test_trainer_get_scenario_not_found(client):
    resp = client.get("/api/trainer/scenarios/nonexistent")
    assert resp.status_code == 404


def test_trainer_submit_decision(client):
    resp = client.post(
        "/api/trainer/scenarios/preflop-btn-premium/submit",
        json={"type": "RAISE", "amount": 30},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"]["total"] > 90
    assert data["score"]["is_optimal"]


def test_trainer_get_hint(client):
    resp = client.get("/api/trainer/scenarios/preflop-utg-marginal/hint?level=0")
    assert resp.status_code == 200
    assert "hint" in resp.json()


def test_scorer_negative_amount_clamped():
    """Negative/absurd client amounts must not produce negative scores."""
    from sekhmet.trainer.scorer import score_decision
    from sekhmet.trainer.scenario_library import Scenario, ScenarioCategory

    s = Scenario(
        id="x", title="t", description="d",
        category=ScenarioCategory.PREFLOP_RANGE, difficulty=1,
        optimal_action={"type": "RAISE", "amount": 30},
    )
    r = score_decision(s, {"type": "RAISE", "amount": -50})
    assert r.total >= 0
    # non-numeric amount must not crash the scorer
    r2 = score_decision(s, {"type": "RAISE", "amount": "banana"})
    assert r2.total >= 0


def test_hint_negative_level_returns_first_hint():
    from sekhmet.trainer.scenario_library import Scenario, ScenarioCategory
    from sekhmet.trainer.scenario_runner import ScenarioRunner

    lib = ScenarioLibrary()
    s = Scenario(
        id="x", title="t", description="d",
        category=ScenarioCategory.PREFLOP_RANGE, difficulty=1,
        optimal_action={"type": "FOLD", "amount": 0},
        hints=["first", "second"],
    )
    lib.add(s)
    runner = ScenarioRunner(lib)
    assert runner.get_hint("x", level=-5) == "first"
    assert runner.get_hint("x", level=0) == "first"


def test_scenario_detail_starts_decision_timer(monkeypatch):
    """GET /scenarios/{id} marks the timing start; a 60s ponder must lose
    part of the timing score (previously elapsed was always ~0)."""
    from sekhmet.api import trainer as trainer_api

    rest_client = TestClient(app)
    resp = rest_client.get("/api/trainer/scenarios/preflop-utg-marginal")
    assert resp.status_code == 200
    assert "preflop-utg-marginal" in trainer_api._runner._start_times

    # simulate a 60-second think
    started = trainer_api._runner._start_times["preflop-utg-marginal"]
    monkeypatch.setattr(
        "sekhmet.trainer.scenario_runner.time.time",
        lambda: started + 60.0,
    )
    resp2 = rest_client.post("/api/trainer/scenarios/preflop-utg-marginal/submit",
                             json={"type": "FOLD", "amount": 0})
    assert resp2.status_code == 200
    score = resp2.json()["score"]
    # 60s → timing component halved: 60 + 25 + 7.5 = 92.5 (not the old 100)
    assert score["timing_judgment"] == 7.5
    assert score["total"] == 92.5
