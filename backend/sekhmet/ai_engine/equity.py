"""Shared Monte Carlo equity machinery — used by GTOBot and the trainer.

Extracted from ``gto_bot`` (iteration #2, design:
``docs/superpowers/specs/2026-10-05-real-ev-analysis-design.md``) so the
trainer's analyzer can compute *real* equity/EV instead of deriving it
from scores.

Key differences from the bot's original inline version: the board may
be incomplete (preflop training scenarios) — missing community cards
are dealt per sample, so a full-runout equity is computed.  With a
complete board the hero's score is evaluated once (same fast path as
the bot).
"""

from __future__ import annotations

import random

from ..game_engine import GamePhase, GameState
from ..game_engine.deck import Card, Rank, Suit
from ..game_engine.hand_evaluator import evaluate_7_cards
from .gto_ranges import (
    BB_DEFEND_CALL,
    LIMP_RANGE,
    RFI,
    THREE_BET,
    Range,
    range_frequency,
)

# Complete-board sampling uses fewer samples (hero score is fixed, so
# each sample is one opponent evaluation); runout sampling needs more
# to damp the added variance of dealing the board.
FAST_SAMPLES = 200
RUNOUT_SAMPLES = 300


def range_combos(rng_dict: Range, deck: list[Card]) -> list[tuple[Card, Card, float]]:
    """All remaining hole-card pairs inside *rng_dict*, with weights."""
    combos: list[tuple[Card, Card, float]] = []
    for i, c1 in enumerate(deck):
        for c2 in deck[i + 1:]:
            freq = range_frequency(rng_dict, c1, c2)
            if freq > 0:
                combos.append((c1, c2, freq))
    return combos


def weighted_sample(
    combos: list[tuple[Card, Card, float]],
    total_weight: float,
    rng: random.Random,
) -> tuple[Card, Card]:
    """One frequency-weighted draw of a hole-card pair."""
    target = rng.random() * total_weight
    acc = 0.0
    for c1, c2, freq in combos:
        acc += freq
        if target <= acc:
            return c1, c2
    return combos[-1][0], combos[-1][1]


def infer_opponent_range(state: GameState, player_seat: int) -> Range | None:
    """Estimate the relevant opponent's preflop range from the table
    story (position of the last aggressor + bet level).

    Preflop: the current bet level says raise vs 3-bet vs limp.
    Postflop: pot size hints at the preflop story (raised vs limped
    pot) — the opponent's postflop actions do not narrow the range.
    (Known simplification, shared with GTOBot.)
    """
    opps = [p.seat_idx for p in state.players
            if p.seat_idx != player_seat and (p.is_active or p.is_all_in)]
    if not opps:
        return None
    aggressor = state.last_aggressor_idx
    if aggressor is None or aggressor == player_seat or aggressor not in opps:
        aggressor = opps[0]
    bucket = position_bucket(aggressor, state)
    # A big blind who *raised* preflop is strong (model as UTG, the
    # tightest chart); a big blind who only defended and then bet
    # postflop is wide — the defend range.
    if state.phase == GamePhase.PREFLOP:
        if bucket == "bb":
            bucket = "utg"
        if state.current_bet >= state.big_blind * 7:
            return THREE_BET[bucket]
        if state.current_bet > state.big_blind:
            return RFI[bucket]
        return LIMP_RANGE
    if bucket == "bb":
        return BB_DEFEND_CALL
    # Raised pot (a 2.5bb+ open HU already yields 60+ chips): model
    # the aggressor with their RFI chart.  A 4-way limped pot stays
    # below this cutoff and keeps the wide limp range.
    if state.pot.main_pot >= (state.small_blind + state.big_blind) * 4:
        return RFI[bucket]
    return LIMP_RANGE


def position_bucket(seat: int, state: GameState) -> str:
    """Named position bucket for *seat* (blinds first, then by seats
    acting after it, scaled to the table size so 6-max and 9-max
    map onto the same five buckets)."""
    if state.sb_seat == seat:
        return "sb"
    if state.bb_seat == seat:
        return "bb"
    after = seats_after(seat, state)
    if after == 0:
        return "btn"
    live = len([p for p in state.players if p.is_active or p.is_all_in])
    frac = after / max(live - 1, 1)
    if frac < 0.35:
        return "co"
    if frac < 0.6:
        return "mp"
    return "utg"


def seats_after(seat: int, state: GameState) -> int:
    """How many live seats act after *seat* in postflop order."""
    seats = sorted(p.seat_idx for p in state.players
                   if p.is_active or p.is_all_in)
    if len(seats) <= 1:
        return 0
    anchor = state.dealer_idx
    anchor_pos = len(seats) - 1
    for i, s in enumerate(seats):
        if s > anchor:
            break
        anchor_pos = i
    order = seats[anchor_pos + 1:] + seats[:anchor_pos + 1]
    if seat not in order:
        return 0
    return len(order) - 1 - order.index(seat)


def equity_vs_combos(
    hole: list[Card],
    board: list[Card],
    combos: list[tuple[Card, Card, float]],
    samples: int | None = None,
    rng: random.Random | None = None,
) -> float | None:
    """Monte Carlo equity of *hole* vs weighted opponent *combos*.

    The board is completed per sample when it has fewer than 5 cards
    (preflop/flop/turn training scenarios); with a full board the
    hero's score is evaluated once.  Returns ``None`` when there is
    nothing to beat.
    """
    if not combos or len(hole) != 2:
        return None
    rng = rng if rng is not None else random.Random()
    board = list(board)
    known = {(c.rank.value, c.suit.value) for c in hole + board}
    deck = [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in known]
    total_weight = sum(freq for _, _, freq in combos)

    complete = len(board) == 5
    if samples is None:
        samples = FAST_SAMPLES if complete else RUNOUT_SAMPLES

    hero_score = evaluate_7_cards(hole + board) if complete else None
    wins = ties = 0
    for _ in range(samples):
        c1, c2 = weighted_sample(combos, total_weight, rng)
        if complete:
            our = hero_score
            opp_score = evaluate_7_cards([c1, c2] + board)
        else:
            # Deal the remaining board + (implicitly) keep villain's cards
            # out of the runout pool.
            need = 5 - len(board)
            drawn = {(c1.rank.value, c1.suit.value),
                     (c2.rank.value, c2.suit.value)}
            pool = [c for c in deck
                    if (c.rank.value, c.suit.value) not in drawn]
            runout = rng.sample(pool, need)
            full_board = board + runout
            our = evaluate_7_cards(hole + full_board)
            opp_score = evaluate_7_cards([c1, c2] + full_board)
        if our > opp_score:
            wins += 1
        elif our == opp_score:
            ties += 1
    return (wins + ties / 2) / samples
