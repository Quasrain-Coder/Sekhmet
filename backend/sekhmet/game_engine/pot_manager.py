"""Pot management — side-pot creation and pot award.

When players go all-in for different amounts, multiple side-pots are
created so that each player can only win the portion of the pot they
were eligible for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .game_state import Player, PotState, SidePot

if TYPE_CHECKING:
    from .hand_evaluator import HandScore


# ---------------------------------------------------------------------------
# Side-pot creation
# ---------------------------------------------------------------------------


def create_side_pots(players: tuple[Player, ...]) -> PotState:
    """Build main pot + side pots from players' total bets.

    Algorithm
    ---------
    1. Collect every player's ``total_bet`` (chips committed this hand).
    2. Sort unique bet levels ascending.
    3. For each level, the difference vs. the previous level is a "slice".
       Every player whose ``total_bet >= level`` contributes to that slice.
       Players whose ``total_bet < level`` are excluded (they are all-in
       below this level and cannot win chips beyond their contribution).

    Parameters
    ----------
    players : tuple[Player, ...]
        All players at the table (including folded).  Folded players'
        bets still contribute to the pot(s), but they are ineligible
        to win at showdown.

    Returns
    -------
    PotState
        ``main_pot`` holds the lowest-level slice (everyone eligible).
        ``side_pots`` are ordered from smallest all-in to largest.
    """
    # Only consider players who actually put chips in
    bets = sorted({p.total_bet for p in players if p.total_bet > 0})
    if not bets:
        return PotState()

    side_pots: list[SidePot] = []
    prev_level = 0
    main_pot_amount = 0

    for level in bets:
        slice_amount = level - prev_level
        if slice_amount <= 0:
            prev_level = level
            continue

        eligible = tuple(
            p.seat_idx for p in players if p.total_bet >= level
        )
        total_slice = len(eligible) * slice_amount

        if prev_level == 0:
            main_pot_amount = total_slice
        else:
            side_pots.append(SidePot(amount=total_slice, eligible_players=eligible))

        prev_level = level

    return PotState(main_pot=main_pot_amount, side_pots=tuple(side_pots))


# ---------------------------------------------------------------------------
# Pot award (showdown)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PotAward:
    """Result of awarding a single pot (main or side)."""

    amount: int
    winner_seat_idx: int
    hand_description: str


def award_pot(
    pot: PotState,
    players: tuple[Player, ...],
    hands: dict[int, HandScore],  # seat_idx → best hand
    dealer_idx: int,
) -> list[PotAward]:
    """Distribute every pot to its winner(s).

    For each pot (main + each side), the eligible player with the best
    hand wins.  Ties split the pot evenly; odd chips go to the tied
    player(s) closest to the dealer's left, continuing clockwise.

    Parameters
    ----------
    pot : PotState
        The pot(s) to distribute.
    players : tuple[Player, ...]
        All players (to resolve seat order for tie-breaking).
    hands : dict[int, HandScore]
        Mapping from seat index to the player's best 5-card hand.
        Only players who reach showdown should be included; folded
        players are implicitly excluded.
    dealer_idx : int
        Seat holding the dealer button — anchor for odd-chip tie-breaks.

    Returns
    -------
    list[PotAward]
        One entry per pot that was awarded, in order from main to last side.
    """
    awards: list[PotAward] = []

    # All pots to distribute: main first, then side pots in order
    pots_to_award: list[tuple[int, tuple[int, ...]]] = [
        (pot.main_pot, tuple(p.seat_idx for p in players if p.total_bet > 0)),
    ]
    for sp in pot.side_pots:
        pots_to_award.append((sp.amount, sp.eligible_players))

    for pot_amount, eligible in pots_to_award:
        if pot_amount == 0:
            continue

        # Find eligible players who have a hand (reached showdown)
        contenders = {
            seat: hands[seat]
            for seat in eligible
            if seat in hands
        }
        if not contenders:
            continue

        # Best hand among contenders
        best_score = max(contenders.values())
        winners = [seat for seat, score in contenders.items() if score == best_score]

        if len(winners) == 1:
            awards.append(PotAward(
                amount=pot_amount,
                winner_seat_idx=winners[0],
                hand_description=best_score.describe(),
            ))
        else:
            # Split pot — odd chips to the tied player(s) closest to the
            # dealer's left, continuing clockwise.  The seat ring size is
            # the highest occupied seat + 1 (matches the engine's turn
            # order over sparse seat indices).
            n_seats = max((p.seat_idx + 1 for p in players), default=0)
            if n_seats > 0:
                winners.sort(key=lambda s: (s - dealer_idx - 1) % n_seats)
            share = pot_amount // len(winners)
            remainder = pot_amount % len(winners)
            for i, seat in enumerate(winners):
                extra = 1 if i < remainder else 0
                if share + extra > 0:
                    awards.append(PotAward(
                        amount=share + extra,
                        winner_seat_idx=seat,
                        hand_description=best_score.describe(),
                    ))

    return awards
