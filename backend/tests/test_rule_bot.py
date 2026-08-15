"""Tests for the rule-based bot (all 3 levels)."""

import pytest
from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.game_state import (
    GameState, GamePhase, Player, ActionType, PotState,
)
from sekhmet.game_engine.action_processor import deal_new_hand
from sekhmet.ai_engine.rule_bot import (
    RuleBot, _preflop_strength, _made_hand_strength, _draw_outs,
    _postflop_equity,
)


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
        sb_seat=0,  # HU: dealer = SB
        bb_seat=1,
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
# Position — anchored to the real table order
# ---------------------------------------------------------------------------


def test_position_heads_up_preflop():
    """HU preflop: SB acts first (0.0), BB closes the action (1.0)."""
    state = make_heads_up_preflop()
    assert RuleBot._position(0, state) == 0.0  # SB/dealer first to act
    assert RuleBot._position(1, state) == 1.0  # BB acts last preflop


def test_position_heads_up_postflop():
    """HU postflop: BB is first to act (0.0), button acts last (1.0)."""
    state = make_postflop_state(GamePhase.FLOP)
    assert RuleBot._position(0, state) == 1.0  # dealer/button
    assert RuleBot._position(1, state) == 0.0  # BB out of position


def test_position_three_handed_wraps_around_button():
    """Seats 0,1,2 with button at 1: order is 2 → 0 → 1."""
    from sekhmet.game_engine.game_state import PotState
    players = tuple(
        Player(name=f"P{i}", seat_idx=i, stack=200, hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)))
        for i in range(3)
    )
    state = GameState(
        phase=GamePhase.FLOP,
        players=players,
        community_cards=(C(2, Suit.HEARTS), C(7, Suit.CLUBS), C(9, Suit.DIAMONDS)),
        dealer_idx=1,
        current_player_idx=2,
        current_bet=0,
        min_raise=10,
        small_blind=5,
        big_blind=10,
        pot=PotState(main_pot=15),
    )
    assert RuleBot._position(2, state) == 0.0  # first left of button
    assert RuleBot._position(0, state) == 0.5
    assert RuleBot._position(1, state) == 1.0  # button acts last


def test_position_excludes_folded_players():
    """Folded seats do not count — order is rebuilt from live seats."""
    from sekhmet.game_engine.game_state import PotState
    p0 = Player(name="Folded", seat_idx=0, stack=200, is_active=False)
    p1 = Player(name="P1", seat_idx=1, stack=200,
                hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)))
    p2 = Player(name="P2", seat_idx=2, stack=200,
                hole_cards=(C(7, Suit.HEARTS), C(2, Suit.CLUBS)))
    state = GameState(
        phase=GamePhase.FLOP,
        players=(p0, p1, p2),
        community_cards=(C(2, Suit.HEARTS), C(7, Suit.CLUBS), C(9, Suit.DIAMONDS)),
        dealer_idx=1,
        current_player_idx=1,
        current_bet=0,
        min_raise=10,
        small_blind=5,
        big_blind=10,
        pot=PotState(main_pot=15),
    )
    # Live seats are 1 (button) and 2: button acts last.
    assert RuleBot._position(2, state) == 0.0
    assert RuleBot._position(1, state) == 1.0


def test_position_folded_anchor_falls_back():
    """Button folded: first to act is the next live seat after it."""
    from sekhmet.game_engine.game_state import PotState
    p0 = Player(name="FoldedBtn", seat_idx=0, stack=200, is_active=False)
    p1 = Player(name="P1", seat_idx=1, stack=200,
                hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)))
    p2 = Player(name="P2", seat_idx=2, stack=200,
                hole_cards=(C(7, Suit.HEARTS), C(2, Suit.CLUBS)))
    state = GameState(
        phase=GamePhase.FLOP,
        players=(p0, p1, p2),
        community_cards=(C(2, Suit.HEARTS), C(7, Suit.CLUBS), C(9, Suit.DIAMONDS)),
        dealer_idx=0,  # button folded
        current_player_idx=1,
        current_bet=0,
        min_raise=10,
        small_blind=5,
        big_blind=10,
        pot=PotState(main_pot=15),
    )
    # Seats 1,2 live; first to act left of the folded button is seat 1.
    assert RuleBot._position(1, state) == 0.0
    assert RuleBot._position(2, state) == 1.0

# ---------------------------------------------------------------------------
# Postflop assessment — made-hand equity scale
# ---------------------------------------------------------------------------


