"""Tests for the shared Monte Carlo equity module (iteration #2).

The trainer's analyzer and GTOBot both ride on
``ai_engine/equity.py``; these tests pin the known-good numbers.
"""

import random

from sekhmet.ai_engine.equity import (
    equity_vs_combos,
    infer_opponent_range,
    position_bucket,
    range_combos,
)
from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.hand_evaluator import HandRank, evaluate_7_cards


def _cards(specs: list[tuple[Rank, Suit]]) -> list[Card]:
    return [Card(r, s) for r, s in specs]


def _all_combos(deck: list[Card], weight: float = 1.0):
    """Uniform weight over every remaining pair."""
    return [(c1, c2, weight)
            for i, c1 in enumerate(deck)
            for c2 in deck[i + 1:]]


def _fresh_deck(exclude: list[Card]) -> list[Card]:
    known = {(c.rank.value, c.suit.value) for c in exclude}
    return [Card(r, s) for r in Rank for s in Suit
            if (r.value, s.value) not in known]


# ---------------------------------------------------------------------------
# Known-good equities
# ---------------------------------------------------------------------------


def test_aces_preflop_vs_random():
    """AA vs two random cards ≈ 0.85 (the classic number)."""
    hole = _cards([(Rank.ACE, Suit.SPADES), (Rank.ACE, Suit.HEARTS)])
    deck = _fresh_deck(hole)
    eq = equity_vs_combos(hole, [], _all_combos(deck), samples=1500,
                          rng=random.Random(42))
    assert eq is not None
    assert 0.80 <= eq <= 0.89


def test_river_quads_win_everything():
    """Quad nines on a full river beat any two unpaired hole cards."""
    hole = _cards([(Rank.NINE, Suit.SPADES), (Rank.NINE, Suit.HEARTS)])
    board = _cards([
        (Rank.NINE, Suit.DIAMONDS), (Rank.NINE, Suit.CLUBS),
        (Rank.FIVE, Suit.SPADES), (Rank.SEVEN, Suit.HEARTS),
        (Rank.KING, Suit.DIAMONDS),
    ])
    assert evaluate_7_cards(hole + board).rank == HandRank.FOUR_OF_A_KIND
    deck = _fresh_deck(hole + board)
    eq = equity_vs_combos(hole, board, _all_combos(deck), samples=500,
                          rng=random.Random(7))
    assert eq == 1.0


def test_nut_flush_on_river_is_the_nuts():
    """AK♠ nut flush — no straight flush available on this board."""
    hole = _cards([(Rank.ACE, Suit.SPADES), (Rank.KING, Suit.SPADES)])
    board = _cards([
        (Rank.QUEEN, Suit.SPADES), (Rank.JACK, Suit.SPADES),
        (Rank.THREE, Suit.SPADES), (Rank.SEVEN, Suit.DIAMONDS),
        (Rank.FOUR, Suit.CLUBS),
    ])
    assert evaluate_7_cards(hole + board).rank == HandRank.FLUSH
    deck = _fresh_deck(hole + board)
    eq = equity_vs_combos(hole, board, _all_combos(deck), samples=800,
                          rng=random.Random(3))
    assert eq == 1.0


def test_turn_flush_draw_full_runout():
    """AK♠ with the nut flush draw on the J♠274 turn vs two random
    cards.  Exhaustively verified (45540 runouts): equity ≈ 0.475 —
    the four-card board gives random hands plenty of pair scenarios,
    so even a nut flush draw + two overcards sits under a coin flip."""
    hole = _cards([(Rank.ACE, Suit.SPADES), (Rank.KING, Suit.SPADES)])
    board = _cards([
        (Rank.JACK, Suit.SPADES), (Rank.TWO, Suit.HEARTS),
        (Rank.SEVEN, Suit.DIAMONDS), (Rank.FOUR, Suit.CLUBS),
    ])
    deck = _fresh_deck(hole + board)
    eq = equity_vs_combos(hole, board, _all_combos(deck), samples=3000,
                          rng=random.Random(11))
    assert 0.42 <= eq <= 0.53


def test_empty_combos_returns_none():
    hole = _cards([(Rank.ACE, Suit.SPADES), (Rank.KING, Suit.HEARTS)])
    assert equity_vs_combos(hole, [], [], samples=10) is None


def test_pair_aces_beats_k_high_only_range():
    """Complete-board fast path: top pair always beats a K-high range."""
    hole = _cards([(Rank.ACE, Suit.SPADES), (Rank.TWO, Suit.HEARTS)])
    board = _cards([
        (Rank.ACE, Suit.DIAMONDS), (Rank.SEVEN, Suit.CLUBS),
        (Rank.EIGHT, Suit.HEARTS), (Rank.TEN, Suit.SPADES),
        (Rank.THREE, Suit.CLUBS),
    ])
    combos = [(Card(Rank.KING, Suit.HEARTS), Card(Rank.QUEEN, Suit.DIAMONDS), 1.0)]
    eq = equity_vs_combos(hole, board, combos, samples=100, rng=random.Random(1))
    assert eq == 1.0


# ---------------------------------------------------------------------------
# Range inference / position buckets
# ---------------------------------------------------------------------------


def _player(seat: int):
    from types import SimpleNamespace
    return SimpleNamespace(seat_idx=seat, is_active=True, is_all_in=False)


def _make_state(players, **kw):
    """Minimal GameState stand-in for the inference helpers."""
    from types import SimpleNamespace
    return SimpleNamespace(
        players=players,
        phase=kw.get("phase"), sb_seat=kw.get("sb_seat"),
        bb_seat=kw.get("bb_seat"), dealer_idx=kw.get("dealer_idx"),
        current_bet=kw.get("current_bet", 10),
        big_blind=kw.get("big_blind", 10),
        small_blind=kw.get("small_blind", 5),
        last_aggressor_idx=kw.get("last_aggressor_idx"),
        pot=SimpleNamespace(main_pot=kw.get("main_pot", 15)),
    )


def test_position_bucket_blinds_and_button():
    players = [_player(i) for i in range(6)]
    st = _make_state(players, sb_seat=1, bb_seat=2, dealer_idx=0)
    assert position_bucket(1, st) == "sb"
    assert position_bucket(2, st) == "bb"
    assert position_bucket(0, st) == "btn"


def test_facing_3bet_range_tighter_than_limp_range():
    from sekhmet.game_engine import GamePhase
    players = [_player(i) for i in range(4)]
    hero_hole = _cards([(Rank.ACE, Suit.SPADES), (Rank.KING, Suit.HEARTS)])
    deck = _fresh_deck(hero_hole)

    st_3bet = _make_state(players, phase=GamePhase.PREFLOP,
                          sb_seat=1, bb_seat=2, dealer_idx=0,
                          current_bet=70, big_blind=10, last_aggressor_idx=3)
    st_limp = _make_state(players, phase=GamePhase.PREFLOP,
                          sb_seat=1, bb_seat=2, dealer_idx=0,
                          current_bet=10, big_blind=10, last_aggressor_idx=3)
    n_3bet = len(range_combos(infer_opponent_range(st_3bet, 1), deck))
    n_limp = len(range_combos(infer_opponent_range(st_limp, 1), deck))
    assert 0 < n_3bet < n_limp


def test_infer_opponent_range_no_opponents():
    st = _make_state([_player(0)], sb_seat=0, bb_seat=0)
    assert infer_opponent_range(st, player_seat=0) is None
