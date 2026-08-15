"""Scenario runner — presents scenarios to the player and scores decisions."""

from __future__ import annotations

import time
from typing import Any

from .scenario_library import Scenario, ScenarioLibrary
from .scorer import score_decision, ScoreBreakdown
from .analyzer import analyze, AnalysisResult


class ScenarioRunner:
    """Orchestrates training sessions.

    Usage::

        lib = ScenarioLibrary()
        lib.load_all()
        runner = ScenarioRunner(lib)

        scenario = runner.next_scenario("preflop_range")
        result = runner.submit(scenario.id, {"type": "FOLD", "amount": 0})
    """

    def __init__(self, library: ScenarioLibrary):
        self.library = library
        self._start_times: dict[str, float] = {}

    def next_scenario(self, category: str | None = None) -> Scenario | None:
        """Return the next scenario, optionally filtered by category."""
        from .scenario_library import ScenarioCategory

        if category:
            cat = ScenarioCategory(category)
            scenarios = self.library.list_by_category(cat)
        else:
            scenarios = self.library.list_all()

        if not scenarios:
            return None

        # Simplest: return the first one (would be random/shuffled in production)
        s = scenarios[0]
        self._start_times[s.id] = time.time()
        return s

    def start(self, scenario_id: str) -> None:
        """Record the decision timer's starting point for *scenario_id*."""
        self._start_times[scenario_id] = time.time()

    def submit(
        self,
        scenario_id: str,
        action: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Score a player's decision and return feedback.

        Returns
        -------
        dict | None
            ``{"score": ScoreBreakdown, "analysis": AnalysisResult, "scenario": Scenario}``
            or None if the scenario wasn't found.
        """
        scenario = self.library.get(scenario_id)
        if scenario is None:
            return None

        elapsed = (time.time() - self._start_times.get(scenario_id, time.time())) * 1000

        score = score_decision(scenario, action, time_taken_ms=elapsed)
        analysis = analyze(scenario, score.total)

        return {
            "score": {
                "total": score.total,
                "action_match": score.action_match,
                "sizing_precision": score.sizing_precision,
                "timing_judgment": score.timing_judgment,
                "feedback": score.feedback,
                "detailed_feedback": score.detailed_feedback,
                "is_optimal": score.is_optimal,
            },
            "analysis": {
                "equity_player": analysis.equity_player,
                "optimal_ev": analysis.optimal_ev,
                "player_ev": analysis.player_ev,
                "ev_loss": analysis.ev_loss,
                "is_gto_deviation": analysis.is_gto_deviation,
                "suggestion": analysis.suggestion,
                "details": analysis.details,
            },
            "scenario": {
                "id": scenario.id,
                "title": scenario.title,
                "category": scenario.category.value,
                "difficulty": scenario.difficulty,
            },
        }

    def get_hint(self, scenario_id: str, level: int = 0) -> str | None:
        """Return a hint for the given scenario."""
        scenario = self.library.get(scenario_id)
        if scenario is None or not scenario.hints:
            return None
        idx = min(max(level, 0), len(scenario.hints) - 1)
        return scenario.hints[idx]
