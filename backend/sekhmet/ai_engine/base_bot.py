"""Abstract base class for all poker bots.

Every bot must implement ``decide(state, player_idx) -> Action``.
The engine calls this when it's the bot's turn to act.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game_engine import Action, GameState


@dataclass
class BotPersonality:
    """Tunable parameters that influence bot decision-making.

    These are set per bot instance and read by the decision logic.
    """

    aggression: float = 0.5       # 0 = passive, 1 = maniac
    tightness: float = 0.5        # 0 = plays any two, 1 = only premiums
    bluff_frequency: float = 0.0  # 0 = never bluffs, 1 = bluffs too much
    use_position: bool = True     # whether to adjust by position
    use_pot_odds: bool = True     # whether to calculate pot odds


class BaseBot(ABC):
    """Interface that every bot must implement."""

    @abstractmethod
    def decide(self, state: "GameState", player_idx: int) -> "Action":
        """Return the action the bot wants to take.

        Parameters
        ----------
        state : GameState
            The current game state (immutable snapshot).
        player_idx : int
            The bot's own seat index.

        Returns
        -------
        Action
            The bot's chosen action.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable bot name, e.g. "RuleBot Lv2"."""
        ...

    @property
    @abstractmethod
    def style_description(self) -> str:
        """One-line description of the bot's play style."""
        ...
