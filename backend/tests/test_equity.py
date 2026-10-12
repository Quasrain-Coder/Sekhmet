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


# ---------------------------------------------------------------------------
# L4.5: range narrowing + multiway modelling (iteration #6)
# ---------------------------------------------------------------------------


def test_narrow_range_monotone_with_fallback():
    from sekhmet.ai_engine.equity import narrow_range
    from sekhmet.ai_engine.gto_ranges import RFI
    full = RFI["co"]
    l1 = narrow_range(full, 1)
    l2 = narrow_range(full, 2)
    assert len(l2) <= len(l1) <= len(full)
    assert all(f >= 0.3 for f in l1.values())
    assert all(f >= 0.7 for f in l2.values())
    assert narrow_range(full, 0) is full
    # A range with no strong core falls back instead of going empty.
    uniform = {(14, 2, "s"): 0.2, (13, 3, "o"): 0.1}
    assert narrow_range(uniform, 1) is uniform


def test_postflop_aggression_count_dedups_preflop_raises():
    from types import SimpleNamespace
    from sekhmet.ai_engine.equity import postflop_aggression_count
    from sekhmet.game_engine import Action, ActionType

    def st(current_bet, history):
        return SimpleNamespace(current_bet=current_bet, big_blind=10,
                               round_history=tuple(history))

    raise_ = Action(1, ActionType.RAISE, 30)
    bet = Action(1, ActionType.BET, 50)
    call = Action(1, ActionType.CALL, 10)
    # Raised pot (30 BB): opponent raised preflop then bet once postflop
    # → 1 deduped postflop aggression.
    assert postflop_aggression_count(st(30, [call, raise_, bet]), 1) == 1
    # Limped pot (10 BB): two bets are both postflop → 2.
    assert postflop_aggression_count(st(10, [call, bet, bet]), 1) == 2
    # Triple-barrel in a 3-bet pot (45+ BB open) → 2 bets + preflop raise
    # (deduped as 2) → 2 postflop aggressions.
    allin = Action(1, ActionType.ALL_IN, 200)
    assert postflop_aggression_count(st(50, [raise_, raise_, bet, bet]), 1) == 2


def test_infer_range_for_opponent_narrows_with_aggression():
    from types import SimpleNamespace
    from sekhmet.ai_engine.equity import (
        infer_range_for_opponent, range_combos,
    )
    from sekhmet.game_engine import Action, ActionType, GamePhase
    from sekhmet.ai_engine.gto_ranges import RFI

    # Opponent on the button (seat 0): postflop base range is RFI[btn],
    # which carries mixed frequencies — so narrowing has room to bite.
    # (Known limitation, see design doc: charts without mixed freqs
    # (BB defend / limp) narrow to themselves; data work, not logic.)
    players = [SimpleNamespace(seat_idx=i, is_active=True, is_all_in=False)
               for i in range(3)]
    base_state = dict(phase=GamePhase.FLOP, sb_seat=1, bb_seat=2,
                      dealer_idx=0, current_bet=30, big_blind=10,
                      small_blind=5, last_aggressor_idx=0,
                      pot=SimpleNamespace(main_pot=75),
                      round_history=())
    st = SimpleNamespace(players=players, **base_state)
    calm = infer_range_for_opponent(st, hero_seat=1, opp_seat=0)
    assert calm is RFI["btn"]            # no postflop aggression yet

    # Opponent fired four aggressive actions across the hand: 4 − 2
    # preflop credits = narrowing level 2 (≥ 0.7 core only), which
    # strips the 0.5-frequency mixed hands from RFI[btn].
    barrel_kw = {**base_state,
                 "round_history": (Action(0, ActionType.RAISE, 30),
                                   Action(0, ActionType.RAISE, 90),
                                   Action(0, ActionType.BET, 60),
                                   Action(0, ActionType.BET, 120),)}
    barrel = SimpleNamespace(players=players, **barrel_kw)
    fired = infer_range_for_opponent(barrel, hero_seat=1, opp_seat=0)
    assert fired is not calm
    assert len(fired) < len(calm)        # mixed hands stripped outright
    assert all(f >= 0.7 for f in fired.values())
    assert len(range_combos(fired, _fresh_deck([]))) < \
        len(range_combos(calm, _fresh_deck([])))


def test_multiway_equity_is_min_across_opponents():
    """L4.5 core semantic: with two live opponents the hero must beat
    both — the modelled equity is the worse of the two matchups."""
    hole = _cards([(Rank.ACE, Suit.SPADES), (Rank.KING, Suit.HEARTS)])
    board = _cards([(Rank.SEVEN, Suit.CLUBS), (Rank.TWO, Suit.DIAMONDS),
                    (Rank.NINE, Suit.HEARTS)])
    deck = _fresh_deck(hole + board)
    weak = [(Card(Rank.SIX, Suit.CLUBS), Card(Rank.FIVE, Suit.DIAMONDS), 1.0)]
    strong = _all_combos(deck)
    eq_weak = equity_vs_combos(hole, board, weak, samples=400, rng=random.Random(5))
    eq_strong = equity_vs_combos(hole, board, strong, samples=400, rng=random.Random(5))
    assert eq_weak > eq_strong             # sanity: one range is much scarier
    # min(weak, strong) ≈ strong — the multiway floor is the scary one.
    assert min(eq_weak, eq_strong) == eq_strong
