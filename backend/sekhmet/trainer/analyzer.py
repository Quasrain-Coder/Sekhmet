"""Deep analysis — real equity and EV for a training decision.

Iteration #2 (design: ``2026-10-05-real-ev-analysis-design.md``):
the equity is Monte Carlo simulated against a GTO-chart opponent range
(shared machinery in ``ai_engine/equity.py``), and each candidate
action's EV is computed from it.  When the scenario carries no frozen
state (or no live opponent can be modelled) we fall back to the
author's pre-computed ``analysis`` values — flagged via
``equity_source``.

EV model (single-street approximation, stated in ``assumptions``):

* ``ev_fold = 0``                      — the baseline
* ``ev_check = equity × pot``
* ``ev_call  = equity × (pot + to_call) − to_call``
* ``ev_bet(X) = equity × (pot + 2X) − (1 − equity) × X``  (all-in: X = stack)

The bet formula assumes the opponent *always calls* — a conservative
lower bound (in reality folds add equity × pot).  Future streets are
not modelled.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..game_engine.deck import Card

if TYPE_CHECKING:
    from .scenario_library import Scenario


@dataclass
class AnalysisResult:
    """Detailed analysis of a training decision."""

    equity_player: float         # hero's equity vs the modelled range
    optimal_ev: float            # best EV among candidate actions
    player_ev: float             # EV of the player's actual action
    ev_loss: float               # optimal_ev - player_ev (may be negative)
    is_gto_deviation: bool       # does this deviate meaningfully from best
    suggestion: str              # actionable advice
    details: list[str] = field(default_factory=list)
    equity_source: str = "authored"   # "monte_carlo" | "authored"
    assumptions: list[str] = field(default_factory=list)


# EV 差异低于该值（筹码）视为与最优打平——蒙卡与模型都有噪声
EV_DEVIATION_TOLERANCE = 0.25


def _candidate_amounts(
    scenario: "Scenario", state: Any, stack: int,
) -> dict[str, int]:
    """Bet/raise sizes to evaluate: the optimal action's own sizing,
    capped by the stack.  (``acceptable_range`` maps action types to
    score-weight intervals, not amounts — nothing to extract there.)"""
    amounts: dict[str, int] = {}
    amt = scenario.optimal_action.get("amount", 0)
    if isinstance(amt, (int, float)) and amt > 0:
        amounts[int(amt)] = min(int(amt), stack)
    return dict(sorted(amounts.items()))


def _ev_for_action(
    ptype: str, amount: int, equity: float, pot: int, to_call: int, stack: int,
) -> float:
    """Single-street EV of one action, in chips."""
    if ptype == "FOLD":
        return 0.0
    if ptype == "CHECK":
        return equity * pot
    if ptype == "CALL":
        return equity * (pot + to_call) - to_call
    if ptype in ("BET", "RAISE", "ALL_IN"):
        x = stack if ptype == "ALL_IN" else max(0, amount)
        return equity * (pot + 2 * x) - (1 - equity) * x
    return 0.0


def analyze(
    scenario: "Scenario",
    score_total: float,
    player_action: dict[str, Any] | None = None,
) -> AnalysisResult:
    """Analyse a decision: real (or authored) equity → per-action EV.

    Parameters
    ----------
    scenario : Scenario
        The scenario with a frozen state and reference analysis data.
    score_total : float
        The player's score (0-100) from the scorer — only used for the
        legacy fallback path and suggestion phrasing.
    player_action : dict | None
        ``{"type": "FOLD", "amount": 0}``; ``None`` keeps the legacy
        behaviour (EV estimated from the score ratio).
    """
    mc = _monte_carlo_equity(scenario)
    if mc is not None:
        equity, source = mc[0], "monte_carlo"
    else:
        # Authored fallback: the scenario author's pre-computed estimate.
        equity, source = scenario.analysis.get("equity_vs_range", 0.5), "authored"

    state = scenario.frozen_state
    pot = state.pot.main_pot if state is not None else 0
    hero = state.player(scenario.player_seat) if state is not None else None
    stack = hero.stack if hero is not None else 0
    to_call = 0
    if hero is not None:
        to_call = max(0, state.current_bet - hero.current_bet)

    # Per-action EV table over the actions worth comparing.
    evs: dict[str, float] = {"FOLD": 0.0, "CHECK": _ev_for_action("CHECK", 0, equity, pot, to_call, stack)}
    if to_call > 0:
        evs["CALL"] = _ev_for_action("CALL", 0, equity, pot, to_call, stack)
    for amt in _candidate_amounts(scenario, state, stack):
        evs[f"RAISE:{amt}"] = _ev_for_action("RAISE", amt, equity, pot, to_call, stack)

    optimal_ev = max(evs.values())

    if player_action is None:
        # Legacy path: no real action known — approximate from the score.
        player_ev = optimal_ev * max(0, score_total) / 100
        player_type = None
    else:
        ptype = str(player_action.get("type", "FOLD")).upper()
        pamount = player_action.get("amount", 0)
        pamount = max(0, int(pamount)) if isinstance(pamount, (int, float)) else 0
        player_type = ptype
        if ptype in ("BET", "RAISE"):
            player_ev = _ev_for_action(ptype, pamount, equity, pot, to_call, stack)
        else:
            key = ptype if ptype in evs else "FOLD"
            player_ev = evs[key]

    ev_loss = optimal_ev - player_ev
    is_gto = ev_loss <= EV_DEVIATION_TOLERANCE

    if player_type is None:
        suggestion = ("Great decision! This line is close to GTO optimal."
                      if score_total >= 90 else
                      f"Score {score_total:.0f}/100 — review the hints to close the gap.")
    elif ev_loss <= EV_DEVIATION_TOLERANCE:
        suggestion = f"Solid: your line is worth about {player_ev:+.1f} chips, essentially optimal."
    elif ev_loss < 1.5:
        suggestion = (f"Close — about {ev_loss:.1f} chip of EV left on the table. "
                      "Check the optimal sizing/action below.")
    else:
        suggestion = (f"This action costs roughly {ev_loss:.1f} chips of EV versus the best line. "
                      "Review the hints and the equity number above.")

    details: list[str] = []
    if source == "authored":
        details.append("数据来源：作者预置估计（该场景无法现场模拟）")
    else:
        details.append(f"数据来源：蒙特卡洛模拟 vs 推断范围（单位：筹码，底池 {pot}）")
    if to_call > 0:
        details.append(f"跟注价：{to_call}（需 {to_call / max(pot + to_call, 1):.0%} 胜率保本）")
    if player_type in ("BET", "RAISE", "ALL_IN") or any(
            k.startswith("RAISE") for k in evs):
        details.append("下注 EV 假设对手必然跟注（保守下界）；未建模后续街")
    if player_type is not None:
        best_key = max(evs, key=evs.get)
        details.append(f"你的动作 EV：{player_ev:+.2f} | 最优 {best_key}：{optimal_ev:+.2f}")

    return AnalysisResult(
        equity_player=round(equity, 3),
        optimal_ev=round(optimal_ev, 2),
        player_ev=round(player_ev, 2),
        ev_loss=round(ev_loss, 2),
        is_gto_deviation=not is_gto,
        suggestion=suggestion,
        details=details,
        equity_source=source,
        assumptions=[
            "单街近似：不含后续轮次的下注树",
            "对手范围：GTO 图表按最后加注者位置推断",
        ],
    )


def _monte_carlo_equity(scenario: "Scenario") -> tuple[float, int] | None:
    """Real equity vs an inferred range, or None when not simulatable."""
    from ..ai_engine.equity import (
        equity_vs_combos,
        infer_opponent_range,
        range_combos,
    )
    from ..game_engine.deck import Rank, Suit

    state = scenario.frozen_state
    seat = scenario.player_seat
    if state is None or seat is None:
        return None
    hero = state.player(seat)
    if hero is None or not hero.hole_cards:
        return None
    opp_range = infer_opponent_range(state, seat)
    if opp_range is None:
        return None
    hole: list[Card] = list(hero.hole_cards)
    board = list(state.community_cards)
    known = {(c.rank.value, c.suit.value) for c in hole + board}
    deck = [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in known]
    combos = range_combos(opp_range, deck)
    if not combos:
        return None
    eq = equity_vs_combos(hole, board, combos, rng=random.Random())
    return (eq, len(combos)) if eq is not None else None
