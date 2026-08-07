"""Texas Hold'em hand evaluator.

Evaluates the best 5-card poker hand from up to 7 cards using the
C(7,5)=21 combination enumeration method (also known as the
"Trevor lookup" approach when paired with a precomputed table).

For a learning platform targeting human-scale throughput, the
algorithmic evaluator below is fast enough without precomputed
tables — 21 five-card evaluations per 7-card hand.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from itertools import combinations

from .deck import Card


class HandRank(IntEnum):
    """Poker hand categories ordered weakest → strongest."""

    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8

    def describe(self) -> str:
        _names: dict[HandRank, str] = {
            HandRank.HIGH_CARD: "High Card",
            HandRank.ONE_PAIR: "One Pair",
            HandRank.TWO_PAIR: "Two Pair",
            HandRank.THREE_OF_A_KIND: "Three of a Kind",
            HandRank.STRAIGHT: "Straight",
            HandRank.FLUSH: "Flush",
            HandRank.FULL_HOUSE: "Full House",
            HandRank.FOUR_OF_A_KIND: "Four of a Kind",
            HandRank.STRAIGHT_FLUSH: "Straight Flush",
        }
        return _names[self]


_RANK_NAMES: dict[int, str] = {
    14: "Ace",
    13: "King",
    12: "Queen",
    11: "Jack",
    10: "Ten",
    9: "Nine",
    8: "Eight",
    7: "Seven",
    6: "Six",
    5: "Five",
    4: "Four",
    3: "Three",
    2: "Deuce",
}


def _rank_name(r: int) -> str:
    return _RANK_NAMES.get(r, str(r))


def _plural_rank_name(r: int) -> str:
    name = _rank_name(r)
    if name == "Six":
        return "Sixes"
    if name.endswith("e"):
        return name + "s"  # Ace → Aces
    return name + "s"


@dataclass(frozen=True, order=True)
class HandScore:
    """Comparable poker hand strength.

    Ordered by ``(rank, kickers)`` so that ``HandScore`` objects sort
    weakest → strongest via the standard ``<`` / ``sorted()``.

    Attributes
    ----------
    rank : HandRank
        Hand category.
    kickers : tuple[int, ...]
        Tie-breaking ranks in descending significance.
        - Straight / straight flush: ``(high_rank,)``
        - Quads: ``(quad_rank, kicker)``
        - Full house: ``(trip_rank, pair_rank)``
        - Flush / high card: ``(k1, k2, k3, k4, k5)``
        - Trips: ``(trip_rank, k1, k2)``
        - Two pair: ``(high_pair, low_pair, kicker)``
        - One pair: ``(pair_rank, k1, k2, k3)``
    """

    rank: HandRank
    kickers: tuple[int, ...]

    def describe(self) -> str:
        """Human-readable description, e.g. "Full House, Aces over Kings"."""
        r = self.rank
        k = self.kickers

        if r == HandRank.STRAIGHT_FLUSH:
            if k[0] == 14:
                return "Royal Flush"
            return f"Straight Flush, {_rank_name(k[0])} high"

        if r == HandRank.FOUR_OF_A_KIND:
            return f"Four of a Kind, {_plural_rank_name(k[0])} (kicker {_rank_name(k[1])})"

        if r == HandRank.FULL_HOUSE:
            return f"Full House, {_plural_rank_name(k[0])} over {_plural_rank_name(k[1])}"

        if r == HandRank.FLUSH:
            return f"Flush, {_rank_name(k[0])} high"

        if r == HandRank.STRAIGHT:
            return f"Straight, {_rank_name(k[0])} high"

        if r == HandRank.THREE_OF_A_KIND:
            return f"Three of a Kind, {_plural_rank_name(k[0])}"

        if r == HandRank.TWO_PAIR:
            return f"Two Pair, {_plural_rank_name(k[0])} and {_plural_rank_name(k[1])}"

        if r == HandRank.ONE_PAIR:
            return f"One Pair, {_plural_rank_name(k[0])}"

        return f"High Card, {_rank_name(k[0])}"


# ---------------------------------------------------------------------------
# Five-card evaluator (the workhorse for the 7 → 5 enumeration)
# ---------------------------------------------------------------------------


def evaluate_5_cards(cards: list[Card]) -> HandScore:
    """Evaluate exactly 5 cards and return their ``HandScore``.

    Raises
    ------
    ValueError
        If ``cards`` does not contain exactly 5 elements.
    """
    if len(cards) != 5:
        raise ValueError(f"evaluate_5_cards expects exactly 5 cards, got {len(cards)}")

    ranks = sorted((c.rank.value for c in cards), reverse=True)
    suits = {c.suit for c in cards}
    is_flush = len(suits) == 1

    # --- straight detection (including A-2-3-4-5 wheel) ---
    is_straight = False
    straight_high = 0
    if len(set(ranks)) == 5:  # all ranks distinct
        if ranks[0] - ranks[4] == 4:
            is_straight = True
            straight_high = ranks[0]
        elif ranks == [14, 5, 4, 3, 2]:  # wheel
            is_straight = True
            straight_high = 5  # 5-high straight

    # --- straight flush ---
    if is_flush and is_straight:
        return HandScore(HandRank.STRAIGHT_FLUSH, (straight_high,))

    # --- flush (not straight) ---
    if is_flush:
        return HandScore(HandRank.FLUSH, tuple(ranks))

    # --- straight (not flush) ---
    if is_straight:
        return HandScore(HandRank.STRAIGHT, (straight_high,))

    # --- paired / set hands ---
    counter = Counter(ranks)
    # sort by (count descending, rank descending)
    groups = sorted(counter.items(), key=lambda item: (item[1], item[0]), reverse=True)

    primary_count = groups[0][1]

    if primary_count == 4:  # quads
        quad_rank = groups[0][0]
        kicker = groups[1][0]
        return HandScore(HandRank.FOUR_OF_A_KIND, (quad_rank, kicker))

    if primary_count == 3:
        trip_rank = groups[0][0]
        if groups[1][1] == 2:  # full house
            pair_rank = groups[1][0]
            return HandScore(HandRank.FULL_HOUSE, (trip_rank, pair_rank))
        # trips
        kicker_high, kicker_low = groups[1][0], groups[2][0]
        return HandScore(HandRank.THREE_OF_A_KIND, (trip_rank, kicker_high, kicker_low))

    if primary_count == 2:
        pair_rank = groups[0][0]
        if groups[1][1] == 2:  # two pair
            low_pair = groups[1][0]
            kicker = groups[2][0]
            return HandScore(HandRank.TWO_PAIR, (pair_rank, low_pair, kicker))
        # one pair
        kickers = tuple(g[0] for g in groups[1:])  # 3 kickers
        return HandScore(HandRank.ONE_PAIR, (pair_rank,) + kickers)

    # high card
    return HandScore(HandRank.HIGH_CARD, tuple(ranks))


# ---------------------------------------------------------------------------
# Seven-card evaluator (the entry point callers use)
# ---------------------------------------------------------------------------


def evaluate_7_cards(cards: list[Card]) -> HandScore:
    """Return the best 5-card ``HandScore`` from up to 7 cards.

    This is the standard Texas Hold'em evaluator: for 7 cards there are
    C(7,5)=21 combinations, each evaluated independently, and the
    highest-scoring combination wins.

    Parameters
    ----------
    cards : list[Card]
        Between 5 and 7 cards (typically 2 hole + 5 community).

    Returns
    -------
    HandScore
        The best possible hand.

    Raises
    ------
    ValueError
        If fewer than 5 or more than 7 cards are provided.
    """
    n = len(cards)
    if n < 5:
        raise ValueError(f"Need at least 5 cards to form a hand, got {n}")
    if n > 7:
        raise ValueError(f"At most 7 cards supported, got {n}")

    if n == 5:
        return evaluate_5_cards(cards)

    return max(evaluate_5_cards(list(combo)) for combo in combinations(cards, 5))