def test_made_hand_strength_scale():
    """Category index is not equity: top pair is medium, trips strong."""
    board = [C(14, Suit.DIAMONDS), C(9, Suit.CLUBS), C(3, Suit.SPADES)]
    top_pair = _made_hand_strength(
        [C(14, Suit.HEARTS), C(13, Suit.HEARTS)], board)  # A + K kicker
    assert 0.45 < top_pair < 0.75

    bottom_pair = _made_hand_strength(
        [C(3, Suit.HEARTS), C(2, Suit.CLUBS)], board)
    assert bottom_pair < top_pair

    trips = _made_hand_strength(
        [C(9, Suit.HEARTS), C(9, Suit.DIAMONDS)], board)
    assert trips > 0.75  # strong

    high_card = _made_hand_strength(
        [C(7, Suit.HEARTS), C(2, Suit.CLUBS)],
        [C(14, Suit.DIAMONDS), C(10, Suit.CLUBS), C(5, Suit.SPADES)],
    )
    assert high_card < 0.45


# ---------------------------------------------------------------------------
# Draw outs
# ---------------------------------------------------------------------------


def test_draw_outs_flush_draw():
    hole = [C(2, Suit.HEARTS), C(3, Suit.HEARTS)]
    board = [C(10, Suit.HEARTS), C(11, Suit.HEARTS), C(5, Suit.DIAMONDS)]
    assert _draw_outs(hole, board) == 9


def test_draw_outs_oesd():
    hole = [C(7, Suit.HEARTS), C(8, Suit.CLUBS)]
    board = [C(9, Suit.DIAMONDS), C(10, Suit.SPADES), C(2, Suit.HEARTS)]
    assert _draw_outs(hole, board) == 8


def test_draw_outs_gutshot():
    hole = [C(5, Suit.HEARTS), C(6, Suit.CLUBS)]
    board = [C(8, Suit.DIAMONDS), C(9, Suit.SPADES), C(14, Suit.HEARTS)]
    assert _draw_outs(hole, board) == 4


def test_draw_outs_combo_not_double_counted():
    """FD+OESD: 9 flush outs + 6 non-flush straight outs = 15."""
    hole = [C(5, Suit.HEARTS), C(6, Suit.HEARTS)]
    board = [C(7, Suit.HEARTS), C(8, Suit.HEARTS), C(2, Suit.DIAMONDS)]
    assert _draw_outs(hole, board) == 15


def test_draw_outs_wheel():
    """A-2 with 3-4 on board: a 5 completes the wheel — 4 outs."""
    hole = [C(14, Suit.HEARTS), C(2, Suit.CLUBS)]
    board = [C(3, Suit.DIAMONDS), C(4, Suit.SPADES), C(9, Suit.HEARTS)]
    assert _draw_outs(hole, board) == 4


def test_postflop_equity_rule_of_four():
    """Flop (two cards to come) gives roughly double the draw equity."""
    assert _postflop_equity(0.1, 9, GamePhase.FLOP) > _postflop_equity(
        0.1, 9, GamePhase.TURN)


def test_postflop_equity_zero_on_river():
    """No cards to come on the river — draws contribute no equity."""
    assert _postflop_equity(0.1, 9, GamePhase.RIVER) == pytest.approx(0.1)


def test_draw_outs_made_straight_has_no_straight_outs():
    """A made straight does not count phantom straight outs."""
    hole = [C(7, Suit.HEARTS), C(4, Suit.CLUBS)]
    board = [C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS),
             C(3, Suit.SPADES), C(2, Suit.HEARTS)]
    assert _draw_outs(hole, board) == 0  # wheel already made


# ---------------------------------------------------------------------------
# Postflop decisions — draws and made hands vs pot odds
# ---------------------------------------------------------------------------


def _facing_bet_state(phase, bot_hole, board, bet, pot, seat=1):
    """Two-player state where the bot faces *bet* into *pot*."""
    hero = Player(name="Hero", seat_idx=0, stack=500,
                  hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)),
                  is_human=True)
    botp = Player(name="Bot", seat_idx=seat, stack=500,
                  hole_cards=tuple(bot_hole))
    return GameState(
        phase=phase,
        players=(hero, botp),
        community_cards=tuple(board),
        dealer_idx=0,
        current_player_idx=seat,
        current_bet=bet,
        min_raise=10,
        small_blind=5,
        big_blind=10,
        pot=PotState(main_pot=pot),
    )


