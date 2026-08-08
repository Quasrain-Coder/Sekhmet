"""In-memory table manager — owns all active game sessions.

Each table has:
- A unique ``table_id`` (UUID-like short string)
- The current ``GameState``
- Connected WebSocket clients (mapped by seat_idx)
- A shuffled deck (consumed as cards are dealt)

This module is the bridge between the WebSocket transport and the
game engine — it translates JSON messages into engine calls and
broadcasts results.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

from ..game_engine import (
    Action,
    ActionType,
    Card,
    Deck,
    GameError,
    GamePhase,
    GameState,
    Player,
    PotState,
    deal_new_hand,
    execute,
    evaluate_7_cards,
)
from ..game_engine.pot_manager import PotAward, create_side_pots, award_pot


@dataclass(frozen=True)
class TableConfig:
    """Per-table room configuration, fixed at creation time."""

    small_blind: int = 5
    big_blind: int = 10
    default_buyin: int = 200
    max_seats: int = 9

    def __post_init__(self):
        if not (0 < self.small_blind < self.big_blind):
            raise ValueError(
                f"Require 0 < small_blind < big_blind, "
                f"got {self.small_blind}/{self.big_blind}"
            )
        if not (2 <= self.max_seats <= 9):
            raise ValueError(f"max_seats must be 2-9, got {self.max_seats}")
        if self.default_buyin < 20 * self.big_blind:
            raise ValueError(
                f"default_buyin must be >= 20 big blinds "
                f"({20 * self.big_blind}), got {self.default_buyin}"
            )

    @classmethod
    def from_dict(cls, d: dict) -> "TableConfig":
        known = {"small_blind", "big_blind", "default_buyin", "max_seats"}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"Unknown config keys: {sorted(unknown)}")
        return cls(**{k: int(v) for k, v in d.items()})


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Table session
# ---------------------------------------------------------------------------


@dataclass
class TableSession:
    table_id: str
    game_state: GameState
    deck: Deck
    clients: dict[int, WebSocket] = field(default_factory=dict)  # seat_idx → ws
    player_names: dict[int, str] = field(default_factory=dict)    # seat_idx → name
    config: TableConfig = field(default_factory=TableConfig)

    @property
    def n_seats(self) -> int:
        return self.config.max_seats

    def player_seats(self) -> list[int]:
        """Return sorted list of occupied seats."""
        return sorted(self.player_names.keys())


# ---------------------------------------------------------------------------
# Global table registry
# ---------------------------------------------------------------------------


_tables: dict[str, TableSession] = {}
_lock = asyncio.Lock()


async def create_table(config: TableConfig | None = None) -> str:
    """Create a new table with the given room config (defaults if None)."""
    cfg = config or TableConfig()
    tid = _short_id()
    session = TableSession(
        table_id=tid,
        game_state=GameState(
            small_blind=cfg.small_blind,
            big_blind=cfg.big_blind,
        ),
        deck=Deck(),
        config=cfg,
    )
    async with _lock:
        _tables[tid] = session
    return tid


async def get_table(table_id: str) -> TableSession | None:
    async with _lock:
        return _tables.get(table_id)


async def remove_table(table_id: str) -> None:
    async with _lock:
        _tables.pop(table_id, None)


# ---------------------------------------------------------------------------
# Player management
# ---------------------------------------------------------------------------


async def sit_down(
    table_id: str,
    seat_idx: int,
    name: str,
    buyin: int | None = None,
    is_human: bool = True,
) -> dict[str, Any]:
    """Seat a player at *table_id*.  Returns the updated table summary."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")

    if seat_idx >= session.n_seats:
        raise GameError(f"Seat {seat_idx} exceeds max {session.n_seats}")

    if seat_idx in session.player_names:
        raise GameError(f"Seat {seat_idx} is already occupied")

    stack = buyin if buyin is not None else session.config.default_buyin
    player = Player(
        name=name,
        seat_idx=seat_idx,
        stack=stack,
        is_human=is_human,
    )
    session.player_names[seat_idx] = name

    # Add player to GameState
    current = list(session.game_state.players)
    current.append(player)
    session.game_state = session.game_state.with_players(tuple(current))

    return _table_summary(session)


