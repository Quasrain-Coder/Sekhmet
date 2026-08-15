"""Tests for the GTO-style Level 4 bot and its range charts."""

import random

from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.game_state import (
    ActionType, GamePhase, GameState, Player, PotState,
)
from sekhmet.ai_engine.gto_ranges import (
    BB_DEFEND_CALL, BB_DEFEND_3BET, FOUR_BET, RFI, THREE_BET,
    expand_range_spec, hand_key, range_frequency,
)
from sekhmet.ai_engine.gto_bot import GTOBot

C = lambda r, s: Card(Rank(r), Suit(s))  # noqa: E731


# ---------------------------------------------------------------------------
# Range spec parser
# ---------------------------------------------------------------------------


def test_expand_pair_plus():
    hands = expand_range_spec("77+")
    assert (14, 14, "p") in hands and (7, 7, "p") in hands
    assert (6, 6, "p") not in hands
    assert len(hands) == 8


def test_expand_pair_span():
    hands = expand_range_spec("TT-88")
    assert hands == {(10, 10, "p"), (9, 9, "p"), (8, 8, "p")}


def test_expand_kicker_plus():
    hands = expand_range_spec("A9s+")
    assert (14, 9, "s") in hands and (14, 13, "s") in hands
    assert (14, 8, "s") not in hands and (14, 9, "o") not in hands


def test_expand_connected_plus_ascends_both():
    hands = expand_range_spec("97s+")
    assert (9, 7, "s") in hands and (13, 11, "s") in hands  # 97s..KJs
    assert (13, 12, "s") not in hands  # KQs not part of the run


def test_expand_exact_hand():
    assert expand_range_spec("JTs") == {(11, 10, "s")}
    assert expand_range_spec("T9o") == {(10, 9, "o")}


def test_hand_key_and_frequency():
    assert hand_key(C(14, Suit.SPADES), C(13, Suit.SPADES)) == (14, 13, "s")
    assert hand_key(C(14, Suit.SPADES), C(13, Suit.HEARTS)) == (14, 13, "o")
    assert hand_key(C(9, Suit.SPADES), C(9, Suit.HEARTS)) == (9, 9, "p")

    btn = RFI["btn"]
    assert range_frequency(btn, C(14, Suit.SPADES), C(13, Suit.SPADES)) == 1.0
    assert range_frequency(btn, C(7, Suit.SPADES), C(2, Suit.HEARTS)) == 0.0
    assert range_frequency(btn, C(14, Suit.SPADES), C(7, Suit.HEARTS)) == 0.5  # A7o


def test_chart_shapes():
    assert len(RFI["utg"]) < len(RFI["mp"]) < len(RFI["co"]) < len(RFI["btn"])
    assert len(BB_DEFEND_CALL) > 90  # wide defense
    assert all(range_frequency(FOUR_BET, C(14, s1), C(14, s2)) == 1.0
               for s1 in Suit for s2 in Suit if s1 is not s2)
    assert (14, 14, "p") in FOUR_BET


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------


def _six_handed(bot_seat, bot_hole, dealer=5, current_bet=10, sb=5, bb=10):
    """6-handed preflop state; bot at *bot_seat*; sb=0, bb=1."""
    players = []
    for i in range(6):
        hole = tuple(bot_hole) if i == bot_seat else (
            C(14, Suit.SPADES), C(13, Suit.SPADES))
        players.append(Player(name=f"P{i}", seat_idx=i, stack=400,
                              hole_cards=hole))
    return GameState(
        phase=GamePhase.PREFLOP, players=tuple(players),
        dealer_idx=dealer, current_player_idx=bot_seat,
        current_bet=current_bet, min_raise=bb,
        small_blind=sb, big_blind=bb, sb_seat=0, bb_seat=1,
        pot=PotState(main_pot=sb + bb),
    )


