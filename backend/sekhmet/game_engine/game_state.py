"""Game state machine — the single source of truth for every hand.

Every action produces a **new** ``GameState`` snapshot (frozen dataclass).
This design enables:

* **Replay** — save ``round_history`` and replay the entire hand.
* **Undo** — the trainer can rewind to any decision point.
* **Testability** — given (state, action), the result is fully deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .deck import Card


# ---------------------------------------------------------------------------
# Game phase
# ---------------------------------------------------------------------------


class GamePhase(Enum):
    """Sequential phases of a single Texas Hold'em hand."""

    WAITING = auto()     # waiting for players to sit down / ready up
    DEALING = auto()     # hole cards dealt, blinds posted
    PREFLOP = auto()     # pre-flop betting round (starts after UTG/CO/...)
    FLOP = auto()        # 3 community cards dealt → betting round
    TURN = auto()        # 4th community card → betting round
    RIVER = auto()       # 5th community card → betting round
    SHOWDOWN = auto()    # reveal hands, award pot, hand over

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Player seat
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Player:
    """Immutable snapshot of a single player at the table.

    Attributes
    ----------
    name : str
        Display name.
    seat_idx : int
        0-based seat index around the table.
    stack : int
        Current chip count.
    hole_cards : tuple[Card, Card] | None
        ``None`` until hole cards are dealt.
    is_active : bool
        ``False`` once the player has folded or is eliminated.
    is_all_in : bool
        ``True`` when the player has committed their entire stack.
    current_bet : int
        Chips the player has committed **in the current betting round**.
    total_bet : int
        Chips the player has committed **across all streets** this hand.
    is_human : bool
        ``True`` for the human user, ``False`` for bots.
    """

    name: str
    seat_idx: int
    stack: int = 1000
    hole_cards: tuple[object, object] | None = None  # Card objects at runtime
    is_active: bool = True
    is_all_in: bool = False
    current_bet: int = 0
    total_bet: int = 0
    is_human: bool = False

    def __post_init__(self):
        if self.stack < 0:
            raise ValueError(f"Player stack cannot be negative: {self.stack}")
        if self.current_bet < 0:
            raise ValueError(f"current_bet cannot be negative: {self.current_bet}")
        if self.total_bet < 0:
            raise ValueError(f"total_bet cannot be negative: {self.total_bet}")


# ---------------------------------------------------------------------------
# Pot state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SidePot:
    """A single side-pot created when one or more players are all-in."""

    amount: int
    eligible_players: tuple[int, ...]  # seat indices


@dataclass(frozen=True)
class PotState:
    """All pots for the current hand.

    ``main_pot`` is always present. ``side_pots`` is ordered from first
    created (smallest all-in) to last (largest all-in).
    """

    main_pot: int = 0
    side_pots: tuple[SidePot, ...] = ()

    @property
    def total(self) -> int:
        return self.main_pot + sum(sp.amount for sp in self.side_pots)


# ---------------------------------------------------------------------------
# Action (what a player does)
# ---------------------------------------------------------------------------


class ActionType(Enum):
    FOLD = auto()
    CHECK = auto()
    CALL = auto()
    BET = auto()
    RAISE = auto()
    ALL_IN = auto()


@dataclass(frozen=True)
class Action:
    """A single action taken by a player during a betting round.

    ``amount`` is only meaningful for BET, RAISE, and CALL (tracking).
    """

    player_idx: int
    type: ActionType
    amount: int = 0

    def __str__(self) -> str:
        base = f"P{self.player_idx} {self.type.name}"
        if self.amount > 0:
            base += f" {self.amount}"
        return base


# ---------------------------------------------------------------------------
# The main GameState
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GameState:
    """Complete snapshot of a poker hand at a single point in time.

    All fields are immutable.  Use ``action_processor.execute(state, action)``
    to produce the **next** ``GameState``.
    """

    phase: GamePhase = GamePhase.WAITING
    players: tuple[Player, ...] = ()
    community_cards: tuple[object, ...] = ()  # Card objects at runtime
    pot: PotState = field(default_factory=PotState)
    deck: tuple[object, ...] = ()  # remaining cards (Card objects)

    # Turn management
    current_player_idx: int | None = None
    dealer_idx: int = 0

    # Betting state for the current street
    current_bet: int = 0          # the "bet to match" this street
    min_raise: int = 0            # minimum raise size
    last_aggressor_idx: int | None = None

    # Blinds
    small_blind: int = 5
    big_blind: int = 10

    # History (append-only log for replay)
    round_history: tuple[Action, ...] = ()

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def active_players(self) -> tuple[Player, ...]:
        """Players who haven't folded and still have chips."""
        return tuple(p for p in self.players if p.is_active)

    @property
    def players_in_hand(self) -> tuple[Player, ...]:
        """Players who haven't folded (may be all-in)."""
        return tuple(p for p in self.players if p.is_active or p.is_all_in)

    @property
    def n_active(self) -> int:
        return len(self.active_players)

    def player(self, idx: int) -> Player | None:
        """Return the player at *idx*, or ``None`` if the seat is empty."""
        for p in self.players:
            if p.seat_idx == idx:
                return p
        return None

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    def with_players(self, players: tuple[Player, ...]) -> GameState:
        """Return a copy with *players* replaced."""
        return GameState(
            phase=self.phase,
            players=players,
            community_cards=self.community_cards,
            pot=self.pot,
            deck=self.deck,
            current_player_idx=self.current_player_idx,
            dealer_idx=self.dealer_idx,
            current_bet=self.current_bet,
            min_raise=self.min_raise,
            last_aggressor_idx=self.last_aggressor_idx,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
            round_history=self.round_history,
        )

    def with_phase(self, phase: GamePhase) -> GameState:
        """Return a copy with *phase* replaced, resetting street-level state."""
        return GameState(
            phase=phase,
            players=self.players,
            community_cards=self.community_cards,
            pot=self.pot,
            deck=self.deck,
            current_player_idx=self.current_player_idx,
            dealer_idx=self.dealer_idx,
            current_bet=0,
            min_raise=self.big_blind,
            last_aggressor_idx=None,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
            round_history=self.round_history,
        )


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class GameError(Exception):
    """Base class for all game-logic errors."""


class InvalidActionError(GameError):
    """The requested action is not legal in the current state."""


class IllegalAmountError(GameError):
    """Bet/raise amount is illegal (below min-raise or exceeds stack)."""


class NotYourTurnError(GameError):
    """A player tried to act when it's not their turn."""


class PhaseError(GameError):
    """The requested operation is not valid in the current phase."""


class TableFullError(GameError):
    """Cannot add a player — the table is full."""


class InsufficientFundsError(GameError):
    """Player does not have enough chips."""


class ScenarioNotFoundError(GameError):
    """The requested training scenario does not exist."""
