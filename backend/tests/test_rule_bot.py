"""Tests for the rule-based bot (all 3 levels)."""

import pytest
from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.game_state import (
    GameState, GamePhase, Player, ActionType,
)
from sekhmet.game_engine.action_processor import deal_new_hand
from sekhmet.ai_engine.rule_bot import RuleBot, _preflop_strength


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

C = lambda r, s: Card(Rank(r), Suit(s))  # noqa: E731


def make_heads_up_preflop(hero_cards=None, bot_cards=None,
                          hero_stack=200, bot_stack=200,
                          dealer=0, sb=5, bb=10):
    """Create a 2-player state at PREFLOP with cards dealt."""
    if hero_cards is None:
        hero_cards = [C(14, Suit.SPADES), C(13, Suit.SPADES)]  # AKs
    if bot_cards is None:
        bot_cards = [C(7, Suit.HEARTS), C(2, Suit.CLUBS)]  # 72o

    # Build state with cards we control
    p1 = Player(name="Hero", seat_idx=0, stack=hero_stack,
                hole_cards=tuple(hero_cards), is_human=True)
    p2 = Player(name="Bot", seat_idx=1, stack=bot_stack,
                hole_cards=tuple(bot_cards))

    # Simulate deal — post blinds manually
    # HU: dealer=SB=seat0, BB=seat1
    p1 = Player(name="Hero", seat_idx=0, stack=hero_stack - sb,
                hole_cards=tuple(hero_cards), current_bet=sb, total_bet=sb,
                is_human=True)
    p2 = Player(name="Bot", seat_idx=1, stack=bot_stack - bb,
                hole_cards=tuple(bot_cards), current_bet=bb, total_bet=bb)

    from sekhmet.game_engine.game_state import PotState
    return GameState(
        phase=GamePhase.PREFLOP,
        players=(p1, p2),
        dealer_idx=dealer,
        current_player_idx=dealer,  # SB acts first in HU
        current_bet=bb,
        min_raise=bb,
        small_blind=sb,
        big_blind=bb,
        pot=PotState(main_pot=sb + bb),
    )


def make_postflop_state(phase=GamePhase.FLOP):
    """Make a 2-player postflop state with community cards."""
    community = {
        GamePhase.FLOP: [C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS)],
        GamePhase.TURN: [C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS), C(3, Suit.SPADES)],
        GamePhase.RIVER: [C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS), C(3, Suit.SPADES), C(2, Suit.HEARTS)],
    }
    cards = community[phase]

    p1 = Player(name="Hero", seat_idx=0, stack=190,
                hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)),
                is_human=True)
    p2 = Player(name="Bot", seat_idx=1, stack=190,
                hole_cards=(C(10, Suit.HEARTS), C(10, Suit.DIAMONDS)))

    from sekhmet.game_engine.game_state import PotState
    return GameState(
        phase=phase,
        players=(p1, p2),
        community_cards=tuple(cards),
        dealer_idx=0,
        current_player_idx=0,
        current_bet=0,
        min_raise=10,
        big_blind=10,
        small_blind=5,
        pot=PotState(main_pot=20),
    )


# ---------------------------------------------------------------------------
# Preflop strength heuristic
# ---------------------------------------------------------------------------


def test_preflop_strength_aces():
    assert _preflop_strength([C(14, Suit.SPADES), C(14, Suit.HEARTS)]) > 0.8


def test_preflop_strength_seven_two_offsuit():
    assert _preflop_strength([C(7, Suit.HEARTS), C(2, Suit.CLUBS)]) < 0.3


def test_preflop_strength_suited_connector():
    s1 = _preflop_strength([C(9, Suit.HEARTS), C(8, Suit.HEARTS)])
    s2 = _preflop_strength([C(9, Suit.HEARTS), C(8, Suit.CLUBS)])
    assert s1 > s2  # suited > offsuit


def test_preflop_strength_premium_pair():
    aa = _preflop_strength([C(14, Suit.SPADES), C(14, Suit.HEARTS)])
    kk = _preflop_strength([C(13, Suit.SPADES), C(13, Suit.HEARTS)])
    assert aa > kk


# ---------------------------------------------------------------------------
# RuleBot — basic
# ---------------------------------------------------------------------------


def test_bot_creation():
    bot = RuleBot(level=1)
    assert bot.name == "RuleBot Lv1"
    assert "ABC" in bot.style_description


def test_bot_invalid_level():
    with pytest.raises(ValueError, match="1–3"):
        RuleBot(level=0)
    with pytest.raises(ValueError, match="1–3"):
        RuleBot(level=4)


