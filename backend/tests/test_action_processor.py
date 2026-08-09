"""Tests for action validation, execution, and hand dealing."""

import pytest
from sekhmet.game_engine.deck import Card, Rank, Suit, Deck
from sekhmet.game_engine.game_state import (
    Action,
    ActionType,
    GamePhase,
    GameState,
    Player,
    PotState,
    InvalidActionError,
    IllegalAmountError,
    NotYourTurnError,
    PhaseError,
)
from sekhmet.game_engine.action_processor import (
    validate,
    execute,
    deal_new_hand,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_player(name: str, seat: int, stack: int = 1000, **kw) -> Player:
    return Player(name=name, seat_idx=seat, stack=stack, **kw)


def make_state(
    *players: Player,
    phase: GamePhase = GamePhase.PREFLOP,
    current_player_idx: int = 0,
    current_bet: int = 10,
    big_blind: int = 10,
    dealer_idx: int = 0,
    **kw,
) -> GameState:
    kw.setdefault("min_raise", big_blind)
    kw.setdefault("small_blind", big_blind // 2)
    return GameState(
        phase=phase,
        players=players,
        current_player_idx=current_player_idx,
        current_bet=current_bet,
        big_blind=big_blind,
        dealer_idx=dealer_idx,
        **kw,
    )


# ---------------------------------------------------------------------------
# Validation — basic legality
# ---------------------------------------------------------------------------


def test_fold_is_legal():
    p = make_player("A", 0)
    state = make_state(p, current_player_idx=0)
    validate(state, Action(0, ActionType.FOLD))


def test_check_when_nothing_to_call():
    p = make_player("A", 0)
    state = make_state(p, current_player_idx=0, current_bet=0)
    validate(state, Action(0, ActionType.CHECK))


def test_check_when_bet_faces_player_raises():
    p = make_player("A", 0)
    state = make_state(p, current_player_idx=0, current_bet=10)
    with pytest.raises(InvalidActionError, match="Cannot check"):
        validate(state, Action(0, ActionType.CHECK))


def test_call_matches_current_bet():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=10)
    validate(state, Action(0, ActionType.CALL, amount=10))


def test_call_with_nothing_to_call_raises():
    p = make_player("A", 0)
    state = make_state(p, current_player_idx=0, current_bet=0)
    with pytest.raises(InvalidActionError, match="Nothing to call"):
        validate(state, Action(0, ActionType.CALL))


def test_bet_when_no_bet_open():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=0)
    validate(state, Action(0, ActionType.BET, amount=20))


def test_bet_below_big_blind_raises():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=0, big_blind=10)
    with pytest.raises(IllegalAmountError, match="Minimum bet"):
        validate(state, Action(0, ActionType.BET, amount=5))


def test_bet_exceeds_stack_raises():
    p = make_player("A", 0, stack=50)
    state = make_state(p, current_player_idx=0, current_bet=0, big_blind=10)
    with pytest.raises(IllegalAmountError, match="exceeds available"):
        validate(state, Action(0, ActionType.BET, amount=60))


def test_raise_when_no_bet_raises():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=0)
    with pytest.raises(InvalidActionError, match="Nothing to raise"):
        validate(state, Action(0, ActionType.RAISE, amount=20))


def test_raise_below_min_raises_error():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=10, min_raise=10)
    # Min raise is to 20 (current_bet 10 + min_raise 10)
    with pytest.raises(IllegalAmountError, match="Minimum raise"):
        validate(state, Action(0, ActionType.RAISE, amount=15))


def test_valid_raise():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=10, min_raise=10)
    validate(state, Action(0, ActionType.RAISE, amount=25))


def test_all_in_always_legal():
    p = make_player("A", 0, stack=50)
    state = make_state(p, current_player_idx=0, current_bet=100)
    validate(state, Action(0, ActionType.ALL_IN))


# ---------------------------------------------------------------------------
# Validation — turn / phase errors
# ---------------------------------------------------------------------------


def test_not_your_turn_raises():
    p1 = make_player("A", 0)
    p2 = make_player("B", 1)
    state = make_state(p1, p2, current_player_idx=0)
    with pytest.raises(NotYourTurnError):
        validate(state, Action(1, ActionType.FOLD))


def test_cannot_act_during_showdown():
    p = make_player("A", 0)
    state = make_state(p, phase=GamePhase.SHOWDOWN, current_player_idx=0)
    with pytest.raises(PhaseError):
        validate(state, Action(0, ActionType.FOLD))


def test_cannot_act_during_waiting():
    p = make_player("A", 0)
    state = GameState(phase=GamePhase.WAITING, players=(p,), current_player_idx=0)
    with pytest.raises(PhaseError):
        validate(state, Action(0, ActionType.FOLD))


def test_folded_player_cannot_act():
    p = make_player("A", 0, is_active=False)
    state = make_state(p, current_player_idx=0)
    with pytest.raises(InvalidActionError, match="Folded"):
        validate(state, Action(0, ActionType.FOLD))


