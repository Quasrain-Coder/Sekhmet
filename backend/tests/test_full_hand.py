"""End-to-end tests: play complete hands and assert poker-level invariants.

These tests exist because unit tests alone let three engine bugs ship:
community cards were never dealt, the big blind's option was skipped,
and all-in runouts stalled with ``current_player_idx=None``.
"""

import pytest

from sekhmet.api import table_manager as tm
from sekhmet.game_engine.deck import Deck
from sekhmet.game_engine.game_state import (
    Action,
    ActionType,
    GamePhase,
    GameState,
    Player,
    PotState,
)
from sekhmet.game_engine.action_processor import deal_new_hand, execute
from sekhmet.game_engine.pot_manager import award_pot, create_side_pots
from sekhmet.game_engine.hand_evaluator import evaluate_7_cards


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_player(name: str, seat: int, stack: int = 1000, **kw) -> Player:
    return Player(name=name, seat_idx=seat, stack=stack, **kw)


def waiting_state(*players: Player, dealer_idx: int = 0, sb: int = 5, bb: int = 10) -> GameState:
    return GameState(
        phase=GamePhase.WAITING,
        players=players,
        dealer_idx=dealer_idx,
        small_blind=sb,
        big_blind=bb,
    )


def deal(state: GameState) -> GameState:
    deck = Deck()
    deck.shuffle()
    return deal_new_hand(state, deck.cards[:], dealer_idx=state.dealer_idx)


def act(state: GameState, seat: int, atype: ActionType, amount: int = 0) -> GameState:
    assert state.current_player_idx == seat, (
        f"expected seat {seat} to act, got {state.current_player_idx}"
    )
    return execute(state, Action(seat, atype, amount))


def chip_total(state: GameState) -> int:
    """All chips in play: stacks + pots."""
    return sum(p.stack for p in state.players) + state.pot.total


# ---------------------------------------------------------------------------
# Big blind option (acted-tracking)
# ---------------------------------------------------------------------------


def test_big_blind_gets_option_preflop():
    """Limped pot: after UTG calls and SB completes, BB must get to act."""
    state = deal(waiting_state(
        make_player("D", 0),   # dealer / UTG
        make_player("SB", 1),
        make_player("BB", 2),
    ))
    assert state.current_player_idx == 0  # UTG first preflop

    state = act(state, 0, ActionType.CALL)
    state = act(state, 1, ActionType.CALL)

    # BB has matched the bet by posting, but has not *acted* yet
    assert state.phase == GamePhase.PREFLOP
    assert state.current_player_idx == 2


def test_big_blind_check_closes_round():
    """BB checks his option → flop is dealt."""
    state = deal(waiting_state(
        make_player("D", 0),
        make_player("SB", 1),
        make_player("BB", 2),
    ))
    state = act(state, 0, ActionType.CALL)
    state = act(state, 1, ActionType.CALL)
    state = act(state, 2, ActionType.CHECK)
    assert state.phase == GamePhase.FLOP


# ---------------------------------------------------------------------------
# Community card dealing
# ---------------------------------------------------------------------------


def test_full_checkdown_deals_every_street():
    """A hand checked all the way down ends with a 5-card board."""
    state = deal(waiting_state(
        make_player("D", 0),
        make_player("SB", 1),
        make_player("BB", 2),
    ))
    chips_at_deal = chip_total(state)

    # Preflop: UTG call, SB complete, BB check
    state = act(state, 0, ActionType.CALL)
    state = act(state, 1, ActionType.CALL)
    state = act(state, 2, ActionType.CHECK)
    assert state.phase == GamePhase.FLOP
    assert len(state.community_cards) == 3

    # Postflop order: first active player left of the dealer acts first
    for expected_board, next_phase in ((4, GamePhase.TURN), (5, GamePhase.RIVER)):
        state = act(state, 1, ActionType.CHECK)
        state = act(state, 2, ActionType.CHECK)
        state = act(state, 0, ActionType.CHECK)
        assert state.phase == next_phase
        assert len(state.community_cards) == expected_board

    state = act(state, 1, ActionType.CHECK)
    state = act(state, 2, ActionType.CHECK)
    state = act(state, 0, ActionType.CHECK)
    assert state.phase == GamePhase.SHOWDOWN
    assert len(state.community_cards) == 5

    # Card conservation: 52 = deck + board + 6 hole cards
    assert len(state.deck) + 5 + 6 == 52
    # Chip conservation: nothing created or destroyed mid-hand
    assert chip_total(state) == chips_at_deal


# ---------------------------------------------------------------------------
# All-in runout
# ---------------------------------------------------------------------------


def test_all_in_runout_heads_up():
    """Both players all-in preflop → board runs out to showdown, no stall."""
    state = deal(waiting_state(
        make_player("SB", 0, stack=200),  # HU: dealer=SB, acts first
        make_player("BB", 1, stack=200),
        dealer_idx=0,
    ))
    assert state.current_player_idx == 0

    state = act(state, 0, ActionType.ALL_IN)
    state = act(state, 1, ActionType.CALL)  # call also puts BB all-in

    assert state.phase == GamePhase.SHOWDOWN
    assert len(state.community_cards) == 5
    assert len(state.deck) + 5 + 4 == 52


def test_runout_when_one_player_still_has_chips():
    """All-in called by a deeper stack → runout immediately, no phantom turn."""
    state = deal(waiting_state(
        make_player("SB", 0, stack=100),
        make_player("BB", 1, stack=200),
        dealer_idx=0,
    ))
    state = act(state, 0, ActionType.ALL_IN)   # short stack shoves 100
    state = act(state, 1, ActionType.CALL)     # BB calls, keeps 100 behind

    # No further betting is possible — the hand must run itself out
    assert state.phase == GamePhase.SHOWDOWN
    assert len(state.community_cards) == 5


