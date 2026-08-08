"""Deep analysis — equity, range, and GTO deviation analysis.

Used by the trainer to produce detailed post-decision feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scenario_library import Scenario


@dataclass
class AnalysisResult:
    """Detailed analysis of a training decision."""

    equity_player: float         # player's estimated equity vs opponent range
    optimal_ev: float            # EV of optimal action
    player_ev: float             # estimated EV of player's chosen action
    ev_loss: float               # how much EV the player lost (optimal - player)
    is_gto_deviation: bool       # does this deviate from GTO
    suggestion: str              # actionable advice
    details: list[str] = field(default_factory=list)


def analyze(scenario: "Scenario", score_total: float) -> AnalysisResult:
    """Produce a detailed analysis based on the scenario and score.

    Parameters
    ----------
    scenario : Scenario
        The scenario with reference data.
    score_total : float
        The player's total score (0–100) from the scorer.

    Returns
    -------
    AnalysisResult
    """
    analysis = scenario.analysis
    equity = analysis.get("equity_vs_range", 0.5)

    # Estimate EV based on which action was probably taken
    player_ev: float
    optimal_ev: float
    if "ev_fold" in analysis:
        optimal_ev = max(
            analysis.get("ev_fold", 0),
            analysis.get("ev_call", 0),
            analysis.get("ev_raise", 0),
            analysis.get("ev_bluff", 0),
            analysis.get("ev_check", 0),
        )
        # Approximate player EV from score
        ev_ratio = max(0, score_total / 100)
        player_ev = optimal_ev * ev_ratio
    else:
        optimal_ev = analysis.get("ev_raise", analysis.get("ev_call", 0))
        player_ev = optimal_ev * max(0, score_total / 100)

    ev_loss = optimal_ev - player_ev
    is_gto = ev_loss < 0.5

    if score_total >= 90:
        suggestion = "Great decision! This line is close to GTO optimal."
    elif score_total >= 70:
        suggestion = f"Good attempt, but you left ~{ev_loss:.1f} BB on the table. Review the hints to close the gap."
    elif score_total >= 40:
        suggestion = f"This decision cost you about {ev_loss:.1f} BB in expected value. Focus on understanding the underlying principles."
    else:
        suggestion = f"Significant EV loss ({ev_loss:.1f} BB). Re-read the scenario description and study the category fundamentals."

    details = []
    if "pot_odds_required" in analysis:
        req = analysis["pot_odds_required"]
        details.append(f"Pot odds required: {req:.0%} | Your equity: {equity:.0%}")
    details.append(f"Optimal EV: {optimal_ev:+.1f} BB | Your estimated EV: {player_ev:+.1f} BB")

    return AnalysisResult(
        equity_player=equity,
        optimal_ev=round(optimal_ev, 2),
        player_ev=round(player_ev, 2),
        ev_loss=round(ev_loss, 2),
        is_gto_deviation=not is_gto,
        suggestion=suggestion,
        details=details,
    )