def test_allin_player_cannot_act():
    p = make_player("A", 0, is_all_in=True)
    state = make_state(p, current_player_idx=0)
    with pytest.raises(InvalidActionError, match="All-in"):
        validate(state, Action(0, ActionType.FOLD))


# ---------------------------------------------------------------------------
# Execution — state transitions
# ---------------------------------------------------------------------------


def test_execute_fold_removes_player():
    p1 = make_player("A", 0, stack=100)
    p2 = make_player("B", 1, stack=100)
    state = make_state(p1, p2, current_player_idx=0, current_bet=0)
    new_state = execute(state, Action(0, ActionType.FOLD))
    # Player 0 should be inactive
    p0_new = new_state.player(0)
    assert p0_new is not None
    assert not p0_new.is_active


def test_execute_call_updates_stack_and_pot():
    p1 = make_player("A", 0, stack=100)
    p2 = make_player("B", 1, stack=100, current_bet=10)
    # Pot should already reflect B's 10-chip bet from a prior action.
    # B has already acted this round (acted_seats), so A's call both
    # equalizes the bets and closes the round → phase advances.
    state = make_state(p1, p2, current_player_idx=0, current_bet=10,
                       pot=PotState(main_pot=10), acted_seats=(1,))
    new_state = execute(state, Action(0, ActionType.CALL))
    p0_new = new_state.player(0)
    assert p0_new is not None
    assert p0_new.stack == 90
    assert p0_new.total_bet == 10  # accumulated across streets
    assert new_state.pot.main_pot == 20  # 10 (B's prior) + 10 (A's call)
    assert new_state.phase == GamePhase.FLOP  # phase advanced


def test_execute_raise_updates_betting():
    p1 = make_player("A", 0, stack=100)
    p2 = make_player("B", 1, stack=100)
    state = make_state(p1, p2, current_player_idx=0, current_bet=10, min_raise=10)
    new_state = execute(state, Action(0, ActionType.RAISE, amount=30))
    assert new_state.current_bet == 30
    assert new_state.last_aggressor_idx == 0


def test_execute_all_in_sets_flag():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=10)
    new_state = execute(state, Action(0, ActionType.ALL_IN))
    p0_new = new_state.player(0)
    assert p0_new is not None
    assert p0_new.is_all_in
    assert p0_new.stack == 0


def test_execute_records_history():
    p = make_player("A", 0, stack=100)
    state = make_state(p, current_player_idx=0, current_bet=0)
    new_state = execute(state, Action(0, ActionType.CHECK))
    assert len(new_state.round_history) == 1
    assert new_state.round_history[0].type == ActionType.CHECK


# ---------------------------------------------------------------------------
# Execution — phase transitions
# ---------------------------------------------------------------------------


def test_last_player_folds_triggers_showdown():
    p1 = make_player("A", 0, stack=100)
    p2 = make_player("B", 1, stack=100)
    state = make_state(p1, p2, current_player_idx=0, current_bet=0)
    new_state = execute(state, Action(0, ActionType.FOLD))
    assert new_state.phase == GamePhase.SHOWDOWN


def test_both_call_advances_preflop_to_flop():
    """When remaining player checks (no bet to call), phase advances.

    Scenario: 2 players, both have already matched the BB (current_bet=10)
    and B has already acted this round.  Player A checks → all bets equal
    and everyone has acted → phase advances.
    """
    p1 = make_player("A", 0, stack=100, current_bet=10)
    p2 = make_player("B", 1, stack=100, current_bet=10)
    state = make_state(p1, p2, current_player_idx=0, current_bet=10, dealer_idx=0,
                       acted_seats=(1,))
    state = execute(state, Action(0, ActionType.CHECK))
    # All bets equal at 10, phase advances
    assert state.phase == GamePhase.FLOP


def test_players_all_in_goes_to_showdown():
    p1 = make_player("A", 0, stack=100, is_all_in=True, current_bet=10)
    p2 = make_player("B", 1, stack=100, current_bet=10)
    p3 = make_player("C", 2, stack=100, is_all_in=True, current_bet=10)
    state = make_state(p1, p2, p3, current_player_idx=1, current_bet=10, dealer_idx=2)
    # Player B is the only one who can act; checks → all bets equal → advance
    state = execute(state, Action(1, ActionType.CHECK))
    assert state.phase in (GamePhase.FLOP, GamePhase.SHOWDOWN)


# ---------------------------------------------------------------------------
# deal_new_hand
# ---------------------------------------------------------------------------