def _hu_facing_raise(bot_hole, raise_to=30, bot_is_bb=True, sb=5, bb=10):
    """HU state where the bot (seat 1, BB) faces an open to *raise_to*."""
    hero = Player(name="Hero", seat_idx=0, stack=400,
                  hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)),
                  current_bet=sb, total_bet=sb)
    bot = Player(name="Bot", seat_idx=1, stack=400,
                 hole_cards=tuple(bot_hole), current_bet=bb, total_bet=bb)
    return GameState(
        phase=GamePhase.PREFLOP, players=(hero, bot),
        dealer_idx=0, current_player_idx=1,
        current_bet=raise_to, min_raise=bb,
        small_blind=sb, big_blind=bb, sb_seat=0, bb_seat=1,
        pot=PotState(main_pot=sb + raise_to),
    )


def _postflop(bot_hole, board, current_bet=0, pot=20, phase=GamePhase.FLOP,
              last_aggressor=0):
    hero = Player(name="Hero", seat_idx=0, stack=400,
                  hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)))
    bot = Player(name="Bot", seat_idx=1, stack=400,
                 hole_cards=tuple(bot_hole))
    return GameState(
        phase=phase, players=(hero, bot),
        community_cards=tuple(board),
        dealer_idx=0, current_player_idx=1,
        current_bet=current_bet, min_raise=10,
        small_blind=5, big_blind=10, sb_seat=0, bb_seat=1,
        last_aggressor_idx=last_aggressor,
        pot=PotState(main_pot=pot),
    )


# ---------------------------------------------------------------------------
# Preflop decisions
# ---------------------------------------------------------------------------


def test_utg_opens_premium_folds_trash():
    bot = GTOBot()
    aa = _six_handed(2, [C(14, Suit.HEARTS), C(14, Suit.DIAMONDS)])  # UTG
    assert bot.decide(aa, 2).type in (ActionType.RAISE, ActionType.ALL_IN)

    trash = _six_handed(2, [C(7, Suit.HEARTS), C(2, Suit.CLUBS)])
    assert bot.decide(trash, 2).type == ActionType.FOLD


def test_button_opens_wider_than_utg():
    bot = GTOBot()
    hole = [C(12, Suit.HEARTS), C(10, Suit.DIAMONDS)]  # QTo
    utg = _six_handed(2, hole)
    btn = _six_handed(5, hole)
    assert bot.decide(utg, 2).type == ActionType.FOLD
    assert bot.decide(btn, 5).type in (ActionType.RAISE, ActionType.ALL_IN)


def test_bb_defends_wide_vs_open():
    bot = GTOBot()
    # Q8o is in BB_DEFEND_CALL but never in the RFI charts.
    defend = _hu_facing_raise([C(12, Suit.HEARTS), C(8, Suit.CLUBS)])
    assert bot.decide(defend, 1).type == ActionType.CALL

    fold = _hu_facing_raise([C(7, Suit.HEARTS), C(2, Suit.CLUBS)])
    assert bot.decide(fold, 1).type == ActionType.FOLD


def test_bb_three_bets_premiums_vs_open():
    bot = GTOBot()
    state = _hu_facing_raise([C(14, Suit.HEARTS), C(14, Suit.DIAMONDS)])
    assert bot.decide(state, 1).type in (ActionType.RAISE, ActionType.ALL_IN)


def test_four_bets_and_calls_vs_three_bet():
    bot = GTOBot()
    kk = _hu_facing_raise([C(13, Suit.HEARTS), C(13, Suit.DIAMONDS)],
                          raise_to=90)
    assert bot.decide(kk, 1).type in (ActionType.RAISE, ActionType.ALL_IN)

    aqs = _hu_facing_raise([C(14, Suit.HEARTS), C(12, Suit.HEARTS)],
                           raise_to=90)
    assert bot.decide(aqs, 1).type == ActionType.CALL

    trash = _hu_facing_raise([C(7, Suit.HEARTS), C(2, Suit.CLUBS)],
                             raise_to=90)
    assert bot.decide(trash, 1).type == ActionType.FOLD


