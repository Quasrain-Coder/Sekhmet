"""Tests for the cross-hand opponent model (VPIP/PFR/fold rates)."""

import asyncio

from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.game_state import (
    Action, ActionType, GamePhase, GameState, Player, PotState,
)
from sekhmet.ai_engine.stats_tracker import OpponentStats, OpponentStatsTracker
from sekhmet.ai_engine.rule_bot import RuleBot

C = lambda r, s: Card(Rank(r), Suit(s))  # noqa: E731


def _preflop_state(current_bet=10, current_player_idx=0):
    """HU preflop state; seat 0 (SB) is first to act."""
    sb = Player(name="Hero", seat_idx=0, stack=195, current_bet=5,
                total_bet=5, hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)))
    bb = Player(name="Bot", seat_idx=1, stack=190, current_bet=10,
                total_bet=10, hole_cards=(C(7, Suit.HEARTS), C(2, Suit.CLUBS)))
    return GameState(
        phase=GamePhase.PREFLOP, players=(sb, bb),
        dealer_idx=0, current_player_idx=current_player_idx,
        current_bet=current_bet, min_raise=10,
        small_blind=5, big_blind=10, sb_seat=0, bb_seat=1,
        pot=PotState(main_pot=15),
    )


def _postflop_state(current_bet=10):
    """HU flop state; seat 1 faces *current_bet*."""
    hero = Player(name="Hero", seat_idx=0, stack=190,
                  hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)))
    bot = Player(name="Bot", seat_idx=1, stack=190,
                 hole_cards=(C(7, Suit.HEARTS), C(2, Suit.CLUBS)))
    return GameState(
        phase=GamePhase.FLOP, players=(hero, bot),
        community_cards=(C(14, Suit.HEARTS), C(10, Suit.CLUBS), C(5, Suit.DIAMONDS)),
        dealer_idx=0, current_player_idx=1,
        current_bet=current_bet, min_raise=10,
        small_blind=5, big_blind=10,
        pot=PotState(main_pot=20),
    )


# ---------------------------------------------------------------------------
# Tracker unit tests
# ---------------------------------------------------------------------------


def test_tracker_accumulates_vpip_and_pfr():
    t = OpponentStatsTracker()
    t.new_hand([0, 1])
    t.observe(_preflop_state(), Action(0, ActionType.CALL))    # hand 1: VPIP
    t.new_hand([0, 1])
    t.observe(_preflop_state(), Action(0, ActionType.RAISE))   # hand 2: VPIP+PFR
    t.new_hand([0, 1])
    t.observe(_preflop_state(), Action(0, ActionType.FOLD))    # hand 3: neither
    t.new_hand([0, 1])

    s = t.stats[0]
    assert s.hands == 4  # one increment per new_hand call
    assert s.vpip == 2
    assert s.pfr == 1
    assert s.pfr_rate() < s.vpip_rate()


def test_tracker_fold_to_bet_and_aggression():
    t = OpponentStatsTracker()
    t.new_hand([0, 1])
    t.observe(_postflop_state(current_bet=10), Action(1, ActionType.FOLD))
    t.observe(_postflop_state(current_bet=10), Action(1, ActionType.RAISE))
    t.observe(_postflop_state(current_bet=10), Action(1, ActionType.CALL))

    s = t.stats[1]
    assert s.faced_bets == 3
    assert s.folds_to_bet == 1
    assert s.raises_facing_bet == 1
    assert s.aggression_rate() > 0.3


def test_tracker_counts_bets_into_unopened_pots():
    t = OpponentStatsTracker()
    t.new_hand([0, 1])
    t.observe(_postflop_state(current_bet=0), Action(1, ActionType.BET, amount=10))
    assert t.stats[1].bets_unopened == 1


def test_tracker_rates_are_smoothed_when_empty():
    s = OpponentStats()
    assert 0.0 < s.vpip_rate() < 1.0
    assert 0.0 < s.fold_to_bet_rate() < 1.0


# ---------------------------------------------------------------------------
# RuleBot reads the opponent model
# ---------------------------------------------------------------------------