def test_deal_new_hand_basic():
    p1 = make_player("A", 0, stack=1000)
    p2 = make_player("B", 1, stack=1000)
    p3 = make_player("C", 2, stack=1000)
    state = GameState(
        phase=GamePhase.WAITING,
        players=(p1, p2, p3),
        dealer_idx=0,
        small_blind=5,
        big_blind=10,
    )
    deck = Deck()
    deck.shuffle()
    new_state = deal_new_hand(state, deck.cards[:], dealer_idx=0)

    assert new_state.phase == GamePhase.PREFLOP
    # Everyone has hole cards
    for p in new_state.players:
        assert p.hole_cards is not None
        assert len(p.hole_cards) == 2  # type: ignore[arg-type]
    # SB posted
    sb = new_state.player(1)
    assert sb is not None and sb.total_bet == 5
    # BB posted
    bb = new_state.player(2)
    assert bb is not None and bb.total_bet == 10
    # Pot has blinds
    assert new_state.pot.main_pot == 15


def test_deal_requires_waiting_phase():
    state = GameState(phase=GamePhase.PREFLOP)
    with pytest.raises(PhaseError):
        deal_new_hand(state, [], 0)


def test_deal_requires_2_players():
    state = GameState(
        phase=GamePhase.WAITING,
        players=(make_player("A", 0),),
    )
    with pytest.raises(InvalidActionError, match="at least 2"):
        deal_new_hand(state, [Card(Rank.ACE, Suit.SPADES)] * 4, 0)


def test_deal_short_stack_blinds():
    """Player with only 3 chips posts what they can."""
    p1 = make_player("A", 0, stack=1000)
    p2 = make_player("B", 1, stack=3)  # short stack in SB
    p3 = make_player("C", 2, stack=1000)
    state = GameState(
        phase=GamePhase.WAITING,
        players=(p1, p2, p3),
        dealer_idx=0,
        small_blind=5,
        big_blind=10,
    )
    deck = Deck()
    deck.shuffle()
    new_state = deal_new_hand(state, deck.cards[:], dealer_idx=0)

    sb = new_state.player(1)
    assert sb is not None
    assert sb.total_bet == 3  # all they could post
    assert sb.is_all_in


# ---------------------------------------------------------------------------
# Integration: a simple heads-up hand flow
# ---------------------------------------------------------------------------


def test_heads_up_hand_flow():
    """Simulate a complete heads-up hand: deal → raise → fold → showdown.

    HU rules: dealer = SB (seat 0), BB = seat 1.
    SB acts first preflop, BB acts second.
    """
    p1 = make_player("Hero", 0, stack=200)
    p2 = make_player("Bot", 1, stack=200)
    state = GameState(
        phase=GamePhase.WAITING,
        players=(p1, p2),
        dealer_idx=0,
        small_blind=5,
        big_blind=10,
    )

    # Deal — HU: dealer=SB=seat0 posts 5, BB=seat1 posts 10
    deck = Deck()
    deck.shuffle()
    state = deal_new_hand(state, deck.cards[:], dealer_idx=0)
    assert state.phase == GamePhase.PREFLOP
    # First to act preflop in HU: SB (seat 0)
    assert state.current_player_idx == 0

    # Hero (SB) raises to 30 total (posts additional 25)
    state = execute(state, Action(0, ActionType.RAISE, amount=30))
    assert state.current_bet == 30
    assert state.player(0).current_bet == 30  # type: ignore[union-attr]
    assert state.player(0).stack == 170  # type: ignore[union-attr]  # 200 - 30

    # Bot folds
    state = execute(state, Action(1, ActionType.FOLD))
    assert state.phase == GamePhase.SHOWDOWN
    hero = state.player(0)
    assert hero is not None and hero.is_active
    bot = state.player(1)
    assert bot is not None and not bot.is_active


def test_deal_skips_zero_stack_player():
    """Busted players sit out: no hole cards, no blinds, stays inactive."""
    p1 = make_player("A", 0, stack=200)
    p2 = make_player("B", 1, stack=0)    # busted — holds the SB seat
    p3 = make_player("C", 2, stack=200)
    state = GameState(
        phase=GamePhase.WAITING,
        players=(p1, p2, p3),
        dealer_idx=0, small_blind=5, big_blind=10,
    )
    deck = Deck(); deck.shuffle()
    new_state = deal_new_hand(state, deck.cards[:], dealer_idx=0)

    busted = new_state.player(1)
    assert busted is not None
    assert busted.hole_cards in (None, ())
    assert busted.is_active is False
    assert busted.current_bet == 0 and busted.total_bet == 0
    # SB 是爆掉玩家 → 死盲注不收（不重排），只有 BB 的 10 入池
    assert new_state.pot.main_pot == 10
    # 有筹码的玩家都拿到了底牌
    for p in new_state.players:
        if p.stack > 0:
            assert p.hole_cards is not None and len(p.hole_cards) == 2


def test_deal_requires_two_players_with_chips():
    p1 = make_player("A", 0, stack=200)
    p2 = make_player("B", 1, stack=0)
    state = GameState(phase=GamePhase.WAITING, players=(p1, p2))
    with pytest.raises(InvalidActionError, match="at least 2"):
        deal_new_hand(state, Deck().cards[:], 0)
