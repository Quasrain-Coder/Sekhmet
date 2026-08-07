"""Tests for hand_evaluator — the most critical module in the engine.

Coverage targets every HandRank variant, tie-breaking, and the 7→5
combination enumeration.
"""

import pytest
from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.hand_evaluator import (
    HandRank,
    HandScore,
    evaluate_5_cards,
    evaluate_7_cards,
)


# ---------------------------------------------------------------------------
# Helpers — build Card instances quickly
# ---------------------------------------------------------------------------

C = lambda r, s: Card(Rank(r), Suit(s))  # noqa: E731


def H(*ranks: int) -> list[Card]:
    """Build hearts with the given ranks."""
    return [C(r, Suit.HEARTS) for r in ranks]


def S(*ranks: int) -> list[Card]:
    """Build spades with the given ranks."""
    return [C(r, Suit.SPADES) for r in ranks]


def D(*ranks: int) -> list[Card]:
    """Build diamonds with the given ranks."""
    return [C(r, Suit.DIAMONDS) for r in ranks]


def CL(*ranks: int) -> list[Card]:
    """Build clubs with the given ranks."""
    return [C(r, Suit.CLUBS) for r in ranks]


# ---------------------------------------------------------------------------
# HandRank enum
# ---------------------------------------------------------------------------


def test_handrank_ordering():
    assert HandRank.HIGH_CARD < HandRank.ONE_PAIR
    assert HandRank.FULL_HOUSE < HandRank.FOUR_OF_A_KIND
    assert HandRank.STRAIGHT_FLUSH == 8
    assert max(HandRank) == HandRank.STRAIGHT_FLUSH


def test_handrank_describe():
    assert HandRank.STRAIGHT_FLUSH.describe() == "Straight Flush"
    assert HandRank.FULL_HOUSE.describe() == "Full House"
    assert HandRank.HIGH_CARD.describe() == "High Card"


# ---------------------------------------------------------------------------
# HandScore ordering
# ---------------------------------------------------------------------------


def test_handscore_ordering_by_rank():
    """A pair always beats high card regardless of kickers."""
    pair = HandScore(HandRank.ONE_PAIR, (2, 14, 13, 12))
    high = HandScore(HandRank.HIGH_CARD, (14, 13, 12, 11, 10))
    assert high < pair


def test_handscore_ordering_by_kickers_same_rank():
    """Same rank → kickers decide."""
    a = HandScore(HandRank.ONE_PAIR, (10, 14, 13, 12))  # TT AKQ
    b = HandScore(HandRank.ONE_PAIR, (10, 14, 13, 11))  # TT AKJ
    assert b < a


# ---------------------------------------------------------------------------
# evaluate_5_cards — error cases
# ---------------------------------------------------------------------------


def test_evaluate_5_wrong_count_raises():
    with pytest.raises(ValueError, match="exactly 5"):
        evaluate_5_cards(H(14, 13, 12, 11))


# ---------------------------------------------------------------------------
# evaluate_5_cards — High Card
# ---------------------------------------------------------------------------


def test_high_card():
    """A-K-Q-J-9 rainbow."""
    cards = H(14) + S(13) + D(12) + CL(11) + H(9)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.HIGH_CARD
    assert score.kickers == (14, 13, 12, 11, 9)
    assert "High Card, Ace" in score.describe()


# ---------------------------------------------------------------------------
# evaluate_5_cards — One Pair
# ---------------------------------------------------------------------------


def test_one_pair():
    """Pair of Aces, K-Q-J kickers."""
    cards = H(14) + S(14) + D(13) + CL(12) + H(11)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.ONE_PAIR
    assert score.kickers == (14, 13, 12, 11)
    assert "One Pair, Aces" in score.describe()


# ---------------------------------------------------------------------------
# evaluate_5_cards — Two Pair
# ---------------------------------------------------------------------------


def test_two_pair():
    """Aces and Kings, Queen kicker."""
    cards = H(14) + S(14) + D(13) + CL(13) + H(12)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.TWO_PAIR
    assert score.kickers == (14, 13, 12)
    assert "Two Pair, Aces and Kings" in score.describe()


# ---------------------------------------------------------------------------
# evaluate_5_cards — Three of a Kind
# ---------------------------------------------------------------------------


def test_three_of_a_kind():
    """Trip Aces, K-Q kickers."""
    cards = H(14) + S(14) + D(14) + CL(13) + H(12)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.THREE_OF_A_KIND
    assert score.kickers == (14, 13, 12)
    assert "Three of a Kind, Aces" in score.describe()


# ---------------------------------------------------------------------------
# evaluate_5_cards — Straight
# ---------------------------------------------------------------------------


