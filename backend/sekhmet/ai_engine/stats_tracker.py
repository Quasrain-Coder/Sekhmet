"""Cross-hand opponent stats (VPIP / PFR / fold-to-bet) for the rule bots.

Bots are re-created for every action — ``table_manager`` builds a fresh
instance per turn — so this tracker lives on the table session and is
handed in at creation time.  The session records every executed action
(human and bot alike); RuleBot levels 2+ read the accumulated rates to
tune bluff frequency against each opponent.

Per-hand scratch flags fold into the counters on ``new_hand``, so the
rates always reflect completed hands only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..game_engine import ActionType, GamePhase

if TYPE_CHECKING:
    from ..game_engine import Action, GameState


@dataclass
class OpponentStats:
    """Aggregated tendencies for one seat."""

    hands: int = 0              # hands dealt into
    actions: int = 0            # actions observed in total
    vpip: int = 0               # hands with a voluntary preflop chip
    pfr: int = 0                # hands with a preflop raise
    faced_bets: int = 0         # postflop decisions facing a bet
    folds_to_bet: int = 0       # of those, folds
    raises_facing_bet: int = 0  # of those, raises (aggression)
    bets_unopened: int = 0      # voluntary bets into unopened pots

    # Scratch for the current hand (folded into the counters on
    # new_hand — never read directly by decision code).
    _vpip_this_hand: bool = field(default=False, repr=False)
    _pfr_this_hand: bool = field(default=False, repr=False)

    def vpip_rate(self) -> float:
        """Laplace-smoothed VPIP."""
        return (self.vpip + 1) / (self.hands + 2)

    def pfr_rate(self) -> float:
        """Laplace-smoothed PFR."""
        return (self.pfr + 1) / (self.hands + 2)

    def fold_to_bet_rate(self) -> float:
        """Laplace-smoothed share of faced bets that got folded."""
        return (self.folds_to_bet + 1) / (self.faced_bets + 2)

    def aggression_rate(self) -> float:
        """Share of faced-bet decisions answered with a raise."""
        return (self.raises_facing_bet + 1) / (self.faced_bets + 2)


class OpponentStatsTracker:
    """Per-seat opponent model; ``observe`` is called after every action."""

    def __init__(self) -> None:
        self.stats: dict[int, OpponentStats] = {}

    def new_hand(self, seats: list[int]) -> None:
        """Fold per-hand scratch into the counters, then start a hand.

        ``seats`` are the seats dealt into the new hand; each gets its
        hand count incremented.
        """
        for st in self.stats.values():
            if st._vpip_this_hand:
                st.vpip += 1
            if st._pfr_this_hand:
                st.pfr += 1
            st._vpip_this_hand = False
            st._pfr_this_hand = False
        for seat in seats:
            self.stats.setdefault(seat, OpponentStats()).hands += 1

    def observe(self, pre_state: "GameState", action: "Action") -> None:
        """Record *action*, taken in *pre_state* (the state before it)."""
        st = self.stats.setdefault(action.player_idx, OpponentStats())
        st.actions += 1
        if pre_state.phase == GamePhase.PREFLOP:
            if action.type in (
                ActionType.CALL, ActionType.BET, ActionType.RAISE,
                ActionType.ALL_IN,
            ):
                st._vpip_this_hand = True
            if action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
                st._pfr_this_hand = True
            return
        player = pre_state.player(action.player_idx)
        to_call = pre_state.current_bet - (player.current_bet if player else 0)
        if to_call > 0:
            st.faced_bets += 1
            if action.type == ActionType.FOLD:
                st.folds_to_bet += 1
            elif action.type in (ActionType.RAISE, ActionType.ALL_IN):
                st.raises_facing_bet += 1
        elif action.type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
            st.bets_unopened += 1
