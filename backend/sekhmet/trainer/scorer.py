"""Decision scorer — evaluates how well a player's action matches the optimal.

Scoring formula (configurable via ScoringWeights in config.py):
    total = action_match * 0.60 + sizing_precision * 0.25 + timing * 0.15
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import app_config
from ..game_engine.game_state import ActionType
from .scenario_library import Scenario


# ---------------------------------------------------------------------------
# Score breakdown
# ---------------------------------------------------------------------------


@dataclass
class ScoreBreakdown:
    """Detailed score for a single training decision."""

    total: float                    # 0–100
    action_match: float            # 0–60  (did you pick the right action?)
    sizing_precision: float        # 0–25  (was your bet size appropriate?)
    timing_judgment: float         # 0–15  (reserved for timed decisions)
    feedback: str                  # one-line summary
    detailed_feedback: str         # paragraph with reasoning
    is_optimal: bool               # did you pick the optimal action?


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------


def score_decision(
    scenario: Scenario,
    player_action: dict[str, Any],
    time_taken_ms: float = 0,
) -> ScoreBreakdown:
    """Score a player's decision against the scenario's optimal action.

    Parameters
    ----------
    scenario : Scenario
        The scenario being evaluated.
    player_action : dict
        ``{"type": "FOLD", "amount": 0}`` or similar.
    time_taken_ms : float
        How long the player took (future: timing bonus/penalty).

    Returns
    -------
    ScoreBreakdown
    """
    weights = app_config.scoring

    ptype = player_action.get("type", "").upper()
    raw_amount = player_action.get("amount", 0)
    # Client-controlled input: negative or non-numeric amounts must not
    # produce negative scores (or a TypeError from min/max).
    pamount = max(0, raw_amount) if isinstance(raw_amount, (int, float)) else 0
    optimal = scenario.optimal_action
    otype = optimal["type"].upper()
    oamount = optimal.get("amount", 0)

    # --- 1.  Action match (60%) ---
    if ptype == otype:
        action_score = weights.action_match * 100
    else:
        # Partial credit if within acceptable range
        acceptable = scenario.acceptable_range
        if ptype in acceptable:
            lo, hi = acceptable[ptype]
            action_score = weights.action_match * 100 * (lo + hi) / 2
        else:
            action_score = 0.0

    # --- 2.  Sizing precision (25%) ---
    sizing_score = 0.0
    if ptype == otype and oamount > 0:
        ratio = min(pamount, oamount) / max(pamount, oamount) if max(pamount, oamount) > 0 else 1.0
        sizing_score = weights.sizing_precision * 100 * ratio
    elif ptype in ("CHECK", "FOLD", "CALL") and ptype == otype:
        sizing_score = weights.sizing_precision * 100  # no sizing needed

    # --- 3.  Timing (15%) — simple version: full credit if under 30s ---
    if time_taken_ms <= 30_000:
        timing_score = weights.timing_judgment * 100
    else:
        timing_score = max(0, weights.timing_judgment * 100 * (1 - (time_taken_ms - 30_000) / 60_000))

    total = action_score + sizing_score + timing_score

    # --- Feedback ---
    is_optimal = ptype == otype and (oamount == 0 or abs(pamount - oamount) / max(oamount, 1) < 0.2)

    if total >= 90:
        fb = "Excellent! Perfect decision."
        detail = f"You chose {ptype}" + (f" {pamount}" if pamount > 0 else "") + ", which matches the optimal play."
    elif total >= 70:
        fb = "Good decision, close to optimal."
        detail = _detail_near_miss(ptype, pamount, otype, oamount, scenario)
    elif total >= 40:
        fb = "Decent, but there's a better option."
        detail = _detail_suboptimal(ptype, otype, scenario)
    else:
        fb = "Poor decision. Review the hints and try again."
        detail = _detail_poor(ptype, otype, scenario)

    return ScoreBreakdown(
        total=round(total, 1),
        action_match=round(action_score, 1),
        sizing_precision=round(sizing_score, 1),
        timing_judgment=round(timing_score, 1),
        feedback=fb,
        detailed_feedback=detail,
        is_optimal=is_optimal,
    )


# ---------------------------------------------------------------------------
# Feedback text helpers
# ---------------------------------------------------------------------------


def _detail_near_miss(ptype: str, pamount: int, otype: str, oamount: int, scenario: Scenario) -> str:
    lines = [f"You chose {ptype}" + (f" {pamount}" if pamount > 0 else "") + "."]
    if ptype != otype:
        lines.append(f"The optimal action is {otype}" + (f" {oamount}" if oamount > 0 else "") + ".")
    elif pamount != oamount:
        lines.append(f"Optimal sizing is {oamount}. Your sizing of {pamount} is close but could be adjusted.")
    if scenario.hints:
        lines.append(f"Hint: {scenario.hints[0]}")
    return " ".join(lines)


def _detail_suboptimal(ptype: str, otype: str, scenario: Scenario) -> str:
    lines = [
        f"You chose {ptype}, but the optimal action is {otype}.",
        f"Category: {scenario.category.value.replace('_', ' ').title()}.",
    ]
    if scenario.hints:
        lines.append(f"Hint: {scenario.hints[0]}")
    return " ".join(lines)


def _detail_poor(ptype: str, otype: str, scenario: Scenario) -> str:
    lines = [
        f"Your action ({ptype}) deviates significantly from optimal ({otype}).",
    ]
    for hint in scenario.hints[:2]:
        lines.append(f"Hint: {hint}")
    return " ".join(lines)
