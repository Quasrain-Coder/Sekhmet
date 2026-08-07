"""Tests for the immutable GameState and its building blocks."""

import pytest
from sekhmet.game_engine.game_state import (
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


# ---------------------------------------------------------------------------
# GamePhase
# ---------------------------------------------------------------------------


def test_game_phase_order():
    """Verify the phases follow the natural poker order."""
    order = [
        GamePhase.WAITING,
        GamePhase.DEALING,
        GamePhase.PREFLOP,
        GamePhase.FLOP,
        GamePhase.TURN,
        GamePhase.RIVER,
        GamePhase.SHOWDOWN,
    ]
    for i in range(len(order) - 1):
        assert order[i].value < order[i + 1].value


def test_game_phase_str():
    assert str(GamePhase.PREFLOP) == "PREFLOP"


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------


def test_player_defaults():
    p = Player(name="Alice", seat_idx=0)
    assert p.name == "Alice"
    assert p.stack == 1000
    assert p.hole_cards is None
    assert p.is_active is True
    assert p.is_all_in is False
    assert p.current_bet == 0
    assert p.total_bet == 0


def test_player_immutable():
    p = Player(name="Bob", seat_idx=1)
    with pytest.raises(Exception):
        p.stack = 500  # type: ignore[misc]


def test_player_negative_stack_raises():
    with pytest.raises(ValueError, match="negative"):
        Player(name="X", seat_idx=0, stack=-1)


# ---------------------------------------------------------------------------
# PotState & SidePot
# ---------------------------------------------------------------------------


def test_pot_total_empty():
    assert PotState().total == 0


def test_pot_total_with_main_and_sides():
    pot = PotState(
        main_pot=100,
        side_pots=(
            SidePot(amount=50, eligible_players=(0, 1)),
            SidePot(amount=30, eligible_players=(0,)),
        ),
    )
    assert pot.total == 180


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------


def test_action_str():
    a = Action(player_idx=2, type=ActionType.RAISE, amount=50)
    assert "RAISE" in str(a)
    assert "50" in str(a)


def test_action_str_fold():
    a = Action(player_idx=0, type=ActionType.FOLD)
    assert "FOLD" in str(a)


# ---------------------------------------------------------------------------
# GameState — defaults
# ---------------------------------------------------------------------------


def test_initial_state():
    gs = GameState()
    assert gs.phase == GamePhase.WAITING
    assert gs.players == ()
    assert gs.community_cards == ()
    assert gs.pot.main_pot == 0
    assert gs.n_active == 0


# ---------------------------------------------------------------------------
# GameState — immutability
# ---------------------------------------------------------------------------


def test_gamestate_is_frozen():
    gs = GameState()
    with pytest.raises(Exception):
        gs.phase = GamePhase.FLOP  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GameState — derived properties
# ---------------------------------------------------------------------------


def make_state_with_players(*players: Player) -> GameState:
    return GameState(players=players)


def test_active_players_filters_folded():
    p1 = Player(name="A", seat_idx=0, is_active=True)
    p2 = Player(name="B", seat_idx=1, is_active=False)
    p3 = Player(name="C", seat_idx=2, is_active=True)
    gs = make_state_with_players(p1, p2, p3)
    assert gs.n_active == 2
    assert {p.name for p in gs.active_players} == {"A", "C"}


def test_player_lookup():
    p = Player(name="Alice", seat_idx=3)
    gs = GameState(players=(p,))
    assert gs.player(3) is p
    assert gs.player(0) is None


# ---------------------------------------------------------------------------
# GameState — factory helpers
# ---------------------------------------------------------------------------


def test_with_players_preserves_other_fields():
    gs = GameState(phase=GamePhase.PREFLOP, small_blind=1, big_blind=2)
    new_players = (Player(name="X", seat_idx=0),)
    gs2 = gs.with_players(new_players)
    assert gs2.phase == GamePhase.PREFLOP
    assert gs2.players == new_players
    assert gs2.small_blind == 1
    assert gs2.big_blind == 2


def test_with_phase_resets_street_state():
    gs = GameState(
        phase=GamePhase.PREFLOP,
        current_bet=50,
        min_raise=20,
        last_aggressor_idx=0,
    )
    gs2 = gs.with_phase(GamePhase.FLOP)
    assert gs2.phase == GamePhase.FLOP
    assert gs2.current_bet == 0
    assert gs2.min_raise == gs2.big_blind
    assert gs2.last_aggressor_idx is None


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


def test_game_error_is_exception():
    with pytest.raises(GameError):
        raise GameError("test")


def test_error_subclass_relationships():
    assert issubclass(InvalidActionError, GameError)
    assert issubclass(IllegalAmountError, GameError)
    assert issubclass(NotYourTurnError, GameError)
    assert issubclass(PhaseError, GameError)
    assert issubclass(TableFullError, GameError)
    assert issubclass(InsufficientFundsError, GameError)
    assert issubclass(ScenarioNotFoundError, GameError)