def test_straight_broadway():
    """T-J-Q-K-A rainbow straight."""
    cards = H(10) + S(11) + D(12) + CL(13) + H(14)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.STRAIGHT
    assert score.kickers == (14,)
    assert "Straight, Ace high" in score.describe()


def test_straight_wheel():
    """A-2-3-4-5 wheel."""
    cards = H(14) + S(2) + D(3) + CL(4) + H(5)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.STRAIGHT
    assert score.kickers == (5,)  # 5-high
    assert "Straight, Five high" in score.describe()


def test_straight_nine_high():
    """5-6-7-8-9."""
    cards = H(5) + S(6) + D(7) + CL(8) + H(9)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.STRAIGHT
    assert score.kickers == (9,)


# ---------------------------------------------------------------------------
# evaluate_5_cards — Flush
# ---------------------------------------------------------------------------


def test_flush():
    """All hearts, not consecutive."""
    cards = H(14, 12, 10, 8, 6)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.FLUSH
    assert score.kickers == (14, 12, 10, 8, 6)
    assert "Flush, Ace high" in score.describe()


def test_flush_beats_straight():
    """Verify flush > straight in HandRank ordering."""
    flush = evaluate_5_cards(H(14, 12, 10, 8, 6))
    straight = evaluate_5_cards([C(Rank(10), Suit.HEARTS), C(Rank(11), Suit.SPADES),
                                  C(Rank(12), Suit.DIAMONDS), C(Rank(13), Suit.CLUBS),
                                  C(Rank(14), Suit.HEARTS)])
    assert straight < flush


# ---------------------------------------------------------------------------
# evaluate_5_cards — Full House
# ---------------------------------------------------------------------------


def test_full_house():
    """Aces full of Kings."""
    cards = H(14) + S(14) + D(14) + CL(13) + H(13)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.FULL_HOUSE
    assert score.kickers == (14, 13)
    assert "Full House, Aces over Kings" in score.describe()


def test_full_house_kicker_ordering():
    """Higher trips wins full house comparison."""
    aces_full = HandScore(HandRank.FULL_HOUSE, (14, 13))
    kings_full = HandScore(HandRank.FULL_HOUSE, (13, 14))
    assert kings_full < aces_full


# ---------------------------------------------------------------------------
# evaluate_5_cards — Four of a Kind
# ---------------------------------------------------------------------------


def test_four_of_a_kind():
    """Quad Aces, King kicker."""
    cards = H(14) + S(14) + D(14) + CL(14) + H(13)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.FOUR_OF_A_KIND
    assert score.kickers == (14, 13)
    assert "Four of a Kind, Aces" in score.describe()


# ---------------------------------------------------------------------------
# evaluate_5_cards — Straight Flush
# ---------------------------------------------------------------------------


def test_straight_flush():
    """9-10-J-Q-K all hearts."""
    cards = H(9, 10, 11, 12, 13)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.STRAIGHT_FLUSH
    assert score.kickers == (13,)
    assert "Straight Flush, King high" in score.describe()


def test_royal_flush():
    """10-J-Q-K-A all spades."""
    cards = S(10, 11, 12, 13, 14)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.STRAIGHT_FLUSH
    assert score.kickers == (14,)
    assert score.describe() == "Royal Flush"


def test_steel_wheel():
    """A-2-3-4-5 all hearts (a straight flush)."""
    cards = H(14, 2, 3, 4, 5)
    score = evaluate_5_cards(cards)
    assert score.rank == HandRank.STRAIGHT_FLUSH
    assert score.kickers == (5,)  # 5-high straight flush


# ---------------------------------------------------------------------------
# evaluate_7_cards — the 7→5 enumeration
# ---------------------------------------------------------------------------


def test_evaluate_7_chooses_best_5():
    """With 7 cards forming both a straight and a flush, picks the flush."""
    # Hearts: A, K, Q, J, 2 + clubs: 10, spades: 10  (has flush and straight)
    cards = H(14, 13, 12, 11, 2) + CL(10) + S(10)
    score = evaluate_7_cards(cards)
    # Flush wins over straight
    assert score.rank == HandRank.FLUSH
    assert score.kickers[:2] == (14, 13)


def test_evaluate_7_finds_straight_in_messy_hand():
    """7-K-2-5-J-10-A with three suits — should find J-10-A-K-... no, let's make it clearer."""
    # 5-6-7-8-9 straight hidden among 7 cards
    cards = H(5) + S(6) + D(7) + CL(8) + H(9) + H(14) + H(3)
    score = evaluate_7_cards(cards)
    assert score.rank == HandRank.STRAIGHT
    assert score.kickers == (9,)


def test_evaluate_7_finds_full_house():
    """Three Aces + two Kings + two random."""
    cards = H(14) + S(14) + D(14) + CL(13) + H(13) + S(2) + D(3)
    score = evaluate_7_cards(cards)
    assert score.rank == HandRank.FULL_HOUSE
    assert score.kickers == (14, 13)