def _draw_state():
    """Flop, seat 1 holds a flush draw, unopened pot."""
    hero = Player(name="Hero", seat_idx=0, stack=300,
                  hole_cards=(C(14, Suit.SPADES), C(13, Suit.SPADES)))
    bot = Player(name="Bot", seat_idx=1, stack=300,
                 hole_cards=(C(2, Suit.HEARTS), C(3, Suit.HEARTS)))
    return GameState(
        phase=GamePhase.FLOP, players=(hero, bot),
        community_cards=(C(10, Suit.HEARTS), C(11, Suit.HEARTS), C(5, Suit.DIAMONDS)),
        dealer_idx=0, current_player_idx=1, current_bet=0, min_raise=10,
        small_blind=5, big_blind=10, pot=PotState(main_pot=20),
    )


def _tight_opponent_tracker():
    """Opponent folds to most postflop bets."""
    t = OpponentStatsTracker()
    t.new_hand([0, 1])
    for _ in range(6):
        t.observe(_postflop_state(current_bet=10), Action(0, ActionType.FOLD))
    return t


def _aggressive_opponent_tracker():
    """Opponent raises most postflop bets they face."""
    t = OpponentStatsTracker()
    t.new_hand([0, 1])
    for _ in range(6):
        t.observe(_postflop_state(current_bet=10), Action(0, ActionType.RAISE))
    return t


def test_semi_bluff_more_vs_tight_opponent():
    base = RuleBot(level=3)
    tuned = RuleBot(level=3, stats=_tight_opponent_tracker())
    state = _draw_state()
    assert tuned._semi_bluff_prob(state, 1) > base._semi_bluff_prob(state, 1)


def test_bluff_catch_more_vs_aggressive_opponent():
    base = RuleBot(level=3)
    tuned = RuleBot(level=3, stats=_aggressive_opponent_tracker())
    state = _postflop_state(current_bet=10)
    assert tuned._bluff_catch_prob(state, 10, 1) > base._bluff_catch_prob(state, 10, 1)


def test_no_stats_tracker_means_baseline_probabilities():
    bot = RuleBot(level=3)
    state = _draw_state()
    assert bot._semi_bluff_prob(state, 1) > 0.0
    assert bot._opponent_stats(state, 1) is None


def test_opponent_stats_prefers_last_aggressor():
    t = OpponentStatsTracker()
    t.new_hand([0, 1])
    t.observe(_postflop_state(current_bet=10), Action(0, ActionType.BET, amount=10))
    bot = RuleBot(level=3, stats=t)
    state = _postflop_state(current_bet=10)
    state = GameState(
        phase=state.phase, players=state.players,
        community_cards=state.community_cards, dealer_idx=state.dealer_idx,
        current_player_idx=1, current_bet=10, min_raise=10,
        small_blind=5, big_blind=10, pot=state.pot,
        last_aggressor_idx=0,
    )
    assert bot._opponent_stats(state, 1) is t.stats[0]


# ---------------------------------------------------------------------------
# table_manager wiring
# ---------------------------------------------------------------------------


async def test_table_session_tracks_hands_and_actions():
    """Sitting down, dealing, and acting all feed the session tracker."""
    from sekhmet.api import table_manager as tm

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False, bot_level=2)
    await tm.start_hand(tid)

    session = await tm.get_table(tid)
    assert session.tracker.stats[0].hands == 1
    assert session.tracker.stats[1].hands == 1

    # Drive until the human is to act preflop.  A bot acting first may
    # fold the hand out — deal again and retry.
    for _ in range(6):
        session = await tm.get_table(tid)
        if session.game_state.phase in (tm.GamePhase.WAITING, tm.GamePhase.SHOWDOWN):
            await tm.start_hand(tid)
            session = await tm.get_table(tid)
        if session.game_state.current_player_idx == 0:
            break
        await tm.auto_bot_actions(tid)
    session = await tm.get_table(tid)
    assert session.game_state.current_player_idx == 0

    # Raise: always legal preflop (SB facing a bet or BB with option)
    # and always a VPIP+PFR event for the tracker.
    await tm.handle_player_action(
        tid, 0, "RAISE",
        amount=session.game_state.current_bet + session.game_state.min_raise,
    )
    session = await tm.get_table(tid)
    assert session.tracker.stats[0]._vpip_this_hand
    assert session.tracker.stats[0]._pfr_this_hand

    # The bot responds — its action is observed too.
    await tm.auto_bot_actions(tid)
    session = await tm.get_table(tid)
    assert session.tracker.stats[1].actions > 0


async def test_stand_up_drops_tracker_entry():
    from sekhmet.api import table_manager as tm

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False, bot_level=2)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert 1 in session.tracker.stats
    tm._stand_up_locked(session, 1)  # mid-hand removal path under the lock
    assert 1 not in session.tracker.stats