def test_bb_option_checks_limped_pot():
    bot = GTOBot()
    hole = [C(9, Suit.HEARTS), C(8, Suit.CLUBS)]
    hero = Player(name="Hero", seat_idx=0, stack=395,
                  hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)),
                  current_bet=5, total_bet=5)
    botp = Player(name="Bot", seat_idx=1, stack=390,
                  hole_cards=tuple(hole), current_bet=10, total_bet=10)
    state = GameState(
        phase=GamePhase.PREFLOP, players=(hero, botp),
        dealer_idx=0, current_player_idx=1, current_bet=10, min_raise=10,
        small_blind=5, big_blind=10, sb_seat=0, bb_seat=1,
        pot=PotState(main_pot=15),
    )
    assert bot.decide(state, 1).type == ActionType.CHECK


def test_mixed_frequency_is_deterministic_per_hand():
    """A mixed hand (e.g. 66 UTG at 50%) plays the same way every time."""
    bot = GTOBot()
    hole = [C(6, Suit.HEARTS), C(6, Suit.DIAMONDS)]
    state = _six_handed(2, hole)
    first = bot.decide(state, 2).type
    for _ in range(10):
        assert bot.decide(state, 2).type == first


# ---------------------------------------------------------------------------
# Postflop decisions
# ---------------------------------------------------------------------------


def test_value_bets_strong_hand_unopened():
    bot = GTOBot()
    # Top set on the flop vs a normal range — must bet.
    hole = [C(14, Suit.HEARTS), C(14, Suit.DIAMONDS)]
    board = [C(14, Suit.CLUBS), C(7, Suit.SPADES), C(2, Suit.HEARTS)]
    state = _postflop(hole, board)
    assert bot.decide(state, 1).type == ActionType.BET


def test_checks_air_unopened():
    bot = GTOBot()
    hole = [C(7, Suit.HEARTS), C(2, Suit.CLUBS)]
    board = [C(14, Suit.CLUBS), C(10, Suit.SPADES), C(5, Suit.HEARTS)]
    state = _postflop(hole, board)
    assert bot.decide(state, 1).type == ActionType.CHECK


def test_folds_air_to_big_bet():
    bot = GTOBot()
    hole = [C(7, Suit.HEARTS), C(2, Suit.CLUBS)]
    board = [C(14, Suit.CLUBS), C(10, Suit.SPADES), C(5, Suit.HEARTS)]
    state = _postflop(hole, board, current_bet=100, pot=20)
    assert bot.decide(state, 1).type == ActionType.FOLD


def test_calls_flush_draw_half_pot():
    bot = GTOBot()
    # Nut flush draw + two overs: a clear call at half pot in a raised pot.
    hole = [C(14, Suit.HEARTS), C(13, Suit.HEARTS)]
    board = [C(10, Suit.HEARTS), C(11, Suit.HEARTS), C(5, Suit.DIAMONDS)]
    state = _postflop(hole, board, current_bet=25, pot=50)
    assert bot.decide(state, 1).type == ActionType.CALL


def test_equity_sanity():
    bot = GTOBot()
    # AA on A72 rainbow vs the aggressor's RFI range — crushing.
    strong = _postflop([C(14, Suit.HEARTS), C(14, Suit.DIAMONDS)],
                       [C(14, Suit.CLUBS), C(7, Suit.SPADES), C(2, Suit.HEARTS)])
    eq_strong = bot._equity_vs_opponent(strong, 1,
                                        [C(14, Suit.HEARTS), C(14, Suit.DIAMONDS)])
    assert eq_strong is not None and eq_strong > 0.75

    weak = _postflop([C(7, Suit.HEARTS), C(2, Suit.CLUBS)],
                     [C(14, Suit.CLUBS), C(10, Suit.SPADES), C(5, Suit.HEARTS)])
    eq_weak = bot._equity_vs_opponent(weak, 1,
                                      [C(7, Suit.HEARTS), C(2, Suit.CLUBS)])
    assert eq_weak is not None and eq_weak < 0.3

    # Deterministic: same state twice → same estimate.
    assert eq_strong == bot._equity_vs_opponent(
        strong, 1, [C(14, Suit.HEARTS), C(14, Suit.DIAMONDS)])


