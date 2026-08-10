"""Game engine — core Texas Hold'em logic.

Public API surface — import from here for the common types and functions::

    from sekhmet.game_engine import (
        GamePhase, GameState, Player, PotState, Action, ActionType,
        evaluate_7_cards, HandScore, HandRank,
        validate, execute, deal_new_hand, runout_step,
        create_side_pots, award_pot,
    )
"""

from .deck import Card, Suit, Rank, Deck
from .hand_evaluator import HandRank, HandScore, evaluate_5_cards, evaluate_7_cards
from .game_state import (
    GamePhase,
    GameState,
    Player,
    PotState,
    SidePot,
    Action,
    ActionType,
    GameError,
    InvalidActionError,
    IllegalAmountError,
    NotYourTurnError,
    PhaseError,
    TableFullError,
    InsufficientFundsError,
    ScenarioNotFoundError,
)
from .action_processor import validate, execute, deal_new_hand, runout_step
from .pot_manager import create_side_pots, award_pot, PotAward

__all__ = [
    # deck
    "Card", "Suit", "Rank", "Deck",
    # hand evaluation
    "HandRank", "HandScore", "evaluate_5_cards", "evaluate_7_cards",
    # game state
    "GamePhase", "GameState", "Player", "PotState", "SidePot",
    "Action", "ActionType",
    # errors
    "GameError", "InvalidActionError", "IllegalAmountError",
    "NotYourTurnError", "PhaseError", "TableFullError",
    "InsufficientFundsError", "ScenarioNotFoundError",
    # action processing
    "validate", "execute", "deal_new_hand", "runout_step",
    # pot management
    "create_side_pots", "award_pot", "PotAward",
]
