"""Tests for the table sweeper (zombie cleanup + stuck-hand completion)."""

import time

from sekhmet.config import app_config
from sekhmet.api import table_manager as tm
from sekhmet.game_engine import GamePhase, GameState, Player, PotState


async def test_idle_table_closed_immediately():
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    session.last_activity = time.monotonic() - app_config.game.room_idle_timeout_seconds - 60

    closed = await tm.sweep_idle_tables()
    assert tid in closed
    assert await tm.get_table(tid) is None


async def test_empty_room_needs_continuous_grace():
    tid = await tm.create_table()
    session = await tm.get_table(tid)

    # First sweep only marks the room as zombie.
    assert await tm.sweep_idle_tables() == []
    assert session.zombie_since is not None

    # Activity clears the mark.
    await tm.touch(tid)
    session.zombie_since = None
    assert await tm.sweep_idle_tables() == []
    assert session.zombie_since is not None

    # Backdate past the grace period → closed.
    session.zombie_since = time.monotonic() - app_config.game.empty_room_timeout_seconds - 1
    closed = await tm.sweep_idle_tables()
    assert tid in closed


async def test_bots_only_orphan_closed():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Bot", buyin=200, is_human=False)
    session = await tm.get_table(tid)
    session.zombie_since = time.monotonic() - app_config.game.orphan_room_timeout_seconds - 1

    closed = await tm.sweep_idle_tables()
    assert tid in closed


async def test_room_with_human_seat_is_not_a_zombie():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    session = await tm.get_table(tid)
    session.zombie_since = time.monotonic() - 10_000  # long dead

    assert await tm.sweep_idle_tables() == []  # humans never auto-closed
    assert session.zombie_since is None


def _stuck_runout_state() -> GameState:
    """Two players all-in preflop; flop dealt; nobody left to act."""
    from sekhmet.game_engine.deck import Card, Rank, Suit

    hero = Player(name="Hero", seat_idx=0, stack=0, is_all_in=True,
                  is_active=True, current_bet=0, total_bet=200,
                  hole_cards=(Card(Rank(14), Suit.SPADES), Card(Rank(13), Suit.SPADES)))
    bot = Player(name="Bot", seat_idx=1, stack=0, is_all_in=True,
                 is_active=True, current_bet=0, total_bet=200,
                 hole_cards=(Card(Rank(2), Suit.HEARTS), Card(Rank(7), Suit.CLUBS)))
    return GameState(
        phase=GamePhase.FLOP,
        players=(hero, bot),
        community_cards=(Card(Rank(9), Suit.HEARTS), Card(Rank(9), Suit.DIAMONDS),
                         Card(Rank(3), Suit.CLUBS)),
        deck=(Card(Rank(5), Suit.SPADES), Card(Rank(10), Suit.DIAMONDS),
              Card(Rank(4), Suit.HEARTS), Card(Rank(6), Suit.CLUBS)),
        current_player_idx=None,
        dealer_idx=0,
        pot=PotState(main_pot=400),
        small_blind=5, big_blind=10, sb_seat=0, bb_seat=1,
    )


async def test_stuck_runout_is_completed_not_closed():
    gs = _stuck_runout_state()
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    session.game_state = gs
    session.zombie_since = time.monotonic() - app_config.game.stuck_hand_timeout_seconds - 1

    # First sweep completes the hand instead of closing the room.
    assert await tm.sweep_idle_tables() == []
    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.phase == GamePhase.SHOWDOWN
    # The winner took the pot: stacks reflect the award.
    stacks = {p.seat_idx: p.stack for p in session.game_state.players}
    assert 400 in stacks.values()  # one player won the whole 400 pot


async def test_stuck_hand_grace_is_continuous():
    gs = _stuck_runout_state()
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    session.game_state = gs

    # First sweep: marks the stuck hand but does nothing yet.
    assert await tm.sweep_idle_tables() == []
    assert session.zombie_since is not None
    assert session.game_state.phase == GamePhase.FLOP