def test_bet_sizing_wet_board_bigger_than_dry():
    bot = GTOBot()
    hole = [C(14, Suit.HEARTS), C(14, Suit.DIAMONDS)]
    dry_board = [C(14, Suit.CLUBS), C(7, Suit.SPADES), C(2, Suit.HEARTS)]
    wet_board = [C(14, Suit.CLUBS), C(13, Suit.CLUBS), C(12, Suit.HEARTS)]
    dry = bot.decide(_postflop(hole, dry_board), 1)
    wet = bot.decide(_postflop(hole, wet_board), 1)
    assert dry.type == wet.type == ActionType.BET
    assert wet.amount > dry.amount


# ---------------------------------------------------------------------------
# Legality fuzz — every decision must pass engine validation
# ---------------------------------------------------------------------------


def test_postflop_unopened_decisions_are_legal():
    from sekhmet.game_engine.deck import Deck
    from sekhmet.game_engine.action_processor import validate

    bot = GTOBot()
    rng = random.Random(20260808)
    for _ in range(80):
        cards = Deck().cards[:]
        rng.shuffle(cards)
        hero = Player(name="Hero", seat_idx=0, stack=400,
                      hole_cards=tuple(cards[2:4]), is_human=True)
        botp = Player(name="Bot", seat_idx=1, stack=400,
                      hole_cards=tuple(cards[:2]))
        state = GameState(
            phase=GamePhase.FLOP,
            players=(hero, botp),
            community_cards=tuple(cards[4:7]),
            dealer_idx=0, current_player_idx=1, current_bet=0,
            min_raise=10, small_blind=5, big_blind=10,
            sb_seat=0, bb_seat=1,
            pot=PotState(main_pot=20),
        )
        action = bot.decide(state, 1)
        validate(state, action)  # raises if the bot's choice is illegal


def test_preflop_facing_raise_decisions_are_legal():
    from sekhmet.game_engine.deck import Deck
    from sekhmet.game_engine.action_processor import validate

    bot = GTOBot()
    rng = random.Random(20260808)
    for _ in range(80):
        cards = Deck().cards[:]
        rng.shuffle(cards)
        state = _hu_facing_raise(cards[:2], raise_to=30)
        action = bot.decide(state, 1)
        validate(state, action)


# ---------------------------------------------------------------------------
# Registry + table wiring
# ---------------------------------------------------------------------------


def test_registry_creates_gto_bot():
    from sekhmet.ai_engine.bot_registry import create, list_bots
    assert "gto_lv4" in list_bots()
    bot = create("gto_lv4")
    assert isinstance(bot, GTOBot)
    assert bot.name == "GTOBot Lv4"


async def test_bot_level_4_sits_and_plays():
    from sekhmet.api import table_manager as tm

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=400)
    await tm.sit_down(tid, 1, "GTO", buyin=400, is_human=False, bot_level=4)
    session = await tm.get_table(tid)
    assert session.bot_levels[1] == 4

    await tm.start_hand(tid)
    # Drive until it's the human's turn or the hand ends — the L4 bot
    # must act without crashing.
    for _ in range(10):
        session = await tm.get_table(tid)
        if session.game_state.phase in (tm.GamePhase.WAITING, tm.GamePhase.SHOWDOWN):
            break
        if session.game_state.current_player_idx == 0:
            gs = session.game_state
            to_call = gs.current_bet - gs.player(0).current_bet
            await tm.handle_player_action(
                tid, 0, "CALL" if to_call > 0 else "CHECK")
        else:
            await tm.auto_bot_actions(tid)
    session = await tm.get_table(tid)
    # Either the hand ran to a conclusion or it advanced past preflop —
    # the L4 bot never crashed or froze the table.
    assert session.game_state.phase in (
        tm.GamePhase.WAITING, tm.GamePhase.SHOWDOWN,
        tm.GamePhase.FLOP, tm.GamePhase.TURN, tm.GamePhase.RIVER)