def test_bot_l2_draw_calls_with_correct_odds():
    """L2 flush draw: calls a half-pot bet, folds to an overbet."""
    bot = RuleBot(level=2)
    hole = [C(2, Suit.HEARTS), C(3, Suit.HEARTS)]
    board = [C(10, Suit.HEARTS), C(11, Suit.HEARTS), C(5, Suit.DIAMONDS)]
    cheap = _facing_bet_state(GamePhase.FLOP, hole, board, bet=10, pot=20)
    assert bot.decide(cheap, 1).type == ActionType.CALL  # required 0.33

    over = _facing_bet_state(GamePhase.FLOP, hole, board, bet=100, pot=20)
    assert bot.decide(over, 1).type == ActionType.FOLD  # required 0.83


def test_bot_l1_chases_cheap_draw_only():
    """L1 has no pot odds: chases ≤3bb draws, folds to big bets."""
    bot = RuleBot(level=1)
    hole = [C(2, Suit.HEARTS), C(3, Suit.HEARTS)]
    board = [C(10, Suit.HEARTS), C(11, Suit.HEARTS), C(5, Suit.DIAMONDS)]
    cheap = _facing_bet_state(GamePhase.FLOP, hole, board, bet=10, pot=20)
    assert bot.decide(cheap, 1).type == ActionType.CALL

    big = _facing_bet_state(GamePhase.FLOP, hole, board, bet=60, pot=20)
    assert bot.decide(big, 1).type == ActionType.FOLD


def test_bot_top_pair_calls_small_bet():
    """Top pair is no longer treated as weak — calls a half-pot bet."""
    bot = RuleBot(level=2)
    hole = [C(14, Suit.SPADES), C(13, Suit.SPADES)]  # A + K kicker
    board = [C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS)]
    state = _facing_bet_state(GamePhase.FLOP, hole, board, bet=10, pot=20)
    assert bot.decide(state, 1).type == ActionType.CALL


def test_bot_two_pair_never_folds_reasonable_bet():
    """Two pair facing a half-pot bet: call at both L1 and L2."""
    hole = [C(14, Suit.SPADES), C(10, Suit.SPADES)]
    board = [C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS)]
    for level in (1, 2):
        bot = RuleBot(level=level)
        state = _facing_bet_state(GamePhase.FLOP, hole, board, bet=10, pot=20)
        assert bot.decide(state, 1).type == ActionType.CALL


def test_bot_gutshot_calls_with_good_odds(monkeypatch):
    """L2 gutshot (4 outs): calls a tiny bet, folds a pot-sized bet.

    The fold side depends on the bluff-catch roll — seed the RNG so a
    pot-odds fold is never overridden by a random bluff-catch.
    """
    import random
    monkeypatch.setattr("sekhmet.ai_engine.rule_bot.random",
                        random.Random(42))
    bot = RuleBot(level=2)
    hole = [C(5, Suit.SPADES), C(6, Suit.CLUBS)]
    board = [C(8, Suit.HEARTS), C(9, Suit.DIAMONDS), C(14, Suit.CLUBS)]
    cheap = _facing_bet_state(GamePhase.FLOP, hole, board, bet=2, pot=20)
    assert bot.decide(cheap, 1).type == ActionType.CALL  # required 0.09

    big = _facing_bet_state(GamePhase.FLOP, hole, board, bet=20, pot=20)
    assert bot.decide(big, 1).type == ActionType.FOLD  # required 0.50


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
        sb_seat=0, bb_seat=1,
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
    # 79o: no pair, no straight on the A-T-5-3-2 river
    # (74o would complete the A-2-3-4-5 wheel).
    players = list(state.players)
    players[1] = Player(name="Bot", seat_idx=1, stack=190,
                        hole_cards=(C(7, Suit.HEARTS), C(9, Suit.CLUBS)))
    state = GameState(
        phase=state.phase, players=tuple(players),
        community_cards=state.community_cards,
        dealer_idx=state.dealer_idx,
        current_player_idx=1, current_bet=10,
        min_raise=10, big_blind=10, small_blind=5,
        pot=state.pot,
    )
    # Run many times — should fold usually, but occasionally call.
    # With bluff_frequency=0.15, P(no call in 50) = 0.85^50 ≈ 0.03%.
    decisions = [bot.decide(state, 1).type for _ in range(50)]
    assert ActionType.FOLD in decisions  # usually folds
    assert ActionType.CALL in decisions  # occasionally bluff-catches
    assert all(d in (ActionType.FOLD, ActionType.CALL) for d in decisions)