def test_side_pots_with_uneven_all_ins():
    """Three-way all-in with different stacks: side pots + full board + conservation."""
    state = deal(waiting_state(
        make_player("Short", 0, stack=50),   # dealer, first to act
        make_player("Mid", 1, stack=200),    # SB
        make_player("Big", 2, stack=200),    # BB
    ))
    state = act(state, 0, ActionType.ALL_IN)   # 50
    state = act(state, 1, ActionType.CALL)     # matches 50
    state = act(state, 2, ActionType.ALL_IN)   # 200
    state = act(state, 1, ActionType.ALL_IN)   # Mid calls the extra 150

    assert state.phase == GamePhase.SHOWDOWN
    assert len(state.community_cards) == 5

    pots = create_side_pots(state.players)
    # Levels 50 / 200: main = 50×3, side = 150×2
    assert pots.main_pot == 150
    assert [sp.amount for sp in pots.side_pots] == [300]
    assert set(pots.side_pots[0].eligible_players) == {1, 2}

    hands = {
        p.seat_idx: evaluate_7_cards(list(p.hole_cards) + list(state.community_cards))
        for p in state.players
        if p.is_active
    }
    awards = award_pot(pots, state.players, hands)
    assert sum(a.amount for a in awards) == 450  # every chip awarded


# ---------------------------------------------------------------------------
# Full-hand integration through the table manager (ws-facing layer)
# ---------------------------------------------------------------------------


async def _make_two_player_table() -> str:
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200)
    await tm.start_hand(tid)
    return tid


async def _current_seat(tid: str) -> int:
    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.current_player_idx is not None
    return session.game_state.current_player_idx


async def test_fold_out_showdown_needs_no_board():
    """Preflop fold → showdown awards the pot without evaluating <5 cards."""
    tid = await _make_two_player_table()
    session = await tm.get_table(tid)
    assert session is not None
    sb_seat = session.game_state.current_player_idx  # HU: SB acts first preflop

    msg = await tm.handle_player_action(tid, sb_seat, "FOLD")

    assert msg["type"] == "hand_result"
    session = await tm.get_table(tid)
    assert session is not None
    stacks = {p.seat_idx: p.stack for p in session.game_state.players}
    assert sum(stacks.values()) == 400  # conservation
    winner = 1 - sb_seat
    assert stacks[winner] > 200


async def test_complete_hand_through_table_manager():
    """Check-down to showdown: board has 5 cards, pot awarded, chips conserved."""
    tid = await _make_two_player_table()

    msg = None
    for _ in range(12):  # generous upper bound on actions
        session = await tm.get_table(tid)
        assert session is not None
        gs = session.game_state
        if gs.phase == GamePhase.SHOWDOWN:
            break
        seat = gs.current_player_idx
        player = gs.player(seat)
        to_call = gs.current_bet - player.current_bet
        msg = await tm.handle_player_action(
            tid, seat, "CALL" if to_call > 0 else "CHECK"
        )
    else:
        pytest.fail("hand did not reach showdown within 12 actions")

    assert msg is not None and msg["type"] == "hand_result"
    assert len(msg["community_cards"]) == 5

    awards = msg["showdown"]["awards"]
    assert sum(a["amount"] for a in awards) == 20  # both limped: 10 each

    session = await tm.get_table(tid)
    assert session is not None
    assert sum(p.stack for p in session.game_state.players) == 400


async def test_illegal_bot_action_falls_back_without_stalling(monkeypatch):
    """A bot that returns an illegal action must not freeze the game —
    auto_bot_actions falls back (check if free, else fold) and continues."""
    from sekhmet.game_engine.game_state import Action, ActionType

    class BrokenBot:
        def decide(self, state, player_idx):
            # Illegal: there is already a bet (BB=10), cannot open
            return Action(player_idx, ActionType.BET, 30)

    monkeypatch.setattr(
        "sekhmet.ai_engine.bot_registry.create", lambda name: BrokenBot()
    )

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)

    # Bot is SB/dealer on hand 1 and acts first; its illegal BET must
    # trigger the fallback (fold — facing 5 to call), ending the hand.
    msgs = await tm.auto_bot_actions(tid)

    session = await tm.get_table(tid)
    assert session is not None
    gs = session.game_state
    assert gs.phase == GamePhase.SHOWDOWN
    assert any(m.get("type") == "hand_result" for m in msgs)


async def test_second_hand_can_start_after_showdown():
    """A hand ends in SHOWDOWN; the next hand must be dealable from there
    (state machine: SHOWDOWN → WAITING → DEALING)."""
    tid = await _make_two_player_table()
    session = await tm.get_table(tid)
    assert session is not None
    sb_seat = session.game_state.current_player_idx

    await tm.handle_player_action(tid, sb_seat, "FOLD")  # hand 1 ends
    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.phase == GamePhase.SHOWDOWN

    msg = await tm.start_hand(tid)  # hand 2 must start cleanly
    assert msg["type"] == "hand_start"

    session = await tm.get_table(tid)
    assert session is not None
    gs = session.game_state
    assert gs.phase == GamePhase.PREFLOP
    # Folded player from hand 1 is back in, stacks carried over
    assert all(p.is_active for p in gs.players)
    assert sum(p.stack for p in gs.players) + gs.pot.total == 400