def test_bot_folds_trash_preflop():
    """With 72o facing a bet, should fold."""
    bot = RuleBot(level=1)
    state = make_heads_up_preflop(
        hero_cards=[C(14, Suit.SPADES), C(13, Suit.SPADES)],
        bot_cards=[C(7, Suit.HEARTS), C(2, Suit.CLUBS)],
    )
    # Bot is seat 1, SB raised (need to set up state where there's a bet to face)
    # Actually, bot is BB and already has 10 in. Hero is SB and checks (no bet).
    # Let's create a state where hero raised
    p1 = Player(name="Hero", seat_idx=0, stack=170,
                hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)),
                current_bet=30, total_bet=30, is_human=True)
    p2 = Player(name="Bot", seat_idx=1, stack=190,
                hole_cards=(C(7, Suit.HEARTS), C(2, Suit.CLUBS)),
                current_bet=10, total_bet=10)
    from sekhmet.game_engine.game_state import PotState
    state = GameState(
        phase=GamePhase.PREFLOP, players=(p1, p2),
        current_player_idx=1, current_bet=30, min_raise=10,
        big_blind=10, small_blind=5, dealer_idx=0,
        pot=PotState(main_pot=40),
    )
    action = bot.decide(state, 1)
    assert action.type == ActionType.FOLD


def test_bot_raises_premium_preflop():
    """With AKs and no bet, should raise."""
    bot = RuleBot(level=1)
    state = make_heads_up_preflop(
        hero_cards=[C(14, Suit.SPADES), C(13, Suit.SPADES)],
        bot_cards=[C(7, Suit.HEARTS), C(2, Suit.CLUBS)],
    )
    action = bot.decide(state, 0)  # seat 0 is first to act with AKs
    assert action.type in (ActionType.RAISE, ActionType.BET)


def test_bot_level2_uses_pot_odds():
    """Level 2 bot folds weak draw when pot odds are bad."""
    bot = RuleBot(level=2)
    # Bot has 72o on A-T-5 board (almost no equity)
    state = make_postflop_state(GamePhase.FLOP)
    # Change bot's cards to 72o
    players = list(state.players)
    players[1] = Player(name="Bot", seat_idx=1, stack=190,
                        hole_cards=(C(7, Suit.HEARTS), C(2, Suit.CLUBS)))
    state = GameState(
        phase=state.phase, players=tuple(players),
        community_cards=state.community_cards,
        dealer_idx=state.dealer_idx,
        current_player_idx=1, current_bet=50,  # facing a big bet
        min_raise=10, big_blind=10, small_blind=5,
        pot=state.pot,
    )
    action = bot.decide(state, 1)
    assert action.type == ActionType.FOLD


def test_bot_level3_can_bluff():
    """Level 3 bot occasionally calls with weak hands (bluff catch)."""
    bot = RuleBot(level=3)
    state = make_postflop_state(GamePhase.RIVER)
    # Give bot very weak hand
    players = list(state.players)
    players[1] = Player(name="Bot", seat_idx=1, stack=190,
                        hole_cards=(C(7, Suit.HEARTS), C(2, Suit.CLUBS)))
    state = GameState(
        phase=state.phase, players=tuple(players),
        community_cards=state.community_cards,
        dealer_idx=state.dealer_idx,
        current_player_idx=1, current_bet=10,
        min_raise=10, big_blind=10, small_blind=5,
        pot=state.pot,
    )
    # Run many times — should fold usually, but occasionally call
    decisions = [bot.decide(state, 1).type for _ in range(50)]
    # With bluff_frequency=0.15, expect some calls
    assert ActionType.FOLD in decisions  # usually folds
    # May have some CALLs (not guaranteed, but likely over 50 runs)
    # At minimum, it should produce valid actions
    assert all(d in (ActionType.FOLD, ActionType.CALL) for d in decisions)


def test_bot_all_three_levels_return_valid_actions():
    """Sanity: all levels produce valid actions in common spots."""
    for lv in [1, 2, 3]:
        bot = RuleBot(level=lv)
        # Preflop
        state = make_heads_up_preflop()
        a = bot.decide(state, 0)
        assert a.player_idx == 0
        assert isinstance(a.type, ActionType)

        # Postflop with no bet facing
        state2 = make_postflop_state(GamePhase.FLOP)
        a2 = bot.decide(state2, 0)
        assert a2.player_idx == 0
        assert isinstance(a2.type, ActionType)