def _weak_hand_facing_bet_state(level=None, hole=None):
    """River, bot holds a weak high-card hand facing a half-pot bet."""
    state = make_postflop_state(GamePhase.RIVER)
    players = list(state.players)
    players[1] = Player(name="Bot", seat_idx=1, stack=190,
                        hole_cards=tuple(hole))
    return GameState(
        phase=state.phase, players=tuple(players),
        community_cards=state.community_cards,
        dealer_idx=state.dealer_idx,
        current_player_idx=1, current_bet=10,
        min_raise=10, big_blind=10, small_blind=5,
        pot=state.pot,
    )


def test_bot_level2_bluff_catches_rarely():
    """L2's bluff_frequency is live now: mostly folds, occasionally calls.

    79o misses the river board (no pair, no straight), so every call
    is a genuine bluff-catch.  P(no call in 200) ≈ 0.95^200 ≈ 0.0035%.
    """
    bot = RuleBot(level=2)
    state = _weak_hand_facing_bet_state(
        hole=(C(7, Suit.HEARTS), C(9, Suit.CLUBS)))
    decisions = [bot.decide(state, 1).type for _ in range(200)]
    assert ActionType.FOLD in decisions
    assert ActionType.CALL in decisions
    assert all(d in (ActionType.FOLD, ActionType.CALL) for d in decisions)


def test_bot_level1_never_bluff_catches():
    """L1 has no bluff-catching — always folds weak hands to a bet."""
    bot = RuleBot(level=1)
    state = _weak_hand_facing_bet_state(
        hole=(C(7, Suit.HEARTS), C(9, Suit.CLUBS)))
    decisions = [bot.decide(state, 1).type for _ in range(50)]
    assert all(d == ActionType.FOLD for d in decisions)


# ---------------------------------------------------------------------------
# Adaptive bluff probabilities
# ---------------------------------------------------------------------------


class _FixedRandom:
    """Deterministic random stub — random() always returns *value*."""

    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def _pot_state(phase, pot):
    """Minimal state carrying only what the probability helpers read."""
    return GameState(
        phase=phase, players=(), community_cards=(),
        dealer_idx=0, current_player_idx=None, current_bet=0,
        min_raise=10, small_blind=5, big_blind=10,
        pot=PotState(main_pot=pot),
    )


def test_semi_bluff_prob_decreases_by_street():
    """Flop > turn > river: fewer cards to come, fewer semi-bluffs."""
    bot = RuleBot(level=3)
    flop = _pot_state(GamePhase.FLOP, 20)
    turn = _pot_state(GamePhase.TURN, 20)
    river = _pot_state(GamePhase.RIVER, 20)
    assert bot._semi_bluff_prob(flop) > bot._semi_bluff_prob(turn)
    assert bot._semi_bluff_prob(turn) > bot._semi_bluff_prob(river)


def test_semi_bluff_prob_grows_with_pot():
    """Bigger pots reward aggression — and saturate at 15bb."""
    bot = RuleBot(level=3)
    small = _pot_state(GamePhase.FLOP, 5)
    mid = _pot_state(GamePhase.FLOP, 150)
    big = _pot_state(GamePhase.FLOP, 600)
    assert bot._semi_bluff_prob(mid) > bot._semi_bluff_prob(small)
    assert bot._semi_bluff_prob(big) == bot._semi_bluff_prob(mid)  # capped


def test_bluff_catch_prob_favors_cheap_bets():
    """Small bets offer good odds → catch more; overbets → catch less."""
    bot = RuleBot(level=3)
    state = _pot_state(GamePhase.RIVER, 20)
    cheap = bot._bluff_catch_prob(state, 2)
    mid = bot._bluff_catch_prob(state, 10)
    over = bot._bluff_catch_prob(state, 40)
    assert cheap > mid > over
    assert all(0.0 <= p <= 1.0 for p in (cheap, mid, over))


