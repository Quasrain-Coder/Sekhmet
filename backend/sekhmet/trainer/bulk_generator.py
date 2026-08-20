"""Bulk-generate training scenarios from a set of structured spot templates.

Design doc §5.5 planned "给定约束随机生成" as the third source of
scenarios.  This module turns that into practice: a handful of spot
templates (each fixing a category + decision structure) are instantiated
many times with random hole/board/bet combinations.  The GTO bot picks
the reference action; a quality filter keeps only non-trivial spots.

Every generated scenario is *deterministic* for a given seed, so the
same command line reproduces the same library (and tests can assert on
exact counts).

Run directly::

    python -m sekhmet.trainer.bulk_generator --count 500 --seed 20260819 --dry-run
    python -m sekhmet.trainer.bulk_generator --count 500 --seed 20260819
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..game_engine import GamePhase, GameState, Player
from ..game_engine.deck import Card, Rank, Suit
from ..game_engine.hand_evaluator import HandRank, evaluate_7_cards
from ..ai_engine.gto_bot import GTOBot
from ..ai_engine.rule_bot import _draw_outs, _made_hand_strength
from .scenario_library import Scenario, ScenarioCategory, state_from_spec
from .scorer import score_decision

DEFAULT_SEED = 20260819
DEFAULT_TARGET = 500

# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------

_RANK = {r.value: r for r in Rank}
_SUIT = {s.value: s for s in Suit}


def _card(text: str) -> Card:
    rank = _RANK[int(text[:-1])] if text[:-1].isdigit() else _RANK[{
        "J": 11, "Q": 12, "K": 13, "A": 14}[text[:-1]]]
    return Card(rank, _SUIT[text[-1]])


def _all_cards() -> list[Card]:
    return [Card(r, s) for r in Rank for s in Suit]


def _remove(cards: list[Card], used: set[tuple[int, int]]) -> Card:
    """Draw a random card not in *used* (rank, suit)."""
    while True:
        c = cards.pop()
        if (c.rank.value, c.suit.value) not in used:
            return c
        # extremely unlikely to exhaust; guard anyway
        if not cards:
            raise RuntimeError("card pool exhausted")


# ---------------------------------------------------------------------------
# Spot template helpers
# ---------------------------------------------------------------------------


def _score(hole: list[Card], board: list[Card]) -> tuple[HandRank, list[int]]:
    s = evaluate_7_cards(hole + board)
    return s.rank, list(s.kickers)


def _board_has(hole: list[Card], board: list[Card], want: HandRank) -> bool:
    return _score(hole, board)[0] == want


def _hero_bet_for(seat: int, bb: int, current_bet: int) -> int | None:
    """hero_current_bet for the given seat: the BB's blind is already
    matched; anyone else faces the full current_bet."""
    if seat == bb:
        return None  # auto: current_bet if hero is bb (full blind matched)
    return 0


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------


@dataclass
class Template:
    """One scenario template — a category plus a way to build a spot."""

    key: str
    category: ScenarioCategory
    difficulty: int
    allowed_actions: set[str]
    # Second-best action used to prove the spot is not trivial.
    alt_actions: list[str]
    build: Callable[[random.Random], dict[str, Any] | None]
    # Optional predicate on the built spec's GameState before accepting.
    check: Callable[[GameState], bool] | None = None
    title_tpl: str = ""
    desc_tpl: str = ""
    hints: list[str] = field(default_factory=list)
    # Reference-action source: GTOBot by default; a fixed action (or a
    # callable(gs, seat) → (type, amount)) for spots the bot won't
    # produce — e.g. a pure river bluff: the bot only value-bets or
    # semi-bluffs, it never bets a bare high card.
    fixed_reference: (
        tuple[str, int] | Callable[[GameState, int], tuple[str, int]] | None
    ) = None


def _pick_board(rng: random.Random, hole: list[Card], n: int,
                ranks: list[int] | None = None,
                suits: list[Suit] | None = None) -> list[Card]:
    """n random board cards avoiding hole ranks (and optional constraints).

    *ranks* restricts the ranks that may appear (for paired/two-tone
    textures); *suits* restricts suits (for flush-draw textures).
    """
    used = {(c.rank.value, c.suit.value) for c in hole}
    deck = [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in used
            and (ranks is None or r.value in ranks)
            and (suits is None or s in suits)]
    rng.shuffle(deck)
    return deck[:n]


# ---------------------------------------------------------------------------
# Spot builders (one per template)
# ---------------------------------------------------------------------------


def _two_offsuit(rng: random.Random, r1: Rank, r2: Rank) -> list[Card]:
    """Two offsuit cards (random distinct suits) of the given ranks."""
    s1 = rng.choice(list(Suit))
    s2 = rng.choice([s for s in Suit if s != s1])
    return [Card(r1, s1), Card(r2, s2)]


def build_preflop_open_fold(rng: random.Random) -> dict[str, Any] | None:
    """UTG/MP with a dominated hand facing the blinds → FOLD."""
    # Pick a marginal offsuit hand (KJo-ish, ATo, QJo) — not so bad it's
    # a slam-dunk fold, not so good it's a raise.
    r1 = rng.choice([Rank.KING, Rank.QUEEN, Rank.JACK, Rank.TEN])
    r2 = rng.choice([Rank.JACK, Rank.TEN, Rank.NINE, Rank.EIGHT])
    if r1 == r2:
        return None
    hi, lo = sorted([r1, r2], reverse=True)
    hole = _two_offsuit(rng, hi, lo)
    seat = rng.choice([3, 4])  # UTG-ish, never late position
    pot = rng.choice([15, 15, 20])
    return dict(
        phase="PREFLOP", player_seat=seat, hole=[str(c) for c in hole],
        board=[], pot=pot, dealer=8, sb=0, bb=1, current_bet=10, stack=200,
        hero_current_bet=None,
    )


def build_preflop_open_raise(rng: random.Random) -> dict[str, Any] | None:
    """BTN/CO with a premium hand, unopened pot → RAISE."""
    pair = rng.random() < 0.5
    if pair:
        r = rng.choice([Rank.ACE, Rank.KING, Rank.QUEEN, Rank.JACK])
        s1 = rng.choice(list(Suit))
        s2 = rng.choice([s for s in Suit if s != s1])
        hole = [Card(r, s1), Card(r, s2)]
    else:
        r1 = rng.choice([Rank.ACE, Rank.KING])
        r2 = rng.choice([Rank.KING, Rank.QUEEN, Rank.JACK])
        if r1 == r2:
            return None
        hole = _two_offsuit(rng, r1, r2)
    seat = rng.choice([5, 6])  # BTN / CO
    pot = rng.choice([15, 15, 20])
    return dict(
        phase="PREFLOP", player_seat=seat, hole=[str(c) for c in hole],
        board=[], pot=pot, dealer=5, sb=0, bb=1, current_bet=10, stack=200,
        hero_current_bet=None,
    )


def build_preflop_bb_defend(rng: random.Random) -> dict[str, Any] | None:
    """BB facing a BTN steal → defend wide (CALL)."""
    # Reasonable-but-not-premium hand: suited connector / suited ace /
    # middle pair.  Keep it callable, not a 3-bet monster.
    hole: list[Card] | None = None
    choice = rng.random()
    s = rng.choice(list(Suit))
    if choice < 0.4:  # suited connector
        lo = rng.choice([Rank.FIVE, Rank.SIX, Rank.SEVEN, Rank.EIGHT])
        hole = [Card(lo, s), Card(Rank(lo.value + 1), s)]
    elif choice < 0.7:  # suited ace
        hole = [Card(Rank.ACE, s), Card(rng.choice([
            Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX]), s)]
    else:  # small pair
        r = rng.choice([Rank.FIVE, Rank.SIX, Rank.SEVEN, Rank.EIGHT, Rank.NINE])
        s2 = rng.choice([x for x in Suit if x != s])
        hole = [Card(r, s), Card(r, s2)]
    if hole is None:
        return None
    pot = rng.choice([20, 25, 30])
    return dict(
        phase="PREFLOP", player_seat=1, hole=[str(c) for c in hole],
        board=[], pot=pot, dealer=5, sb=0, bb=1, current_bet=25, stack=190,
        hero_current_bet=10,  # big blind already matched
    )


def build_flop_tptk_bet(rng: random.Random) -> dict[str, Any] | None:
    """Top pair top kicker facing a bet → CALL/RAISE."""
    # Hero holds a big kicker with an A on board.
    k = rng.choice([Rank.KING, Rank.QUEEN, Rank.JACK])
    a_suit = rng.choice(list(Suit))
    other_suit = rng.choice([s for s in Suit if s != a_suit])
    hole = [Card(Rank.ACE, a_suit), Card(k, other_suit)]
    # Board: our A + two blanks (no pairs, no flush/straight).
    board = [Card(Rank.ACE, other_suit)]
    used = {(c.rank.value, c.suit.value) for c in hole + board}
    deck = [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in used and r.value not in (14, 13, 12, 11)]
    rng.shuffle(deck)
    board += deck[:2]
    pot = rng.choice([50, 60, 70, 80])
    bet = int(pot * rng.choice([0.4, 0.5, 0.66]))
    return dict(
        phase="FLOP", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=bet, stack=180,
        hero_current_bet=0,
    )


def build_flop_overpair_bet(rng: random.Random) -> dict[str, Any] | None:
    """Overpair vs an unopened pot → BET."""
    r = rng.choice([Rank.JACK, Rank.QUEEN, Rank.KING])
    hole = [Card(r, Suit.SPADES), Card(r, Suit.HEARTS)]
    # Board all below the pair, no two-tone, no pairs.
    board = _pick_board(rng, hole, 3, ranks=[2, 3, 4, 5, 6, 7, 8, 9, 10])
    pot = rng.choice([60, 80, 100])
    return dict(
        phase="FLOP", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=0, stack=200,
        hero_current_bet=0,
    )


def build_flop_two_pair(rng: random.Random) -> dict[str, Any] | None:
    """Two pair vs a bet → RAISE."""
    hi = rng.choice([Rank.QUEEN, Rank.KING])
    lo = rng.choice([Rank.NINE, Rank.TEN])
    hi_suit, lo_suit = Suit.SPADES, Suit.HEARTS
    hole = [Card(hi, hi_suit), Card(lo, lo_suit)]
    # Board pairs both our cards (Q x 9 x) + a blank.
    blank_suit = Suit.DIAMONDS
    board = [Card(hi, Suit.DIAMONDS), Card(lo, Suit.CLUBS)]
    used = {(c.rank.value, c.suit.value) for c in hole + board}
    deck = [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in used and r.value not in (hi.value, lo.value, 14)]
    rng.shuffle(deck)
    board += deck[:1]
    pot = rng.choice([80, 100, 120])
    bet = int(pot * 0.33)
    return dict(
        phase="FLOP", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=bet, stack=180,
        hero_current_bet=0,
    )


def build_flop_draw_call(rng: random.Random) -> dict[str, Any] | None:
    """Flush or OESD vs a bet → CALL on price."""
    if rng.random() < 0.5:
        # Flush draw: suited hand + two of our suit on board.
        s = rng.choice(list(Suit))
        r1 = rng.choice([Rank.ACE, Rank.KING, Rank.QUEEN, Rank.JACK])
        r2 = rng.choice([Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE])
        hole = [Card(r1, s), Card(r2, s)]
        board = _pick_board(rng, hole, 2, suits=[s]) + _pick_board(
            rng, hole, 1, suits=[x for x in Suit if x != s])
    else:
        # OESD: connected hand + two connecting board cards.
        lo = rng.choice([Rank.SEVEN, Rank.EIGHT, Rank.NINE])
        hole = [Card(lo, Suit.SPADES), Card(Rank(lo.value + 1), Suit.HEARTS)]
        mid = rng.choice([Rank.THREE, Rank.FOUR, Rank.FIVE])
        board = [Card(mid, Suit.DIAMONDS),
                 Card(Rank(mid.value + 1), Suit.CLUBS),
                 Card(Rank(mid.value + 2), Suit.SPADES)]
    # Sanity: must actually be a draw (not a made flush/straight).
    outs = _draw_outs(hole, board)
    if outs < 8:
        return None
    pot = rng.choice([60, 80, 100])
    bet = int(pot * rng.choice([0.5, 0.66, 0.75]))
    return dict(
        phase="FLOP", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=bet, stack=200,
        hero_current_bet=0,
    )


def build_turn_draw_call(rng: random.Random) -> dict[str, Any] | None:
    """Turn flush draw vs a bet → CALL on (slightly worse) price."""
    s = rng.choice(list(Suit))
    r1 = rng.choice([Rank.ACE, Rank.KING, Rank.QUEEN])
    r2 = rng.choice([Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE])
    hole = [Card(r1, s), Card(r2, s)]
    board = _pick_board(rng, hole, 2, suits=[s]) + _pick_board(
        rng, hole, 2, suits=[x for x in Suit if x != s])
    if _draw_outs(hole, board) < 8:
        return None
    pot = rng.choice([100, 120, 150])
    bet = int(pot * rng.choice([0.4, 0.5]))
    return dict(
        phase="TURN", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=bet, stack=180,
        hero_current_bet=0,
    )


def build_flop_semi_bluff(rng: random.Random) -> dict[str, Any] | None:
    """Strong draw, unopened pot → BET (semi-bluff)."""
    # OESD: hole 7,8 with a board of 5,6,X — the 4 and 9 are the outs.
    # The two board cards sit just under the connectors so the hole
    # cards are the middle of a 5-card straight run (never already
    # made).  The third card is a random high card (never a 9-ish or a
    # pair) that keeps the board unpaired/un-flushed.
    lo = rng.choice([Rank.SEVEN, Rank.EIGHT, Rank.NINE])
    s = rng.choice(list(Suit))
    hole = [Card(lo, s), Card(Rank(lo.value + 1), s)]
    b_suit = rng.choice([x for x in Suit if x != s])
    used = {(c.rank.value, c.suit.value) for c in hole}
    third_ranks = [r for r in (Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE)]
    while True:
        t3 = rng.choice(third_ranks)
        t3s = rng.choice([x for x in Suit if x != s and x != b_suit])
        if (t3.value, t3s.value) not in used:
            break
    board = [Card(Rank(lo.value - 2), b_suit),
             Card(Rank(lo.value - 1), rng.choice(
                 [x for x in Suit if x not in (s, b_suit, t3s)])),
             Card(t3, t3s)]
    # Sanity: must be a genuine open-ended straight draw (8 outs).
    if _draw_outs(hole, board) < 8:
        return None
    pot = rng.choice([40, 60, 80, 100])
    seat = rng.choice([0, 1])  # vary who is out of position
    return dict(
        phase="FLOP", player_seat=seat, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=0, stack=200,
        hero_current_bet=0,
    )


def build_river_value_bet(rng: random.Random) -> dict[str, Any] | None:
    """River two-pair+, opponent checks → BET for value."""
    hi = rng.choice([Rank.KING, Rank.QUEEN])
    lo = rng.choice([Rank.NINE, Rank.TEN, Rank.JACK])
    if lo.value >= hi.value:
        return None
    hole = [Card(hi, Suit.SPADES), Card(lo, Suit.HEARTS)]
    board = [Card(hi, Suit.DIAMONDS), Card(lo, Suit.CLUBS)]
    used = {(c.rank.value, c.suit.value) for c in hole + board}
    deck = [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in used and r.value not in (hi.value, lo.value, 14)]
    rng.shuffle(deck)
    # Three more board cards, drawn so the board stays unpaired and never
    # makes a 4-straight — a paired/coordinated board would weaken the
    # "two pair for value" premise (or counterfeit it).
    for _ in range(3):
        for c in deck:
            if c.rank.value in (r.rank.value for r in board):
                continue
            ranks = [b.rank.value for b in board] + [c.rank.value]
            ranks.sort()
            if any(b - a <= 2 and b - a >= 1 for a, b in zip(ranks, ranks[1:])):
                # allow one adjacency but not three in a row
                runs = 1
                best = 1
                for a, b in zip(ranks, ranks[1:]):
                    if b - a == 1:
                        runs += 1
                        best = max(best, runs)
                    else:
                        runs = 1
                if best >= 4:
                    continue
            board.append(c)
            deck.remove(c)
            break
        else:
            return None  # couldn't find a clean card
    pot = rng.choice([80, 100, 120])
    return dict(
        phase="RIVER", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=0, stack=200,
        hero_current_bet=0,
    )


def build_river_bluff(rng: random.Random) -> dict[str, Any] | None:
    """River with a missed draw / no showdown value → BET as a bluff."""
    lo = rng.choice([Rank.SEVEN, Rank.EIGHT])
    s = rng.choice(list(Suit))
    hole = [Card(lo, s), Card(Rank(lo.value + 1), s)]
    # Board deliberately misses the draw: an unpaired, unflushed board
    # whose ranks never make our connectors a pair or a straight, but
    # which still looks bluffable (a couple of connected-looking ranks).
    used = {(c.rank.value, c.suit.value) for c in hole}
    # Exclude ranks that would pair or straighten our connectors.
    excluded = {lo.value, lo.value + 1, lo.value - 1, lo.value + 2}
    deck = [Card(r, s2) for r in Rank for s2 in Suit
            if (r.value, s2.value) not in used
            and r.value not in excluded and r.value not in (lo.value,)]
    rng.shuffle(deck)
    board = deck[:5]
    # Sanity: must have missed — a pair would push strength to ~0.45
    # (one-pair baseline), so anything below 0.25 is a bare high card.
    if _made_hand_strength(hole, board) > 0.25:
        return None
    # Ensure at least a couple of connected ranks for bluff credibility.
    board_ranks = sorted(c.rank.value for c in board)
    if not any(b - a <= 2 for a, b in zip(board_ranks, board_ranks[1:])):
        return None
    pot = rng.choice([80, 100, 120])
    return dict(
        phase="RIVER", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=0, stack=200,
        hero_current_bet=0,
    )


def build_river_call_or_fold(rng: random.Random) -> dict[str, Any] | None:
    """River bluff-catcher facing a bet → CALL or FOLD by hand strength."""
    # Weak-ish one-pair bluff catcher: a middle pair plus an ace kicker.
    r = rng.choice([Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN])
    s1 = rng.choice(list(Suit))
    s2 = rng.choice([s for s in Suit if s != s1])
    hole = [Card(r, s1), Card(Rank.ACE, s2)]
    # Board pairs our card + an A + three blanks below our pair (no
    # 4-straight, no flush), so we hold a mediocre made hand.
    b_suit = rng.choice([x for x in Suit if x != s1 and x != s2])
    used = {(c.rank.value, c.suit.value) for c in hole}
    deck = [Card(rk, su) for rk in Rank for su in Suit
            if (rk.value, su.value) not in used
            and rk.value not in (r.value, 14, 13, 12, 11)]
    rng.shuffle(deck)
    board = [Card(r, b_suit), Card(Rank.ACE, b_suit)] + deck[:3]
    # Stack comfortably covers the call so GTOBot never shoves.
    pot = rng.choice([120, 150, 180])
    bet = int(pot * rng.choice([0.4, 0.5]))
    return dict(
        phase="RIVER", player_seat=0, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=bet, stack=400,
        hero_current_bet=0,
    )


def build_bb_ace_high(rng: random.Random) -> dict[str, Any] | None:
    """BB defends, flop A-high vs a bet → CALL/FOLD."""
    kicker = rng.choice([Rank.FIVE, Rank.SIX, Rank.SEVEN, Rank.EIGHT, Rank.NINE])
    a_suit = rng.choice(list(Suit))
    k_suit = rng.choice([s for s in Suit if s != a_suit])
    hole = [Card(Rank.ACE, a_suit), Card(kicker, k_suit)]
    # Board pairs the A + two blanks, no flush/straight, so A-high is TPTK-ish.
    board = [Card(Rank.ACE, k_suit)]
    used = {(c.rank.value, c.suit.value) for c in hole + board}
    deck = [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in used and r.value not in (14, 13, 12, 11, 10)]
    rng.shuffle(deck)
    board += deck[:2]
    pot = rng.choice([30, 40, 50])
    bet = int(pot * rng.choice([0.4, 0.5]))
    return dict(
        phase="FLOP", player_seat=1, hole=[str(c) for c in hole],
        board=[str(c) for c in board], pot=pot,
        dealer=0, sb=0, bb=1, current_bet=bet, stack=180,
        hero_current_bet=0,
    )


def build_btn_steal(rng: random.Random) -> dict[str, Any] | None:
    """BTN with a stealable hand, everyone folded → RAISE."""
    hole: list[Card] | None = None
    choice = rng.random()
    if choice < 0.4:
        r1 = rng.choice([Rank.ACE, Rank.KING])
        r2 = rng.choice([Rank.TWO, Rank.THREE, Rank.FOUR])
        hole = _two_offsuit(rng, r1, r2)
    elif choice < 0.7:
        lo = rng.choice([Rank.SIX, Rank.SEVEN, Rank.EIGHT])
        s = rng.choice(list(Suit))
        hole = [Card(lo, s), Card(Rank(lo.value + 1), s)]
    else:
        r = rng.choice([Rank.SEVEN, Rank.EIGHT, Rank.NINE])
        s1 = rng.choice(list(Suit))
        s2 = rng.choice([x for x in Suit if x != s1])
        hole = [Card(r, s1), Card(r, s2)]
    if hole is None:
        return None
    return dict(
        phase="PREFLOP", player_seat=5, hole=[str(c) for c in hole],
        board=[], pot=rng.choice([15, 15, 20]), dealer=5, sb=0, bb=1,
        current_bet=10, stack=200,
        hero_current_bet=None,
    )


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: list[Template] = [
    Template("preflop-open-fold", ScenarioCategory.PREFLOP_RANGE, 2,
             {"FOLD", "RAISE"}, ["CALL"],
             build_preflop_open_fold,
             title_tpl="翻前 {pos} 边缘手牌",
             desc_tpl="你在 {pos} 位置拿到 {hole}，前序无人行动，你该怎么办？",
             # Edge hands like KJo/QJo are GTO-mixed from early position —
             # the bot may raise or fold, and either is the reference.
             hints=["边缘手牌在早期位置是负 EV", "紧的范围是赢钱的关键"]),
    Template("preflop-open-raise", ScenarioCategory.PREFLOP_RANGE, 1,
             {"RAISE"}, ["CALL", "FOLD"],
             build_preflop_open_raise,
             title_tpl="翻前 {pos} 强牌",
             desc_tpl="你在 {pos} 位置拿到 {hole}，前序弃牌到你",
             hints=["顶级手牌在位置应该加注", "加注建立底池并隔离弱手"]),
    Template("preflop-bb-defend", ScenarioCategory.PREFLOP_RANGE, 3,
             {"CALL"}, ["FOLD", "RAISE"],
             build_preflop_bb_defend,
             title_tpl="翻前 BB 防御",
             desc_tpl="你在 BB 面对 BTN 加注，手里是 {hole}",
             hints=["大盲位置可以放宽防守范围", "suited 牌比 offsuit 更适合防御"]),
    Template("flop-tptk-bet", ScenarioCategory.POSTFLOP_VALUE, 3,
             {"CALL", "RAISE"}, ["FOLD"],
             build_flop_tptk_bet,
             title_tpl="翻后顶对面对下注",
             desc_tpl="你击中顶对顶踢，对手下注",
             hints=["顶对顶踢有很好的摊牌价值", "跟注控制底池，保留对手诈唬空间"]),
    Template("flop-overpair-bet", ScenarioCategory.POSTFLOP_VALUE, 1,
             {"BET"}, ["CHECK"],
             build_flop_overpair_bet,
             title_tpl="翻牌超对价值下注",
             desc_tpl="你翻前加注，翻牌拿着超对 {hole}",
             hints=["超对在翻牌是价值牌，必须主动下注", "持续下注约 1/2 底池"]),
    Template("flop-two-pair", ScenarioCategory.POSTFLOP_VALUE, 2,
             {"RAISE"}, ["CALL"],
             build_flop_two_pair,
             title_tpl="翻牌两对加注打价值",
             desc_tpl="你击中两对，底池已有下注",
             hints=["两对在翻牌是强牌，应尽快建立底池", "价值加注从被反超的范围赚取"]),
    Template("flop-draw-call", ScenarioCategory.POT_ODDS, 2,
             {"CALL"}, ["FOLD", "RAISE"],
             build_flop_draw_call,
             title_tpl="翻牌听牌跟注",
             desc_tpl="你在翻牌有听牌，对手下注",
             hints=["计算底池赔率决定跟注", "同花听牌约 36% 胜率，顺子听牌约 32%"]),
    Template("turn-draw-call", ScenarioCategory.POT_ODDS, 3,
             {"CALL"}, ["FOLD"],
             build_turn_draw_call,
             title_tpl="转牌听牌跟注",
             desc_tpl="你在转牌有同花听牌，对手下注",
             hints=["转牌只剩一张牌，听牌胜率减半", "赔率不足时弃牌是正确选择"]),
    Template("flop-semi-bluff", ScenarioCategory.BLUFFING, 3,
             {"BET", "RAISE"}, ["CHECK", "CALL"],
             build_flop_semi_bluff,
             title_tpl="翻牌半诈唬",
             desc_tpl="你拿着强听牌，对手过牌",
             hints=["半诈唬是教科书打法：落后但有充足赢率", "下注同时赚取弃牌收益和实现权益"]),
    Template("river-value-bet", ScenarioCategory.RIVER_DECISION, 2,
             {"BET"}, ["CHECK"],
             build_river_value_bet,
             title_tpl="河牌价值下注",
             desc_tpl="你在河牌拿到两对以上，对手过牌",
             hints=["强牌在河牌必须价值下注", "对手过牌通常意味着较弱范围"]),
    Template("river-bluff", ScenarioCategory.RIVER_DECISION, 4,
             {"BET"}, ["CHECK", "FOLD"],
             build_river_bluff,
             title_tpl="河牌诈唬",
             desc_tpl="你在河牌没有摊牌价值，对手过牌",
             hints=["没有摊牌价值只能靠下注取胜", "选择对手弃牌率高的牌面诈唬"],
             # GTOBot never bets a bare high card on the river — it only
             # value-bets or semi-bluffs.  A river bluff is a real spot,
             # so fix the reference to a 2/3-pot bet.
             fixed_reference=lambda gs, seat: (
                 "BET", max(int(gs.pot.main_pot * 2 / 3), gs.big_blind))),
    Template("river-call-or-fold", ScenarioCategory.RIVER_DECISION, 4,
             {"CALL", "FOLD"}, ["RAISE"],
             build_river_call_or_fold,
             title_tpl="河牌抓诈唬",
             desc_tpl="你在河牌是中等牌力，面对对手下注",
             hints=["中等牌力面对下注：要么抓诈唬跟注，要么弃牌", "加注只会被更强牌跟注"]),
    Template("bb-ace-high", ScenarioCategory.POSITION, 3,
             {"CALL", "FOLD"}, ["RAISE"],
             build_bb_ace_high,
             title_tpl="大盲位 A 高牌翻后",
             desc_tpl="你在 BB 用 A 高牌补盲进池，翻牌 A72，对手下注",
             hints=["A 高顶对在干燥牌面有摊牌价值", "跟注控制底池，加注打走你赢的范围"]),
    Template("btn-steal", ScenarioCategory.POSITION, 1,
             {"RAISE"}, ["FOLD", "CALL"],
             build_btn_steal,
             title_tpl="BTN 偷盲",
             desc_tpl="你在 BTN，前面弃牌到你，手牌 {hole}",
             hints=["BTN 是全场最好位置，施加最大压力", "偷盲加注通常 2.5BB"]),
]


# ---------------------------------------------------------------------------
# Quality filter
# ---------------------------------------------------------------------------


def _reference_action(gs: GameState, seat: int) -> tuple[str, int]:
    bot = GTOBot()
    act = bot.decide(gs, seat)
    return act.type.name, act.amount


def _scenario_for(
    spec: dict[str, Any], tpl: Template, idx: int,
) -> Scenario | None:
    """Build a Scenario from a spec, or None if it fails quality checks."""
    gs = state_from_spec(spec)
    seat = spec["player_seat"]
    if tpl.fixed_reference is not None:
        if callable(tpl.fixed_reference):
            ref_type, ref_amount = tpl.fixed_reference(gs, seat)
        else:
            ref_type, ref_amount = tpl.fixed_reference
    else:
        ref_type, ref_amount = _reference_action(gs, seat)

    # 1. Reference action must be one of the template's allowed answers.
    if ref_type not in tpl.allowed_actions:
        return None

    # 2. Template-specific board predicate.
    if tpl.check is not None and not tpl.check(gs):
        return None

    # 3. The optimal answer must score near-perfect in the scorer.
    # Preflop spots have no board — skip the made-hand strength there.
    hole_cards = [_card(c) for c in spec["hole"]]
    board_cards = [_card(c) for c in spec["board"]]
    equity = (round(_made_hand_strength(hole_cards, board_cards), 2)
              if len(hole_cards) + len(board_cards) >= 5 else 0.5)
    # The reference action is the fully-correct answer; the template's
    # alternative actions get partial credit (a "close but suboptimal"
    # decision isn't a 0).  The non-triviality check below guarantees the
    # gap between optimal and alt stays meaningful.
    acceptable_range = {ref_type: [0.6, 1.0]}
    for alt in tpl.alt_actions:
        if alt != ref_type:
            acceptable_range[alt] = [0.15, 0.35]
    scenario = Scenario(
        id=f"gen-{idx:04d}",
        title=tpl.title_tpl.format(pos=_seat_label(seat), hole=_hole_label(spec["hole"])),
        description=tpl.desc_tpl.format(pos=_seat_label(seat), hole=_hole_label(spec["hole"])),
        category=tpl.category,
        difficulty=tpl.difficulty,
        optimal_action={"type": ref_type, "amount": ref_amount},
        acceptable_range=acceptable_range,
        hints=tpl.hints,
        analysis={"equity_vs_range": equity},
        frozen_state=gs,
        player_seat=seat,
    )
    best = score_decision(scenario, {"type": ref_type, "amount": ref_amount})
    if best.total < 90:
        return None

    # 4. Non-trivial: some other allowed action must differ meaningfully.
    others = [a for a in tpl.allowed_actions if a != ref_type]
    for alt in tpl.alt_actions:
        if alt == ref_type:
            continue
        alt_score = score_decision(
            scenario,
            {"type": alt, "amount": _alt_amount(alt, ref_type, ref_amount, spec, gs)},
        )
        if best.total - alt_score.total < 15:
            return None
    return scenario


def _alt_amount(alt: str, ref: str, ref_amount: int,
                spec: dict[str, Any], gs: GameState) -> int:
    """A plausible amount for the alternative action."""
    if alt in ("FOLD", "CHECK"):
        return 0
    if alt in ("CALL",):
        return max(0, gs.current_bet - gs.player(spec["player_seat"]).current_bet)
    if alt == "RAISE":
        return gs.current_bet * 3 or gs.big_blind * 3
    if alt == "BET":
        return int(gs.pot.main_pot * 0.66)
    return 0


def _seat_label(seat: int) -> str:
    return {5: "BTN", 6: "CO", 4: "MP", 3: "UTG"}.get(seat, f"{seat} 号位")


def _hole_label(hole: list[str]) -> str:
    return "".join(hole)


# ---------------------------------------------------------------------------
# Generator entry point
# ---------------------------------------------------------------------------


def generate_library(
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
) -> list[Scenario]:
    """Generate *target* scenarios (deterministic for a given seed).

    Splits the target evenly across templates so no category starves,
    then per-template: build/accept in a loop until its quota is met or
    its attempt budget is exhausted.  Deterministic for a fixed seed.
    """
    rng = random.Random(seed)
    accepted: list[Scenario] = []
    seen: set[tuple] = set()
    idx = 1

    # Per-template quota: spread the target across the templates, never
    # below 1; the remainder is handed to the first templates so the
    # total lands on the requested *target* (14×35=490, remainder 10 →
    # first 10 templates get 36).  Balances categories since each has
    # 2–3 templates.
    n_templates = len(_TEMPLATES)
    quota = max(1, target // n_templates)
    remainder = target - quota * n_templates
    quota_extra = {t.key: (1 if i < remainder else 0)
                   for i, t in enumerate(_TEMPLATES)}
    per_tpl: dict[str, int] = {t.key: 0 for t in _TEMPLATES}
    attempts = {t.key: 0 for t in _TEMPLATES}

    # 400 attempts per quota slot — low-yield templates (river bluff)
    # may need many retries, high-yield ones fill fast.
    tpl_quota = lambda t: quota + quota_extra[t.key]
    max_attempts = max(tpl_quota(t) for t in _TEMPLATES) * 400

    for tpl in _TEMPLATES:
        q = tpl_quota(tpl)
        while per_tpl[tpl.key] < q and attempts[tpl.key] < max_attempts:
            attempts[tpl.key] += 1
            idx += 1
            spec = tpl.build(rng)
            if spec is None:
                continue
            key = (tpl.key, tuple(spec["hole"]), tuple(spec["board"]),
                   spec["phase"], spec["current_bet"])
            if key in seen:
                continue
            seen.add(key)
            scenario = _scenario_for(spec, tpl, idx)
            if scenario is None:
                continue
            accepted.append(scenario)
            per_tpl[tpl.key] += 1

    # Sort for a stable output order.
    accepted.sort(key=lambda s: (s.category.value, s.id))
    return accepted


def write_yaml(scenarios: list[Scenario], data_dir: str | Path,
               files: int = 5) -> int:
    """Write *scenarios* as YAML lists split across *files* files."""
    import yaml
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    # Clear any stale generated files first.
    for old in data_dir.glob("scenarios_*.yaml"):
        old.unlink()
    per = (len(scenarios) + files - 1) // files
    n = 0
    for i in range(0, len(scenarios), per):
        chunk = scenarios[i:i + per]
        if not chunk:
            continue
        path = data_dir / f"scenarios_{i // per:03d}.yaml"
        payload = [_scenario_to_dict(s) for s in chunk]
        with open(path, "w") as f:
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
        n += len(chunk)
    return n


def _scenario_to_dict(s: Scenario) -> dict[str, Any]:
    gs = s.frozen_state
    return {
        "id": s.id,
        "title": s.title,
        "description": s.description,
        "category": s.category.value,
        "difficulty": s.difficulty,
        "optimal_action": s.optimal_action,
        "acceptable_range": s.acceptable_range,
        "hints": s.hints,
        "analysis": s.analysis,
        "player_seat": s.player_seat,
        "frozen_state": _state_spec(gs, s.player_seat),
    }


def _state_spec(gs: GameState, player_seat: int) -> dict[str, Any]:
    """Reverse of ``state_from_spec`` — the GameState back to plain data."""
    return {
        "phase": gs.phase.name,
        "player_seat": player_seat,
        "hole": [str(c) for c in gs.player(player_seat).hole_cards],
        "board": [str(c) for c in gs.community_cards],
        "pot": gs.pot.main_pot,
        "dealer": gs.dealer_idx,
        "sb": gs.sb_seat,
        "bb": gs.bb_seat,
        "current_bet": gs.current_bet,
        "stack": gs.player(player_seat).stack,
        "hero_current_bet": gs.player(player_seat).current_bet,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate bulk training scenarios")
    parser.add_argument("--count", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--dry-run", action="store_true",
                        help="print category stats without writing files")
    parser.add_argument("--out", default=None,
                        help="output dir (default: the packaged data/scenarios)")
    args = parser.parse_args()

    from collections import Counter
    scenarios = generate_library(target=args.count, seed=args.seed)
    counts = Counter(s.category.value for s in scenarios)
    print(f"generated {len(scenarios)} scenarios:")
    for cat, n in sorted(counts.items()):
        print(f"  {cat:<18} {n}")

    if args.dry_run:
        return
    out = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent.parent / "data" / "scenarios")
    written = write_yaml(scenarios, out)
    print(f"wrote {written} scenarios to {out}")


if __name__ == "__main__":
    main()