async def stand_up(table_id: str, seat_idx: int) -> dict[str, Any]:
    """Remove a player from the table."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")

    session.player_names.pop(seat_idx, None)
    session.clients.pop(seat_idx, None)

    players = tuple(p for p in session.game_state.players if p.seat_idx != seat_idx)
    session.game_state = session.game_state.with_players(players)

    return _table_summary(session)


# ---------------------------------------------------------------------------
# Hand lifecycle
# ---------------------------------------------------------------------------


async def start_hand(table_id: str) -> dict[str, Any]:
    """Deal a new hand.  Requires ≥2 seated players."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")

    if session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        raise GameError(f"Cannot start hand during {session.game_state.phase.name}")

    if len(session.player_seats()) < 2:
        raise GameError("Need at least 2 players to start a hand")

    # Fresh deck, shuffle, deal
    session.deck = Deck()
    session.deck.shuffle()
    dealer = session.game_state.dealer_idx

    # Advance dealer button
    seats = session.player_seats()
    if dealer in seats:
        idx = seats.index(dealer)
        dealer = seats[(idx + 1) % len(seats)]

    session.game_state = deal_new_hand(
        session.game_state,
        session.deck.cards[:],
        dealer_idx=dealer,
    )
    session.deck.cards = list(session.game_state.deck)

    return _hand_start_broadcast(session)


# ---------------------------------------------------------------------------
# Action handling
# ---------------------------------------------------------------------------