def test_evaluate_7_finds_quads():
    """Four 7s + various."""
    cards = H(7) + S(7) + D(7) + CL(7) + H(14) + S(13) + D(2)
    score = evaluate_7_cards(cards)
    assert score.rank == HandRank.FOUR_OF_A_KIND
    assert score.kickers == (7, 14)


def test_evaluate_7_exactly_5_cards():
    """5 cards function as a fast path."""
    # mixed suits so it's not a flush
    cards = [C(14, Suit.HEARTS), C(14, Suit.SPADES), C(14, Suit.DIAMONDS),
             C(13, Suit.CLUBS), C(13, Suit.HEARTS)]
    score = evaluate_7_cards(cards)
    assert score.rank == HandRank.FULL_HOUSE


def test_evaluate_7_6_cards():
    """6-card input — mixed suits so it's two pair, not a flush."""
    cards = [C(14, Suit.HEARTS), C(14, Suit.SPADES),
             C(13, Suit.DIAMONDS), C(13, Suit.CLUBS),
             C(12, Suit.HEARTS), C(11, Suit.SPADES)]
    score = evaluate_7_cards(cards)
    assert score.rank == HandRank.TWO_PAIR
    assert score.kickers == (14, 13, 12)


# ---------------------------------------------------------------------------
# evaluate_7_cards — error cases
# ---------------------------------------------------------------------------


def test_evaluate_7_too_few_raises():
    with pytest.raises(ValueError, match="at least 5"):
        evaluate_7_cards(H(14, 13, 12, 11))


def test_evaluate_7_too_many_raises():
    with pytest.raises(ValueError, match="most 7"):
        evaluate_7_cards(H(14, 13, 12, 11, 10, 9, 8) + S(7))


# ---------------------------------------------------------------------------
# describe() — coverage for every HandRank
# ---------------------------------------------------------------------------


def test_describe_high_card():
    assert "High Card, Ace" in HandScore(HandRank.HIGH_CARD, (14, 13, 12, 11, 9)).describe()


def test_describe_one_pair():
    assert "One Pair, Deuces" in HandScore(HandRank.ONE_PAIR, (2, 14, 13, 12)).describe()


def test_describe_two_pair():
    assert "Two Pair, Aces and Kings" in HandScore(HandRank.TWO_PAIR, (14, 13, 12)).describe()


def test_describe_three_of_a_kind():
    assert "Three of a Kind, Sixes" in HandScore(HandRank.THREE_OF_A_KIND, (6, 14, 13)).describe()


def test_describe_straight():
    assert "Straight, Ace high" in HandScore(HandRank.STRAIGHT, (14,)).describe()


def test_describe_flush():
    assert "Flush, King high" in HandScore(HandRank.FLUSH, (13, 12, 11, 10, 9)).describe()


def test_describe_full_house():
    assert "Full House, Aces over Kings" in HandScore(HandRank.FULL_HOUSE, (14, 13)).describe()


def test_describe_four_of_a_kind():
    desc = HandScore(HandRank.FOUR_OF_A_KIND, (14, 13)).describe()
    assert "Four of a Kind, Aces" in desc
    assert "(kicker King)" in desc
    # actual format: "Four of a Kind, Aces (kicker King)"


def test_describe_straight_flush_non_royal():
    desc = HandScore(HandRank.STRAIGHT_FLUSH, (9,)).describe()
    assert "Straight Flush, Nine high" in desc


# ---------------------------------------------------------------------------
# Tie-breaking completeness
# ---------------------------------------------------------------------------


def test_two_pair_second_pair_tiebreaker():
    """Aces and Tens vs Aces and Nines — first wins."""
    a = HandScore(HandRank.TWO_PAIR, (14, 10, 5))
    b = HandScore(HandRank.TWO_PAIR, (14, 9, 5))
    assert b < a


def test_two_pair_kicker_tiebreaker():
    """Same two pair, different kicker."""
    a = HandScore(HandRank.TWO_PAIR, (14, 13, 12))
    b = HandScore(HandRank.TWO_PAIR, (14, 13, 11))
    assert b < a


def test_one_pair_kicker_tiebreaker():
    """Same pair, kicker cascade."""
    a = HandScore(HandRank.ONE_PAIR, (14, 13, 12, 11))
    b = HandScore(HandRank.ONE_PAIR, (14, 13, 12, 10))
    assert b < a


def test_flush_kicker_tiebreaker():
    """Both Ace-high flush, second card decides."""
    a = HandScore(HandRank.FLUSH, (14, 13, 12, 11, 9))
    b = HandScore(HandRank.FLUSH, (14, 13, 12, 11, 8))
    assert b < a
