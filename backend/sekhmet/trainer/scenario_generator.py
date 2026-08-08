"""Auto-generate training scenarios from historical weaknesses.

Given a player's training history (scenario_id + scores), this module
suggests which categories to practice and generates new scenarios
targeting the player's weakest areas.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scenario_library import Scenario, ScenarioCategory, ScenarioLibrary


def analyze_weaknesses(
    history: list[dict],
) -> dict[str, float]:
    """Return average score per category from training history.

    Parameters
    ----------
    history : list[dict]
        List of ``{"category": "preflop_range", "score": 85.0}`` entries.

    Returns
    -------
    dict[str, float]
        Category → average score (lower = weaker).
    """
    cat_scores: dict[str, list[float]] = defaultdict(list)
    for entry in history:
        cat = entry.get("category", "unknown")
        score = entry.get("score", 0)
        cat_scores[cat].append(score)

    return {
        cat: sum(scores) / len(scores)
        for cat, scores in sorted(cat_scores.items(), key=lambda x: sum(x[1]) / len(x[1]))
    }


def suggest_next_category(history: list[dict]) -> str | None:
    """Return the category where the player needs the most practice."""
    weaknesses = analyze_weaknesses(history)
    if not weaknesses:
        return None
    return min(weaknesses, key=lambda k: weaknesses[k])
