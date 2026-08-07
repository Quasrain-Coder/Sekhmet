"""Rule-based poker bot with three difficulty levels.

Level 1 — Basic ABC poker:
    Raises premiums, calls medium hands, folds trash.

Level 2 — Intermediate:
    Adds position awareness, pot-odds consideration, and tighter
    play against aggression.

Level 3 — Advanced:
    Adds range-based thinking, semi-bluffing with draws, variable
    bet sizing, and board-texture awareness.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .base_bot import BaseBot, BotPersonality
from ..game_engine import Action, ActionType, GamePhase, GameState
from ..game_engine.hand_evaluator import evaluate_7_cards, HandRank

if TYPE_CHECKING:
    from ..game_engine.deck import Card


# ---------------------------------------------------------------------------
# Preflop hand strength heuristic
# ---------------------------------------------------------------------------


def _preflop_strength(cards: list["Card"]) -> float:
    """Return a 0–1 score for hole-card strength.

    Rough approximation — not a full equity calc, but good enough for
    a rule-based bot's opening decisions.
    """
    r1 = cards[0].rank.value
    r2 = cards[1].rank.value
    high = max(r1, r2)
    low = min(r1, r2)
    suited = cards[0].suit == cards[1].suit
    gap = high - low
    paired = high == low

    # Base score from high card + low card
    score = (high - 2) / 12 * 0.6 + (low - 2) / 12 * 0.2

    # Pair bonus (scale with rank so AA > KK > ... > 22)
    if paired:
        score += 0.10 + (high - 2) / 12 * 0.12  # 0.10–0.22 pair bonus
    elif suited:
        score += 0.04
    if gap <= 2 and not paired:
        score += 0.04  # connected
    if gap == 1 and suited:
        score += 0.04  # suited connector bonus

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Postflop hand assessment
# ---------------------------------------------------------------------------


def _made_hand_strength(hole: list["Card"], community: list["Card"]) -> float:
    """Return 0–1 score for current made-hand strength.

    Uses the evaluator to find the best 5-card hand and maps the
    HandRank to a normalized 0–1 scale.
    """
    score = evaluate_7_cards(hole + community)
    rank_count = len(HandRank)  # 9 categories
    base = score.rank.value / (rank_count - 1)
    # Boost by top kicker
    kicker_bonus = score.kickers[0] / 14 * 0.05 if score.kickers else 0
    return min(base + kicker_bonus, 1.0)


def _has_draw(hole: list["Card"], community: list["Card"]) -> tuple[bool, bool]:
    """Check for flush draw and open-ended straight draw.

    Returns (flush_draw, oesd).
    """
    suits = [c.suit for c in hole + community]
    flush_draw = any(suits.count(s) == 4 for s in set(suits))

    ranks = sorted({c.rank.value for c in hole + community})
    oesd = False
    for i in range(len(ranks) - 3):
        if ranks[i + 3] - ranks[i] == 3:
            oesd = True
            break

    return flush_draw, oesd


# ---------------------------------------------------------------------------
# RuleBot
# ---------------------------------------------------------------------------


class RuleBot(BaseBot):
    """A bot that makes decisions using hand-crafted rules.

    Parameters
    ----------
    level : int
        Difficulty level (1–3).
    personality : BotPersonality | None
        Custom personality; defaults to level-appropriate settings.
    """

    def __init__(self, level: int = 1, personality: BotPersonality | None = None):
        if level not in (1, 2, 3):
            raise ValueError(f"RuleBot level must be 1–3, got {level}")
        self._level = level
        self._personality = personality or self._default_personality(level)

    # ------------------------------------------------------------------
    # BaseBot interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return f"RuleBot Lv{self._level}"

    @property
    def style_description(self) -> str:
        desc = {
            1: "ABC poker — plays premiums, folds trash",
            2: "Position-aware with pot-odds consideration",
            3: "Range-based with semi-bluffs and variable sizing",
        }
        return desc[self._level]

    def decide(self, state: GameState, player_idx: int) -> Action:
        player = state.player(player_idx)
        assert player is not None and player.hole_cards is not None
        hole = list(player.hole_cards)

        if state.phase == GamePhase.PREFLOP:
            return self._decide_preflop(state, player_idx, hole)
        else:
            return self._decide_postflop(state, player_idx, hole)

    # ------------------------------------------------------------------
    # Preflop decisions
    # ------------------------------------------------------------------

    def _decide_preflop(
        self, state: GameState, player_idx: int, hole: list["Card"],
    ) -> Action:
        strength = _preflop_strength(hole)
        p = self._personality
        to_call = state.current_bet - state.player(player_idx).current_bet  # type: ignore[operator]
        pos = self._position(player_idx, state)

        # Adjust threshold by tightness and position
        threshold = 0.2 + p.tightness * 0.3
        if p.use_position:
            threshold -= pos * 0.05  # looser in late position

        if strength < threshold:
            if to_call == 0:
                return Action(player_idx, ActionType.CHECK)
            return Action(player_idx, ActionType.FOLD)

        # Premium: raise
        if strength > 0.7 + p.tightness * 0.1:
            sizing = self._bet_size(state, strength, is_preflop=True)
            if sizing >= state.player(player_idx).stack:  # type: ignore[operator]
                return Action(player_idx, ActionType.ALL_IN)
            return Action(player_idx, ActionType.RAISE, amount=sizing)

        # Medium: call or small raise
        if strength > threshold + 0.15:
            if to_call == 0:
                sizing = self._bet_size(state, strength, is_preflop=True)
                return Action(player_idx, ActionType.BET, amount=sizing)
            return Action(player_idx, ActionType.CALL)

        # Marginal: call if cheap, fold otherwise
        if to_call <= state.big_blind * 3:
            return Action(player_idx, ActionType.CALL)
        return Action(player_idx, ActionType.FOLD)

    # ------------------------------------------------------------------
    # Postflop decisions
    # ------------------------------------------------------------------

    def _decide_postflop(
        self, state: GameState, player_idx: int, hole: list["Card"],
    ) -> Action:
        community = list(state.community_cards)
        made = _made_hand_strength(hole, community)
        flush_draw, oesd = _has_draw(hole, community)
        p = self._personality
        to_call = state.current_bet - state.player(player_idx).current_bet  # type: ignore[operator]

        # --- Determine action category ---
        if made > 0.8:
            category = "strong"
        elif made > 0.5:
            category = "medium"
        elif flush_draw or oesd:
            category = "draw"
        else:
            category = "weak"

        if self._level >= 3 and category == "draw":
            # Semi-bluff some of the time
            if random.random() < p.aggression * 0.4:
                sizing = self._bet_size(state, 0.5, is_preflop=False)
                if sizing >= state.player(player_idx).stack:  # type: ignore[operator]
                    return Action(player_idx, ActionType.ALL_IN)
                return Action(player_idx, ActionType.RAISE, amount=sizing)

        if category == "strong":
            sizing = self._bet_size(state, made, is_preflop=False)
            if to_call == 0:
                return Action(player_idx, ActionType.BET, amount=sizing)
            if made > 0.9 and self._level >= 2:
                return Action(player_idx, ActionType.RAISE, amount=sizing)
            return Action(player_idx, ActionType.CALL)

        if category == "medium":
            if to_call == 0:
                # Sometimes bet for protection
                if random.random() < p.aggression * 0.5:
                    sizing = self._bet_size(state, made, is_preflop=False)
                    return Action(player_idx, ActionType.BET, amount=sizing)
                return Action(player_idx, ActionType.CHECK)
            # Call if price is right (Level 2+ uses pot odds)
            if self._level >= 2 and p.use_pot_odds:
                pot = state.pot.main_pot
                odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 0
                if made > odds:
                    return Action(player_idx, ActionType.CALL)
                return Action(player_idx, ActionType.FOLD)
            return Action(player_idx, ActionType.CALL)

        # category == "weak"
        if to_call == 0:
            # Level 2+: occasionally stab at orphan pots
            if self._level >= 2 and random.random() < p.aggression * 0.15:
                sizing = state.big_blind * 2
                return Action(player_idx, ActionType.BET, amount=sizing)
            return Action(player_idx, ActionType.CHECK)
        else:
            # Bluff catch or fold
            if self._level >= 3 and random.random() < p.bluff_frequency:
                return Action(player_idx, ActionType.CALL)
            return Action(player_idx, ActionType.FOLD)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _position(player_idx: int, state: GameState) -> float:
        """Return 0–1 position quality (0 = early, 1 = late/button)."""
        seats = sorted(p.seat_idx for p in state.players)
        if len(seats) <= 1:
            return 0.5
        idx = seats.index(player_idx)
        # Normalize so dealer is last
        return idx / (len(seats) - 1) if len(seats) > 1 else 0.5

    def _bet_size(
        self, state: GameState, strength: float, is_preflop: bool,
    ) -> int:
        """Compute a bet/raise size in chips.

        Level 1-2: fixed sizing (3bb pre, 2/3 pot post).
        Level 3: variable based on strength.
        """
        if is_preflop:
            if self._level >= 3:
                base = int(state.big_blind * (2.5 + strength * 3))
            else:
                base = state.big_blind * 3
            return max(base, state.current_bet + state.min_raise)

        # Postflop: fraction of pot
        pot = state.pot.main_pot
        if self._level >= 3:
            frac = 0.4 + strength * 0.6  # 0.4–1.0 pot
        else:
            frac = 0.67
        amount = max(int(pot * frac), state.big_blind)
        if state.current_bet > 0:
            amount = max(amount, state.current_bet + state.min_raise)
        return amount

    @staticmethod
    def _default_personality(level: int) -> BotPersonality:
        if level == 1:
            return BotPersonality(aggression=0.3, tightness=0.7, bluff_frequency=0.0)
        if level == 2:
            return BotPersonality(aggression=0.5, tightness=0.5, bluff_frequency=0.05,
                                  use_position=True, use_pot_odds=True)
        # Level 3
        return BotPersonality(aggression=0.65, tightness=0.35, bluff_frequency=0.15,
                              use_position=True, use_pot_odds=True)
