"""GTO-style Level 4 bot — preflop charts plus postflop equity estimation.

Not a solver — a table of simplified GTO approximations:

* **Preflop**: position-based open / 3-bet / call / BB-defend charts
  with mixed frequencies (``gto_ranges.py``).  Mixed hands roll a
  deterministic RNG seeded from the hole cards, so a hand always plays
  the same way within a hand (stable frequencies across the table).
* **Postflop**: Monte Carlo equity of our exact hand vs the estimated
  range of the last aggressor, then value-bet / pot-odds-call /
  semi-bluff decisions with board-texture sizing (bigger on wet boards).

Known simplifications (documented honestly): the opponent's postflop
range is inferred from the preflop story (raise vs limp) and position,
not from their postflop actions; multiway pots are modeled against the
last aggressor only.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .base_bot import BaseBot
from ..game_engine import Action, ActionType, GamePhase, GameState
from ..game_engine.deck import Card, Rank, Suit
from ..game_engine.hand_evaluator import evaluate_7_cards
from .gto_ranges import (
    BB_DEFEND_3BET,
    BB_DEFEND_CALL,
    CALL_VS_3BET,
    CALL_VS_OPEN,
    FOUR_BET,
    LIMP_RANGE,
    RFI,
    THREE_BET,
    Range,
    range_frequency,
)
from .rule_bot import _draw_outs, _made_hand_strength, _postflop_equity

if TYPE_CHECKING:
    from .stats_tracker import OpponentStatsTracker


class GTOBot(BaseBot):
    """Range-chart bot approximating GTO play at a human-readable level.

    Parameters
    ----------
    stats : OpponentStatsTracker | None
        Accepted for registry parity with RuleBot; the charts currently
        don't adapt to opponent tendencies.
    """

    # Monte Carlo samples per equity estimate (≈ 20–40 ms per decision).
    N_SAMPLES = 200

    def __init__(self, stats: "OpponentStatsTracker | None" = None):
        self._stats = stats

    # ------------------------------------------------------------------
    # BaseBot interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "GTOBot Lv4"

    @property
    def style_description(self) -> str:
        return "GTO-inspired: preflop charts + Monte Carlo range equity"

    def decide(self, state: GameState, player_idx: int) -> Action:
        player = state.player(player_idx)
        assert player is not None and player.hole_cards is not None
        hole = list(player.hole_cards)
        if state.phase == GamePhase.PREFLOP:
            return self._decide_preflop(state, player_idx, hole)
        return self._decide_postflop(state, player_idx, hole)

    # ------------------------------------------------------------------
    # Preflop — chart-driven
    # ------------------------------------------------------------------

    def _decide_preflop(
        self, state: GameState, player_idx: int, hole: list[Card],
    ) -> Action:
        p = state.player(player_idx)
        assert p is not None
        to_call = state.current_bet - p.current_bet
        rng = self._rng(hole, state)
        is_bb = state.bb_seat == player_idx
        is_sb = state.sb_seat == player_idx
        bucket = self._position_bucket(player_idx, state)

        # Facing a 3-bet or larger (5bb cutoff separates opens from 3-bets).
        if state.current_bet >= state.big_blind * 5:
            if self._in(rng, hole, FOUR_BET):
                return self._raise_action(state, player_idx, 2.5)
            if (self._in(rng, hole, CALL_VS_3BET)
                    and to_call <= state.big_blind * 12):
                return Action(player_idx, ActionType.CALL)
            return Action(player_idx, ActionType.FOLD)

        # Facing a single raise.
        if state.current_bet > state.big_blind:
            if is_bb:
                # BB defense: wide call chart + polar 3-bet chart.
                if self._in(rng, hole, BB_DEFEND_3BET):
                    return self._raise_action(state, player_idx, 3.0)
                if self._in(rng, hole, BB_DEFEND_CALL):
                    return Action(player_idx, ActionType.CALL)
                return Action(player_idx, ActionType.FOLD)
            opener = self._opener_bucket(state, player_idx)
            if self._in(rng, hole, THREE_BET[opener]):
                return self._raise_action(state, player_idx, 3.0)
            if (self._in(rng, hole, CALL_VS_OPEN[opener])
                    and to_call <= state.big_blind * 10):
                return Action(player_idx, ActionType.CALL)
            return Action(player_idx, ActionType.FOLD)

        # Unopened pot.
        if to_call == 0:
            # BB option in a limped pot: raise the top of the range.
            if is_bb and self._in(rng, hole, BB_DEFEND_3BET):
                return self._raise_action(state, player_idx, 3.0)
            return Action(player_idx, ActionType.CHECK)
        if is_sb:
            # Raise-or-fold from the SB, completing sometimes.
            if self._in(rng, hole, RFI["sb"]):
                return self._raise_action(state, player_idx, 3.0)
            if self._in(rng, hole, LIMP_RANGE) and rng.random() < 0.5:
                return Action(player_idx, ActionType.CALL)
            return Action(player_idx, ActionType.FOLD)
        # Open-raise from position.
        if self._in(rng, hole, RFI[bucket]):
            return self._raise_action(state, player_idx, 2.5)
        return Action(player_idx, ActionType.FOLD)

    # ------------------------------------------------------------------
    # Postflop — equity vs estimated range
    # ------------------------------------------------------------------

    def _decide_postflop(
        self, state: GameState, player_idx: int, hole: list[Card],
    ) -> Action:
        board = list(state.community_cards)
        made = _made_hand_strength(hole, board)
        outs = _draw_outs(hole, board)
        equity = self._equity_vs_opponent(state, player_idx, hole)
        if equity is None:
            # No opponent model — fall back to the made-hand heuristic.
            equity = _postflop_equity(made, outs, state.phase)
        p = state.player(player_idx)
        assert p is not None
        to_call = state.current_bet - p.current_bet
        pot = state.pot.main_pot
        wet = self._board_is_wet(state)
        rng = self._rng(hole, state)

        # Draw outs are stale on the river (no cards to come): semi-bluffs
        # and implied-odds chases only make sense on the flop and turn.
        live_draw = outs >= 8 and state.phase in (
            GamePhase.FLOP, GamePhase.TURN,
        )

        if to_call == 0:
            # Value-bet strong hands; semi-bluff draws sometimes.
            if equity >= 0.62:
                sizing = 0.75 if wet else 0.5
                return self._bet_action(state, player_idx, pot, sizing)
            if live_draw and rng.random() < 0.45:
                return self._bet_action(state, player_idx, pot, 0.67)
            return Action(player_idx, ActionType.CHECK)

        required = to_call / (pot + to_call) if (pot + to_call) > 0 else 0.0
        if equity >= required + 0.03:
            # Raise the very top for value half the time.
            if equity >= 0.78 and rng.random() < 0.5:
                return self._raise_action(state, player_idx, 3.0)
            return Action(player_idx, ActionType.CALL)
        # Draws may chase slightly under the direct price (implied odds).
        if live_draw and equity >= required * 0.6:
            return Action(player_idx, ActionType.CALL)
        return Action(player_idx, ActionType.FOLD)

    # ------------------------------------------------------------------
    # Equity estimation
    # ------------------------------------------------------------------

    def _equity_vs_opponent(
        self, state: GameState, player_idx: int, hole: list[Card],
    ) -> float | None:
        """Monte Carlo equity of *hole* vs the opponent's estimated range.

        Returns ``None`` when no opponent range can be estimated.
        """
        opp_range = self._opponent_range(state, player_idx)
        if opp_range is None:
            return None
        board = list(state.community_cards)
        known = {(c.rank.value, c.suit.value) for c in hole + board}
        deck = [Card(r, s) for r in Rank for s in Suit
                if (r.value, s.value) not in known]
        combos = self._range_combos(opp_range, deck)
        if not combos:
            return None
        rng = self._rng(hole, state)
        wins = ties = 0
        total_weight = sum(freq for _, _, freq in combos)
        our_score = evaluate_7_cards(hole + board)
        for _ in range(self.N_SAMPLES):
            c1, c2 = self._weighted_sample(combos, total_weight, rng)
            opp_score = evaluate_7_cards([c1, c2] + board)
            if our_score > opp_score:
                wins += 1
            elif our_score == opp_score:
                ties += 1
        return (wins + ties / 2) / self.N_SAMPLES

    @staticmethod
    def _range_combos(
        rng_dict: Range, deck: list[Card],
    ) -> list[tuple[Card, Card, float]]:
        """All remaining hole-card pairs inside *rng_dict*, with weights."""
        combos: list[tuple[Card, Card, float]] = []
        for i, c1 in enumerate(deck):
            for c2 in deck[i + 1:]:
                freq = range_frequency(rng_dict, c1, c2)
                if freq > 0:
                    combos.append((c1, c2, freq))
        return combos

    @staticmethod
    def _weighted_sample(
        combos: list[tuple[Card, Card, float]],
        total_weight: float,
        rng: random.Random,
    ) -> tuple[Card, Card]:
        target = rng.random() * total_weight
        acc = 0.0
        for c1, c2, freq in combos:
            acc += freq
            if target <= acc:
                return c1, c2
        return combos[-1][0], combos[-1][1]

    def _opponent_range(
        self, state: GameState, player_idx: int,
    ) -> Range | None:
        """Estimate the relevant opponent's preflop range.

        Preflop: the current bet level says raise vs 3-bet vs limp.
        Postflop: pot size hints at the preflop story (raised vs limped
        pot) — the opponent's postflop actions do not narrow the range.
        """
        opps = [p.seat_idx for p in state.players
                if p.seat_idx != player_idx and (p.is_active or p.is_all_in)]
        if not opps:
            return None
        aggressor = state.last_aggressor_idx
        if aggressor is None or aggressor == player_idx or aggressor not in opps:
            aggressor = opps[0]
        bucket = self._position_bucket(aggressor, state)
        if state.phase == GamePhase.PREFLOP:
            if state.current_bet >= state.big_blind * 5:
                return THREE_BET[bucket]
            if state.current_bet > state.big_blind:
                return RFI[bucket]
            return LIMP_RANGE
        if state.pot.main_pot >= (state.small_blind + state.big_blind) * 3:
            return RFI[bucket]
        return LIMP_RANGE

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _in(rng: random.Random, hole: list[Card], rng_dict: Range) -> bool:
        """Range membership honoring mixed frequencies (rolled by *rng*)."""
        freq = range_frequency(rng_dict, hole[0], hole[1])
        if freq >= 1.0:
            return True
        if freq <= 0.0:
            return False
        return rng.random() < freq

    def _opener_bucket(self, state: GameState, player_idx: int) -> str:
        """Position bucket of the player who opened the betting."""
        opps = [p.seat_idx for p in state.players
                if p.seat_idx != player_idx and (p.is_active or p.is_all_in)]
        if not opps:
            return "utg"
        opener = state.last_aggressor_idx
        if opener is None or opener == player_idx or opener not in opps:
            opener = opps[0]
        return self._position_bucket(opener, state)

    def _position_bucket(self, seat: int, state: GameState) -> str:
        """Named position bucket for *seat* (blinds first, then by seats
        acting after it)."""
        if state.sb_seat == seat:
            return "sb"
        if state.bb_seat == seat:
            return "bb"
        after = self._seats_after(seat, state)
        if after == 0:
            return "btn"
        if after == 1:
            return "co"
        if after <= 3:
            return "mp"
        return "utg"

    @staticmethod
    def _seats_after(seat: int, state: GameState) -> int:
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

    @staticmethod
    def _raise_action(state: GameState, player_idx: int, sizing: float) -> Action:
        """RAISE to *sizing* × the bet to match (× big blind when opening),
        or ALL_IN when that exceeds the stack."""
        if state.current_bet > state.big_blind:
            target = int(state.current_bet * sizing)
        else:
            target = int(state.big_blind * sizing)
        target = max(target, state.current_bet + state.min_raise)
        stack = state.player(player_idx).stack  # type: ignore[union-attr]
        if target >= stack:
            return Action(player_idx, ActionType.ALL_IN)
        return Action(player_idx, ActionType.RAISE, amount=target)

    @staticmethod
    def _bet_action(
        state: GameState, player_idx: int, pot: int, fraction: float,
    ) -> Action:
        """BET *fraction* of the pot (ALL_IN when it exceeds the stack)."""
        amount = max(int(pot * fraction), state.big_blind)
        stack = state.player(player_idx).stack  # type: ignore[union-attr]
        if amount >= stack:
            return Action(player_idx, ActionType.ALL_IN)
        return Action(player_idx, ActionType.BET, amount=amount)

    @staticmethod
    def _board_is_wet(state: GameState) -> bool:
        """Two-tone or connected boards are wet (favor bigger sizing)."""
        board = list(state.community_cards)
        if len(board) < 3:
            return False
        suits = [c.suit for c in board]
        if any(suits.count(s) >= 2 for s in set(suits)):
            return True
        ranks = sorted({c.rank.value for c in board})
        return any(b - a <= 2 for a, b in zip(ranks, ranks[1:]))

    @staticmethod
    def _rng(hole: list[Card], state: GameState) -> random.Random:
        """Deterministic RNG seeded from cards and street — mixed
        frequencies stay stable for the same hand throughout."""
        phase_salt = {
            GamePhase.PREFLOP: 0, GamePhase.FLOP: 1,
            GamePhase.TURN: 2, GamePhase.RIVER: 3,
        }[state.phase]
        seed = phase_salt
        for c in sorted(hole + list(state.community_cards),
                        key=lambda c: (c.rank.value, c.suit.value)):
            seed = seed * 53 + c.rank.value * 4 + list(Suit).index(c.suit)
        return random.Random(seed)