async def handle_player_action(
    table_id: str,
    seat_idx: int,
    action_type: str,
    amount: int = 0,
) -> dict[str, Any]:
    """Validate and execute a player action, then broadcast the new state."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")

    at = ActionType[action_type.upper()]
    action = Action(player_idx=seat_idx, type=at, amount=amount)
    session.game_state = execute(session.game_state, action)

    # If we reached showdown, evaluate hands and award pot
    result = None
    if session.game_state.phase == GamePhase.SHOWDOWN:
        result = _resolve_showdown(session)

    return _state_broadcast(session, result)


async def auto_bot_actions(table_id: str) -> list[dict[str, Any]]:
    """Let bots act until it's a human's turn or the hand ends.

    Call this after a human action or after dealing a new hand.
    Returns the list of broadcast messages generated by bot actions.
    """
    from ..ai_engine.bot_registry import create as create_bot

    broadcasts: list[dict[str, Any]] = []
    max_iterations = 20  # safety limit

    for _ in range(max_iterations):
        session = await get_table(table_id)
        if session is None:
            break

        gs = session.game_state
        if gs.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            break

        cur_idx = gs.current_player_idx
        if cur_idx is None:
            break

        player = gs.player(cur_idx)
        if player is None or not player.is_active or player.is_all_in:
            break

        if player.is_human:
            break  # it's a human's turn — stop auto-play

        # Bot's turn — decide and execute.  A bot that produces an illegal
        # action must never freeze the game: fall back to check (free) or
        # fold (facing a bet) and carry on.
        bot_name = session.player_names.get(cur_idx, f"Bot{cur_idx}")
        # Default to rule_lv2 for bots
        bot = create_bot("rule_lv2")
        try:
            action = bot.decide(gs, cur_idx)
            gs = execute(gs, action)
        except GameError:
            logger.warning(
                "Bot %s produced an illegal action at table %s — falling back",
                bot_name, table_id, exc_info=True,
            )
            to_call = gs.current_bet - player.current_bet
            fallback = Action(
                cur_idx,
                ActionType.CHECK if to_call == 0 else ActionType.FOLD,
            )
            gs = execute(gs, fallback)
        session.game_state = gs

        result = None
        if gs.phase == GamePhase.SHOWDOWN:
            result = _resolve_showdown(session)

        msg = _state_broadcast(session, result)
        broadcasts.append(msg)

    return broadcasts


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------


async def broadcast(table_id: str, message: dict[str, Any]) -> None:
    """Send a JSON message to every connected client at the table."""
    session = await get_table(table_id)
    if session is None:
        return

    dead: list[int] = []
    for seat, ws in session.clients.items():
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(seat)

    for seat in dead:
        session.clients.pop(seat, None)


async def send_to_player(table_id: str, seat_idx: int, message: dict[str, Any]) -> None:
    """Send a private message to a single player."""
    session = await get_table(table_id)
    if session is None:
        return
    ws = session.clients.get(seat_idx)
    if ws is not None:
        try:
            await ws.send_json(message)
        except Exception:
            session.clients.pop(seat_idx, None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _table_summary(session: TableSession) -> dict[str, Any]:
    return {
        "type": "table_state",
        "table_id": session.table_id,
        "seats": {
            seat: name for seat, name in session.player_names.items()
        },
        "phase": session.game_state.phase.name,
        "max_seats": session.n_seats,
    }


def _hand_start_broadcast(session: TableSession) -> dict[str, Any]:
    return {
        "type": "hand_start",
        "table_id": session.table_id,
        "phase": session.game_state.phase.name,
        "dealer_idx": session.game_state.dealer_idx,
        "current_player_idx": session.game_state.current_player_idx,
        "current_bet": session.game_state.current_bet,
        "players": [
            {
                "seat_idx": p.seat_idx,
                "name": p.name,
                "stack": p.stack,
                "current_bet": p.current_bet,
                "is_human": p.is_human,
            }
            for p in session.game_state.players
        ],
        "small_blind": session.game_state.small_blind,
        "big_blind": session.game_state.big_blind,
        "pot": session.game_state.pot.main_pot,
    }


def _state_broadcast(
    session: TableSession,
    showdown_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gs = session.game_state

    # Public info: everyone sees this
    public = {
        "type": "game_state_update",
        "table_id": session.table_id,
        "phase": gs.phase.name,
        "community_cards": [str(c) for c in gs.community_cards],
        "pot": gs.pot.main_pot,
        "current_bet": gs.current_bet,
        "current_player_idx": gs.current_player_idx,
        "players": [
            {
                "seat_idx": p.seat_idx,
                "name": p.name,
                "stack": p.stack,
                "current_bet": p.current_bet,
                "is_active": p.is_active,
                "is_all_in": p.is_all_in,
                "is_human": p.is_human,
            }
            for p in gs.players
        ],
        "round_history": [
            {"seat": a.player_idx, "action": a.type.name, "amount": a.amount}
            for a in gs.round_history
        ],
    }

    if showdown_result:
        public["type"] = "hand_result"
        public["showdown"] = showdown_result

    return public


def _resolve_showdown(session: TableSession) -> dict[str, Any]:
    """Evaluate hands, create side pots, and award to winners."""
    gs = session.game_state

    active = [p for p in gs.players if p.is_active and p.hole_cards]

    # Create side pots from total bets
    pot = create_side_pots(gs.players)

    if len(active) == 1:
        # Fold-out: the last player standing wins without revealing cards.
        # The board may be incomplete, so no hand evaluation is possible
        # (or appropriate — the winner's hole cards stay hidden).
        winner = active[0]
        awards_list = (
            [PotAward(amount=pot.total, winner_seat_idx=winner.seat_idx,
                      hand_description="Won without showdown")]
            if pot.total > 0 else []
        )
        hands: dict[int, Any] = {}
    else:
        # Gather hands for active (non-folded) players
        hands = {}
        for p in active:
            all_cards = list(p.hole_cards) + list(gs.community_cards)
            hands[p.seat_idx] = evaluate_7_cards(all_cards)

        # Award
        awards_list = award_pot(pot, gs.players, hands)

    # Update player stacks
    players_list = list(gs.players)
    for award in awards_list:
        for i, p in enumerate(players_list):
            if p.seat_idx == award.winner_seat_idx:
                players_list[i] = Player(
                    name=p.name,
                    seat_idx=p.seat_idx,
                    stack=p.stack + award.amount,
                    hole_cards=p.hole_cards,
                    is_active=p.is_active,
                    is_all_in=p.is_all_in,
                    current_bet=p.current_bet,
                    total_bet=p.total_bet,
                    is_human=p.is_human,
                )
                break
    session.game_state = gs.with_players(tuple(players_list))

    return {
        "hands": {
            seat: score.describe()
            for seat, score in hands.items()
        },
        "awards": [
            {
                "seat_idx": a.winner_seat_idx,
                "amount": a.amount,
                "hand": a.hand_description,
            }
            for a in awards_list
        ],
    }
