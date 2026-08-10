"""Action validation and execution.

Each player action passes through:

1. ``validate(state, action)`` — is this legal right now?
2. ``execute(state, action)`` — produce the **next** ``GameState``.
3. Phase-transition checks (all acted? advance street. all folded? showdown).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .deck import Card
from .game_state import (
    Action,
    ActionType,
    GameError,
    GamePhase,
    GameState,
    IllegalAmountError,
    InvalidActionError,
    NotYourTurnError,
    PhaseError,
    Player,
    PotState,
)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(state: GameState, action: Action) -> None:
    """Raise a ``GameError`` if *action* is illegal in *state*.

    Does **not** modify state — pure read-only check.
    """
    player = state.player(action.player_idx)
    if player is None:
        raise InvalidActionError(f"No player at seat {action.player_idx}")

    if state.phase in (GamePhase.WAITING, GamePhase.DEALING, GamePhase.SHOWDOWN):
        raise PhaseError(f"Cannot act during {state.phase.name}")

    if action.player_idx != state.current_player_idx:
        raise NotYourTurnError(
            f"Player {action.player_idx} is not the current player "
            f"(expected {state.current_player_idx})"
        )

    if not player.is_active:
        raise InvalidActionError("Folded players cannot act")

    if player.is_all_in:
        raise InvalidActionError("All-in players cannot act")

    at = action.type
    to_call = state.current_bet - player.current_bet

    if at == ActionType.FOLD:
        return  # always legal

    if at == ActionType.CHECK:
        if to_call > 0:
            raise InvalidActionError(f"Cannot check — must call {to_call} or fold")
        return

    if at == ActionType.CALL:
        if to_call == 0:
            raise InvalidActionError("Nothing to call — check or bet instead")
        # amount=0 is shorthand for "call whatever the difference is"
        call_amount = to_call if action.amount == 0 else action.amount
        if call_amount != to_call:
            raise IllegalAmountError(f"Call amount must be {to_call}, got {call_amount}")
        if call_amount > player.stack:
            raise IllegalAmountError(
                f"Call amount {call_amount} exceeds stack {player.stack}"
            )
        return

    if at == ActionType.BET:
        if state.current_bet > 0:
            raise InvalidActionError("Cannot open — there is already a bet; raise instead")
        # *amount* is the total the player wants to commit this street
        total_bet = action.amount
        if total_bet < state.big_blind:
            raise IllegalAmountError(
                f"Minimum bet is {state.big_blind}, got {total_bet}"
            )
        if total_bet > player.stack + player.current_bet:
            raise IllegalAmountError(
                f"Total bet {total_bet} exceeds available chips"
            )
        return

    if at == ActionType.RAISE:
        if state.current_bet == 0:
            raise InvalidActionError("Nothing to raise — bet instead")
        # *amount* is the total the player wants to commit this street
        total_bet = action.amount
        min_total = state.current_bet + state.min_raise
        if total_bet < min_total:
            raise IllegalAmountError(
                f"Minimum raise is to {min_total}, got {total_bet}"
            )
        if total_bet > player.stack + player.current_bet:
            raise IllegalAmountError(
                f"Total raise to {total_bet} exceeds available chips"
            )
        return

    if at == ActionType.ALL_IN:
        return  # always legal (provided player is active and not already all-in)

    raise InvalidActionError(f"Unknown action type: {at}")


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute(state: GameState, action: Action) -> GameState:
    """Validate *action*, then produce the next ``GameState``.

    This is the **only** entry point for mutating (logically) game state.
    """
    validate(state, action)

    player = state.player(action.player_idx)
    assert player is not None

    at = action.type
    to_call = state.current_bet - player.current_bet

    # --- 1.  Determine the effective bet amount ---
    if at == ActionType.FOLD:
        amount_committed = 0
        new_stack = player.stack
        is_fold = True
        is_all_in = False
    elif at == ActionType.CHECK:
        amount_committed = 0
        new_stack = player.stack
        is_fold = False
        is_all_in = False
    elif at == ActionType.CALL:
        call_amount = to_call if action.amount == 0 else action.amount
        amount_committed = min(call_amount, player.stack)
        new_stack = player.stack - amount_committed
        is_fold = False
        is_all_in = new_stack == 0
    elif at == ActionType.BET:
        # action.amount is the TOTAL bet this street
        amount_committed = min(action.amount, player.stack + player.current_bet) - player.current_bet
        new_stack = player.stack - amount_committed
        is_fold = False
        is_all_in = new_stack == 0
    elif at == ActionType.RAISE:
        # action.amount is the TOTAL bet this street
        total_bet = min(action.amount, player.stack + player.current_bet)
        amount_committed = total_bet - player.current_bet
        new_stack = player.stack - amount_committed
        is_fold = False
        is_all_in = new_stack == 0
    elif at == ActionType.ALL_IN:
        amount_committed = player.stack
        new_stack = 0
        is_fold = False
        is_all_in = True
    else:
        raise InvalidActionError(f"Unknown action type: {at}")

    # --- 2.  Update the player ---
    new_player = Player(
        name=player.name,
        seat_idx=player.seat_idx,
        stack=new_stack,
        hole_cards=player.hole_cards,
        is_active=player.is_active and not is_fold,
        is_all_in=is_all_in,
        current_bet=player.current_bet + amount_committed,
        total_bet=player.total_bet + amount_committed,
        is_human=player.is_human,
    )

    players = _replace_player(state.players, new_player)

    # --- 3.  Update pot ---
    new_pot = PotState(
        main_pot=state.pot.main_pot + amount_committed,
        side_pots=state.pot.side_pots,
    )

    # --- 4.  Update betting state ---
    new_current_bet = state.current_bet
    new_min_raise = state.min_raise
    new_last_aggressor = state.last_aggressor_idx
    acted_this_round: tuple[int, ...]

    if at in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
        effective_bet = player.current_bet + amount_committed
        if effective_bet > state.current_bet:
            new_current_bet = effective_bet
            new_last_aggressor = player.seat_idx
            raise_amount = effective_bet - state.current_bet
            if raise_amount > state.min_raise:
                new_min_raise = raise_amount

    # --- 5.  Track which players have acted this round ---
    # A betting round closes only when every player who can still act has
    # acted AND matched the current bet (see ``_round_closed``).  This is
    # what preserves the big blind's option in a limped pot.
    if action.player_idx in state.acted_seats:
        new_acted = state.acted_seats
    else:
        new_acted = state.acted_seats + (action.player_idx,)

    # --- 6.  Record history ---
    recorded_action = Action(
        player_idx=action.player_idx,
        type=action.type,
        amount=amount_committed,
    )
    new_history = state.round_history + (recorded_action,)

    # --- 7.  Build interim state ---
    new_state = GameState(
        phase=state.phase,
        players=players,
        community_cards=state.community_cards,
        pot=new_pot,
        deck=state.deck,
        current_player_idx=state.current_player_idx,  # will be updated below
        dealer_idx=state.dealer_idx,
        current_bet=new_current_bet,
        min_raise=new_min_raise,
        last_aggressor_idx=new_last_aggressor,
        small_blind=state.small_blind,
        big_blind=state.big_blind,
        round_history=new_history,
        acted_seats=new_acted,
    )

    # --- 8.  Determine next player & phase transition ---
    return _advance(new_state, action.player_idx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _replace_player(players: tuple[Player, ...], updated: Player) -> tuple[Player, ...]:
    """Return a new tuple with *updated* replacing the player at the same index."""
    return tuple(updated if p.seat_idx == updated.seat_idx else p for p in players)


def _next_active_seat(
    players: tuple[Player, ...],
    from_seat: int,
    n_seats: int,
) -> int | None:
    """Find the next active (non-folded, non-all-in) player clockwise."""
    for offset in range(1, n_seats + 1):
        candidate = (from_seat + offset) % n_seats
        for p in players:
            if p.seat_idx == candidate and p.is_active and not p.is_all_in:
                return candidate
    return None


def _count_players_who_can_act(players: tuple[Player, ...]) -> int:
    """Count players who are active and not all-in."""
    return sum(1 for p in players if p.is_active and not p.is_all_in)


def _round_closed(state: GameState) -> bool:
    """Whether the current betting round is complete.

    A round closes only when **every** player who can still act (active and
    not all-in) has both matched ``current_bet`` and taken at least one
    action this round.  Checking ``acted_seats`` is what stops a limped pot
    from skipping the big blind's option.
    """
    for p in state.players:
        if p.is_active and not p.is_all_in:
            if p.current_bet != state.current_bet:
                return False
            if p.seat_idx not in state.acted_seats:
                return False
    return True


def _advance(state: GameState, from_seat: int) -> GameState:
    """Figure out who acts next, or whether the phase needs to change."""
    n_seats = max((p.seat_idx + 1 for p in state.players), default=0)

    # Everyone folded except one player → hand over, no board needed
    if state.n_active <= 1:
        return state.with_phase(GamePhase.SHOWDOWN)

    if _round_closed(state):
        if _count_players_who_can_act(state.players) <= 1:
            # No further betting is possible (everyone else is all-in) —
            # advance one street; current_player_idx=None signals "runout
            # pending" and the table layer drives runout_step().
            return _advance_phase(state)
        return _advance_phase(state)

    # Otherwise, pass to the next player
    next_seat = _next_active_seat(state.players, from_seat, n_seats)
    if next_seat is None:
        # No one left who can act — advance one street of the runout
        return _advance_phase(state)

    return GameState(
        phase=state.phase,
        players=state.players,
        community_cards=state.community_cards,
        pot=state.pot,
        deck=state.deck,
        current_player_idx=next_seat,
        dealer_idx=state.dealer_idx,
        current_bet=state.current_bet,
        min_raise=state.min_raise,
        last_aggressor_idx=state.last_aggressor_idx,
        small_blind=state.small_blind,
        big_blind=state.big_blind,
        round_history=state.round_history,
        acted_seats=state.acted_seats,
    )


# Community cards dealt when entering each street (no burn cards — the
# deck is digital, burning adds nothing).
_CARDS_PER_STREET: dict[GamePhase, int] = {
    GamePhase.FLOP: 3,
    GamePhase.TURN: 1,
    GamePhase.RIVER: 1,
}


def _deal_community(
    community: tuple[object, ...], deck: tuple[object, ...], n: int
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    """Deal *n* cards off the top (end) of *deck* onto the board."""
    n = min(n, len(deck))
    if n == 0:
        return community, deck
    return community + deck[-n:], deck[:-n]


def runout_step(state: GameState) -> GameState:
    """Advance one street during an all-in runout (nobody left to act).

    The table layer calls this in a loop (broadcasting each street) until
    the state reaches SHOWDOWN.
    """
    if state.phase in (GamePhase.WAITING, GamePhase.DEALING, GamePhase.SHOWDOWN):
        raise PhaseError(f"Cannot run out from {state.phase.name}")
    return _advance_phase(state)


def _advance_phase(state: GameState) -> GameState:
    """Move to the next phase — dealing community cards if applicable."""
    # Reset per-street bets
    players = tuple(
        Player(
            name=p.name,
            seat_idx=p.seat_idx,
            stack=p.stack,
            hole_cards=p.hole_cards,
            is_active=p.is_active,
            is_all_in=p.is_all_in,
            current_bet=0,  # reset for next street
            total_bet=p.total_bet,
            is_human=p.is_human,
        )
        for p in state.players
    )

    next_phase_map = {
        GamePhase.PREFLOP: GamePhase.FLOP,
        GamePhase.FLOP: GamePhase.TURN,
        GamePhase.TURN: GamePhase.RIVER,
        GamePhase.RIVER: GamePhase.SHOWDOWN,
    }
    next_phase = next_phase_map.get(state.phase, GamePhase.SHOWDOWN)

    if next_phase == GamePhase.SHOWDOWN:
        return GameState(
            phase=GamePhase.SHOWDOWN,
            players=players,
            community_cards=state.community_cards,
            pot=state.pot,
            deck=state.deck,
            current_player_idx=None,
            dealer_idx=state.dealer_idx,
            current_bet=0,
            min_raise=state.big_blind,
            last_aggressor_idx=None,
            small_blind=state.small_blind,
            big_blind=state.big_blind,
            round_history=state.round_history,
            acted_seats=(),
        )

    # Deal this street's community cards
    community, deck = _deal_community(
        state.community_cards, state.deck, _CARDS_PER_STREET[next_phase]
    )

    # First to act post-flop: first active player left of the dealer.
    # No more betting is possible with ≤1 actor — signal "runout pending"
    # with current_player_idx=None instead of offering a phantom turn.
    if _count_players_who_can_act(players) <= 1:
        first_to_act = None
    else:
        n_seats = max((p.seat_idx + 1 for p in players), default=0)
        first_to_act = _next_active_seat(players, state.dealer_idx, n_seats)

    return GameState(
        phase=next_phase,
        players=players,
        community_cards=community,
        pot=state.pot,
        deck=deck,
        current_player_idx=first_to_act,
        dealer_idx=state.dealer_idx,
        current_bet=0,
        min_raise=state.big_blind,
        last_aggressor_idx=None,
        small_blind=state.small_blind,
        big_blind=state.big_blind,
        round_history=state.round_history,
        acted_seats=(),
    )


# ---------------------------------------------------------------------------
# Convenience: process a hand from deal through conclusion
# ---------------------------------------------------------------------------


def deal_new_hand(
    state: GameState,
    deck_cards: list[Card],
    dealer_idx: int = 0,
) -> GameState:
    """Deal hole cards and post blinds, transitioning to PREFLOP.

    Parameters
    ----------
    state : GameState
        Must be in WAITING phase (fresh table) or SHOWDOWN (previous hand
        complete — the state machine's SHOWDOWN → WAITING edge), with at
        least 2 players with chips.
    deck_cards : list[Card]
        A shuffled deck (will be consumed via ``.pop()``).
    dealer_idx : int
        Which seat holds the dealer button.
    """
    if state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        raise PhaseError(f"Cannot deal — expected WAITING or SHOWDOWN, got {state.phase.name}")
    # Only players with chips can be dealt in; busted players sit out.
    live_count = sum(1 for p in state.players if p.stack > 0)
    if live_count < 2:
        raise InvalidActionError("Need at least 2 players with chips to deal")

    # Blinds rotate clockwise over players WITH CHIPS (busted players sit
    # out; a busted blind seat is dead and the blind moves on).  Seat
    # indices may be sparse (custom seat picker), so rotate over the
    # actual live seat list, never modulo len(players).
    live_seats = sorted(p.seat_idx for p in state.players if p.stack > 0)

    def _after(seat: int) -> int:
        """First live seat clockwise after *seat* (wraps)."""
        for s in live_seats:
            if s > seat:
                return s
        return live_seats[0]

    if len(live_seats) == 2:
        # HU: dealer is SB when they have chips; otherwise first live seat
        # after the (dead) button.
        sb_seat = dealer_idx if dealer_idx in live_seats else _after(dealer_idx)
        bb_seat = _after(sb_seat)
    else:
        sb_seat = _after(dealer_idx)
        bb_seat = _after(sb_seat)

    updated: list[Player] = []
    for p in state.players:
        if p.stack == 0:
            # Busted — sits out this hand (can rebuy between hands)
            updated.append(Player(
                name=p.name, seat_idx=p.seat_idx, stack=0,
                hole_cards=(), is_active=False, is_all_in=False,
                current_bet=0, total_bet=0, is_human=p.is_human,
            ))
            continue
        card1 = deck_cards.pop()
        card2 = deck_cards.pop()
        is_sb = p.seat_idx == sb_seat
        is_bb = p.seat_idx == bb_seat

        sb_amount = min(state.small_blind, p.stack) if is_sb else 0
        bb_amount = min(state.big_blind, p.stack) if is_bb else 0
        blind_total = sb_amount + bb_amount

        new_stack = p.stack - blind_total
        updated.append(Player(
            name=p.name,
            seat_idx=p.seat_idx,
            stack=new_stack,
            hole_cards=(card1, card2),
            is_active=True,
            is_all_in=new_stack == 0,
            current_bet=blind_total,
            total_bet=blind_total,
            is_human=p.is_human,
        ))

    players = tuple(updated)
    pot = PotState(main_pot=sum(p.total_bet for p in players))

    # First to act preflop: left of the big blind (bb_seat + 1)
    n_seats = max((p.seat_idx + 1 for p in players), default=0)
    first_to_act = _next_active_seat(players, bb_seat, n_seats)

    return GameState(
        phase=GamePhase.PREFLOP,
        players=players,
        community_cards=(),
        pot=pot,
        deck=tuple(deck_cards),
        current_player_idx=first_to_act,
        dealer_idx=dealer_idx,
        current_bet=state.big_blind,
        min_raise=state.big_blind,
        last_aggressor_idx=bb_seat if first_to_act != bb_seat else None,
        small_blind=state.small_blind,
        big_blind=state.big_blind,
        round_history=(),
    )