def test_semi_bluff_fires_on_flop_big_pot_not_river_small(monkeypatch):
    """The adaptive probability actually gates the semi-bluff branch."""
    monkeypatch.setattr("sekhmet.ai_engine.rule_bot.random",
                        _FixedRandom(0.2))
    bot = RuleBot(level=3)
    hole = [C(2, Suit.HEARTS), C(3, Suit.HEARTS)]
    flop = [C(10, Suit.HEARTS), C(11, Suit.HEARTS), C(5, Suit.DIAMONDS)]
    big = _facing_bet_state(GamePhase.FLOP, hole, flop, bet=0, pot=150)
    assert bot.decide(big, 1).type == ActionType.BET  # prob 0.26 > 0.2

    # River with the same draw but a small pot: prob ~0.06 < 0.2 → check.
    river_board = flop + [C(9, Suit.SPADES), C(14, Suit.CLUBS)]
    small = _facing_bet_state(GamePhase.RIVER, hole, river_board,
                              bet=0, pot=20)
    assert bot.decide(small, 1).type == ActionType.CHECK


def test_bluff_catch_fires_on_cheap_bet_not_overbet(monkeypatch):
    """The price-tuned probability gates the bluff-catch branch."""
    monkeypatch.setattr("sekhmet.ai_engine.rule_bot.random",
                        _FixedRandom(0.15))
    bot = RuleBot(level=3)
    hole = [C(7, Suit.HEARTS), C(9, Suit.CLUBS)]
    board = [C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS),
             C(3, Suit.SPADES), C(2, Suit.HEARTS)]
    cheap = _facing_bet_state(GamePhase.RIVER, hole, board, bet=10, pot=20)
    assert bot.decide(cheap, 1).type == ActionType.CALL  # prob 0.175 > 0.15

    over = _facing_bet_state(GamePhase.RIVER, hole, board, bet=100, pot=20)
    assert bot.decide(over, 1).type == ActionType.FOLD  # prob 0.10 < 0.15


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


# ---------------------------------------------------------------------------
# Legality fuzz — bot decisions must pass engine validation
# ---------------------------------------------------------------------------


def _bb_option_state(bot_hole):
    """BB's option: limped pot, to_call=0 but current_bet=big_blind."""
    hero = Player(name="Hero", seat_idx=0, stack=190,
                  hole_cards=(), current_bet=10, total_bet=10, is_human=True)
    bot = Player(name="Bot", seat_idx=1, stack=190,
                 hole_cards=tuple(bot_hole), current_bet=10, total_bet=10)
    from sekhmet.game_engine.game_state import PotState
    return GameState(
        phase=GamePhase.PREFLOP,
        players=(hero, bot),
        dealer_idx=0,  # HU: hero is SB/dealer and has limped
        current_player_idx=1,
        current_bet=10,
        min_raise=10,
        small_blind=5,
        big_blind=10,
        sb_seat=0,
        bb_seat=1,
        pot=PotState(main_pot=20),
        acted_seats=(0,),
    )


def test_bb_option_produces_legal_actions():
    """Bot facing its big-blind option must not BET into the existing bet
    or CALL zero — every decision must pass engine validation."""
    import random
    from sekhmet.game_engine.deck import Deck
    from sekhmet.game_engine.action_processor import validate

    rng = random.Random(20260808)
    for level in (1, 2, 3):
        bot = RuleBot(level=level)
        for _ in range(100):
            cards = Deck().cards[:]
            rng.shuffle(cards)
            state = _bb_option_state(cards[:2])
            action = bot.decide(state, 1)
            validate(state, action)  # raises if the bot's choice is illegal


def test_postflop_unopened_pot_produces_legal_actions():
    """Unopened postflop pot (current_bet=0): bot must never RAISE."""
    import random
    from sekhmet.game_engine.deck import Deck
    from sekhmet.game_engine.action_processor import validate
    from sekhmet.game_engine.game_state import PotState

    rng = random.Random(20260808)
    for level in (1, 2, 3):
        bot = RuleBot(level=level)
        for _ in range(150):
            cards = Deck().cards[:]
            rng.shuffle(cards)
            hero = Player(name="Hero", seat_idx=0, stack=200,
                          hole_cards=tuple(cards[2:4]), is_human=True)
            botp = Player(name="Bot", seat_idx=1, stack=200,
                          hole_cards=tuple(cards[:2]))
            state = GameState(
                phase=GamePhase.FLOP,
                players=(hero, botp),
                community_cards=tuple(cards[4:7]),
                dealer_idx=0,
                current_player_idx=1,
                current_bet=0,
                min_raise=10,
                small_blind=5,
                big_blind=10,
                pot=PotState(main_pot=20),
            )
            action = bot.decide(state, 1)
            validate(state, action)  # raises if the bot's choice is illegal
