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
import secrets
import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

from ..config import app_config
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
    runout_step,
)
from ..game_engine.pot_manager import PotAward, create_side_pots, award_pot
from ..models import recorder


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
class PlayerStats:
    """Per-seat in-memory stats for the room leaderboard (resets on stand_up)."""
    hands: int = 0
    wins: int = 0


@dataclass
class TableSession:
    table_id: str
    game_state: GameState
    deck: Deck
    clients: dict[int, WebSocket] = field(default_factory=dict)  # seat_idx → ws
    player_names: dict[int, str] = field(default_factory=dict)    # seat_idx → name
    config: TableConfig = field(default_factory=TableConfig)
    bot_levels: dict[int, int] = field(default_factory=dict)  # seat_idx → 1-3
    stats: dict[int, PlayerStats] = field(default_factory=dict)      # seat_idx → stats
    total_buyin: dict[int, int] = field(default_factory=dict)        # seat_idx → chips bought
    disconnected: set[int] = field(default_factory=set)
    consecutive_timeouts: dict[int, int] = field(default_factory=dict)  # seat_idx → count
    grace_timers: dict[int, asyncio.Task] = field(default_factory=dict)
    reclaim_tokens: dict[int, str] = field(default_factory=dict)  # seat_idx → token
    action_timer: asyncio.Task | None = None
    owner_seat: int | None = None
    owner_token: str | None = None  # room key from create_table — bearer claims ownership
    # Serializes sends per client socket: concurrent broadcast/send_to_player
    # calls (runout street + reclaim catch-up + kick notices can overlap)
    # would interleave frames on one websocket otherwise.
    send_locks: dict[int, asyncio.Lock] = field(default_factory=dict)
    last_activity: float = field(default_factory=time.monotonic)
    # Serializes every read-modify-write of ``game_state`` that can race:
    # the auto_bot_actions loop (incl. the all-in runout, whose per-street
    # sleep is deliberately inside the critical section) and _expire_seat's
    # mid-hand surgery.  Never call after_action/auto_bot_actions while
    # holding it — asyncio.Lock is not reentrant.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

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
        owner_token=secrets.token_hex(16),
    )
    async with _lock:
        if len(_tables) >= app_config.game.max_tables:
            raise GameError(
                f"Table limit reached ({app_config.game.max_tables}) — "
                "try again later"
            )
        _tables[tid] = session
    return tid


async def get_table(table_id: str) -> TableSession | None:
    async with _lock:
        return _tables.get(table_id)


async def remove_table(table_id: str) -> None:
    async with _lock:
        session = _tables.pop(table_id, None)
    if session is not None:
        # Don't leak pending tasks: cancel every grace timer and the
        # action timer or they fire against a table that no longer exists.
        for task in session.grace_timers.values():
            task.cancel()
        session.grace_timers.clear()
        if session.action_timer is not None:
            session.action_timer.cancel()
            session.action_timer = None


async def touch(table_id: str) -> None:
    session = await get_table(table_id)
    if session is not None:
        session.last_activity = time.monotonic()


async def sweep_idle_tables() -> list[str]:
    """Close rooms idle beyond the configured timeout. Returns closed ids."""
    timeout = app_config.game.room_idle_timeout_seconds
    now = time.monotonic()
    closed: list[str] = []
    for tid, session in list(_tables.items()):
        if now - session.last_activity <= timeout:
            continue
        for task in session.grace_timers.values():
            task.cancel()
        if session.action_timer is not None:
            session.action_timer.cancel()
        await broadcast(tid, {"type": "room_closed", "table_id": tid})
        await remove_table(tid)
        closed.append(tid)
    return closed


async def sweeper_loop(interval_seconds: float = 60.0) -> None:
    """Background task: periodically sweep idle rooms."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await sweep_idle_tables()
        except Exception:
            logger.exception("sweeper iteration failed")


# ---------------------------------------------------------------------------
# Player management
# ---------------------------------------------------------------------------


def _reassign_owner(session: TableSession) -> None:
    """Hand ownership to the lowest-seated remaining human (or None)."""
    if session.owner_seat is not None:
        p = session.game_state.player(session.owner_seat)
        if p is not None and p.is_human and session.owner_seat in session.player_names:
            return  # current owner still valid
    humans = [
        p.seat_idx for p in session.game_state.players
        if p.is_human and p.seat_idx in session.player_names
    ]
    session.owner_seat = min(humans) if humans else None


async def sit_down(
    table_id: str,
    seat_idx: int,
    name: str,
    buyin: int | None = None,
    is_human: bool = True,
    bot_level: int | None = None,
    owner_token: str | None = None,
) -> dict[str, Any]:
    """Seat a player at *table_id*.  Returns the updated table summary."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")

    if seat_idx >= session.n_seats:
        raise GameError(f"Seat {seat_idx} exceeds max {session.n_seats}")

    if seat_idx in session.player_names:
        raise GameError(f"Seat {seat_idx} is already occupied")

    # Mid-hand joins corrupt the betting round (a fresh player has matched
    # no bets and holds no cards) — only allow seating between hands.
    if session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        raise GameError("Table is mid-hand — wait for the next hand")

    if not is_human:
        level = 2 if bot_level is None else int(bot_level)
        if level not in (1, 2, 3):
            raise GameError(f"bot_level must be 1-3, got {bot_level}")
        session.bot_levels[seat_idx] = level

    stack = buyin if buyin is not None else session.config.default_buyin
    # Bounds mirror the rebuy limits (20bb–200bb).  This also blocks the
    # 0-chip grief seat: a dead player occupies the seat but can never play.
    lo = 20 * session.config.big_blind
    hi = max(200 * session.config.big_blind, session.config.default_buyin)
    if not (lo <= stack <= hi):
        raise GameError(f"Buy-in must be between {lo} and {hi}, got {buyin}")
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

    # Ownership: the bearer of the room's owner_token (returned at
    # creation) claims the room — on first sit-down or by taking over
    # from a stranger who raced in first.  Without a token the lowest-
    # seated human becomes (or stays) owner.
    if is_human and owner_token is not None and owner_token == session.owner_token:
        session.owner_seat = seat_idx
    else:
        _reassign_owner(session)

    session.stats[seat_idx] = PlayerStats()
    session.total_buyin[seat_idx] = stack
    if is_human:
        session.reclaim_tokens[seat_idx] = secrets.token_hex(16)

    return _table_summary(session)


def _stand_up_locked(session: TableSession, seat_idx: int) -> None:
    """Remove a seat from *session* — caller must hold ``session.lock``."""
    session.player_names.pop(seat_idx, None)
    session.clients.pop(seat_idx, None)
    session.send_locks.pop(seat_idx, None)
    session.bot_levels.pop(seat_idx, None)
    session.stats.pop(seat_idx, None)
    session.total_buyin.pop(seat_idx, None)
    session.reclaim_tokens.pop(seat_idx, None)
    session.consecutive_timeouts.pop(seat_idx, None)

    players = tuple(p for p in session.game_state.players if p.seat_idx != seat_idx)
    session.game_state = session.game_state.with_players(players)
    _reassign_owner(session)


async def stand_up(table_id: str, seat_idx: int) -> dict[str, Any]:
    """Remove a player from the table (between hands only).

    Ripping a seat out of ``game_state.players`` mid-hand would wedge the
    betting round — the caller must check the phase first; this guard is
    the backstop that closes the race with a concurrent ``start_hand``.
    """
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")

    async with session.lock:
        if session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameError("Table is mid-hand — cannot remove a seat")
        _stand_up_locked(session, seat_idx)

    return _table_summary(session)


async def handle_disconnect(table_id: str, seat_idx: int) -> None:
    """Mark the seat disconnected and start the grace timer (no instant removal)."""
    session = await get_table(table_id)
    if session is None:
        return
    session.clients.pop(seat_idx, None)  # dead socket
    session.disconnected.add(seat_idx)
    await broadcast(table_id, _table_summary(session))

    async def _expire() -> None:
        try:
            await asyncio.sleep(app_config.game.disconnect_grace_seconds)
        except asyncio.CancelledError:
            return
        await _expire_seat(table_id, seat_idx)

    # A repeated disconnect must not orphan the previous timer task.
    old_timer = session.grace_timers.pop(seat_idx, None)
    if old_timer is not None:
        old_timer.cancel()
    session.grace_timers[seat_idx] = asyncio.create_task(_expire())


async def try_reclaim(
    table_id: str, name: str, token: str | None
) -> tuple[int, str] | None:
    """Reclaim a disconnected seat by name + token. Returns (seat, new_token)."""
    session = await get_table(table_id)
    if session is None or token is None:
        return None
    for seat in list(session.disconnected):
        if (
            session.player_names.get(seat) == name
            and session.reclaim_tokens.get(seat) == token
        ):
            timer = session.grace_timers.pop(seat, None)
            if timer is not None:
                timer.cancel()
            session.disconnected.discard(seat)
            new_token = secrets.token_hex(16)
            session.reclaim_tokens[seat] = new_token
            return seat, new_token
    return None


async def _expire_seat(table_id: str, seat_idx: int, *, force: bool = False) -> None:
    """Grace expired (or timeout-kicked): fold out of any running hand, then remove."""
    session = await get_table(table_id)
    if session is None or (not force and seat_idx not in session.disconnected):
        return
    session.disconnected.discard(seat_idx)
    timer = session.grace_timers.pop(seat_idx, None)
    # A force-kick can orphan a still-pending grace timer — cancel it or it
    # fires a second expiry later.  On the grace-expiry path the popped
    # timer IS the currently-running task; cancelling ourselves would abort
    # the cleanup below, so skip that case.
    if timer is not None and timer is not asyncio.current_task():
        timer.cancel()

    # A timeout-kicked player is still connected — tell them why their seat
    # vanished before either removal path drops the socket.  (Grace expiry
    # already popped the socket in handle_disconnect, so force only.)
    if force:
        ws = session.clients.get(seat_idx)
        if ws is not None:
            try:
                await ws.send_json({
                    "type": "kicked",
                    "message": "Removed after consecutive timeouts",
                })
            except Exception:
                pass

    gs = session.game_state
    mid_hand = gs.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN)

    if not mid_hand:
        # stand_up re-checks the phase under the lock — a start_hand that
        # slips in between this check and the removal loses the race and
        # the seat stays until the next expiry attempt.
        try:
            await stand_up(table_id, seat_idx)
        except GameError:
            return
        await broadcast(table_id, _table_summary(session))
        return

    # Mid-hand: force-fold (engine fold if it's their turn, else mark inactive —
    # the engine's round logic skips inactive players either way).
    try:
        result = None
        # Critical section: the surgery below and the runout loop in
        # auto_bot_actions both do read → modify → write on game_state;
        # interleaving them double-pays the pot or resurrects pre-surgery
        # state.  Re-read the state inside the lock — the hand may have
        # ended (runout finished) while we waited.  The identity mappings
        # are popped under the same lock so a concurrent start_hand (which
        # now also takes the lock) can never deal a ghost seat whose
        # identity vanished between its purge check and the deal.
        async with session.lock:
            gs = session.game_state
            was_showdown = gs.phase == GamePhase.SHOWDOWN
            if gs.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
                p = gs.player(seat_idx)
                if p is not None and p.is_active and not p.is_all_in:
                    if gs.current_player_idx == seat_idx:
                        gs = execute(gs, Action(seat_idx, ActionType.FOLD))
                    else:
                        gs = gs.with_players(tuple(
                            replace(pl, is_active=False) if pl.seat_idx == seat_idx else pl
                            for pl in gs.players
                        ))
                        # The replace surgery bypasses execute(), so the engine's
                        # fold-out check never runs.  If only one active player
                        # remains, force SHOWDOWN now so the fold-out branch below
                        # pays the survivor — otherwise the pot evaporates when the
                        # survivor later folds.
                        if gs.n_active <= 1:
                            gs = gs.with_phase(GamePhase.SHOWDOWN)
                    session.game_state = gs
            # Identity mappings go now; the folded shell stays in
            # game_state.players until the hand ends (start_hand purges it
            # before the next deal).
            session.player_names.pop(seat_idx, None)
            session.stats.pop(seat_idx, None)
            session.total_buyin.pop(seat_idx, None)
            session.bot_levels.pop(seat_idx, None)
            session.reclaim_tokens.pop(seat_idx, None)
            session.consecutive_timeouts.pop(seat_idx, None)
            session.send_locks.pop(seat_idx, None)
            # Drop the kicked player's socket or they keep receiving
            # broadcasts for a seat they no longer hold (the 'kicked'
            # notice already went out at entry).  Grace expiry popped it
            # in handle_disconnect, so this is a no-op on that path.
            session.clients.pop(seat_idx, None)
            _reassign_owner(session)

        # Resolve only a showdown we just caused under the lock —
        # if the hand was already at SHOWDOWN when we acquired it,
        # the runout/action path that got it there owns the payout.
        if not was_showdown and session.game_state.phase == GamePhase.SHOWDOWN:
            result = _resolve_showdown(session)
        await broadcast(table_id, _state_broadcast(session, result))
        # after_action → auto_bot_actions takes session.lock itself; it must
        # be called only after the critical section above has released it.
        await after_action(table_id)
    except Exception:
        logger.exception(
            "Grace-expiry mid-hand removal failed for seat %s at table %s",
            seat_idx, table_id,
        )
    finally:
        await broadcast(table_id, _table_summary(session))


async def rebuy(table_id: str, seat_idx: int, amount: int) -> dict[str, Any]:
    """Top up a busted player between hands. Only stack==0 may rebuy."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")
    if session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        raise GameError("Table is mid-hand — rebuy between hands")
    player = session.game_state.player(seat_idx)
    if player is None or seat_idx not in session.player_names:
        raise GameError(f"Seat {seat_idx} is not occupied")
    if player.stack > 0:
        raise GameError("Only busted players (0 chips) can rebuy")
    lo = 20 * session.config.big_blind
    hi = 200 * session.config.big_blind
    if not (lo <= amount <= hi):
        raise GameError(f"Rebuy must be between 20bb ({lo}) and 200bb ({hi})")

    session.game_state = session.game_state.with_players(tuple(
        Player(name=p.name, seat_idx=p.seat_idx,
               stack=p.stack + amount if p.seat_idx == seat_idx else p.stack,
               hole_cards=p.hole_cards, is_active=p.is_active, is_all_in=p.is_all_in,
               current_bet=p.current_bet, total_bet=p.total_bet, is_human=p.is_human)
        for p in session.game_state.players
    ))
    session.total_buyin[seat_idx] = session.total_buyin.get(seat_idx, 0) + amount
    return _table_summary(session)


# ---------------------------------------------------------------------------
# Hand lifecycle
# ---------------------------------------------------------------------------


async def start_hand(table_id: str) -> dict[str, Any]:
    """Deal a new hand.  Requires ≥2 seated players."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")

    # The whole deal is one critical section: a grace-expiry popping its
    # identity mappings between our purge check and the deal would deal a
    # ghost seat into the new hand (a player who no longer exists acts
    # out the hand via the action timer).  _expire_seat now does its
    # surgery + identity pops under the same lock, so the interleaving
    # window is closed.
    async with session.lock:
        if session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameError(f"Cannot start hand during {session.game_state.phase.name}")

        if len(session.player_seats()) < 2:
            raise GameError("Need at least 2 players to start a hand")

        # Purge shells of players removed mid-hand (grace expiry) before dealing.
        live = tuple(
            p for p in session.game_state.players
            if p.seat_idx in session.player_names
        )
        if len(live) != len(session.game_state.players):
            session.game_state = session.game_state.with_players(live)

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

        for p in session.game_state.players:
            if p.seat_idx in session.stats:
                session.stats[p.seat_idx].hands += 1

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
    # Same critical section as auto_bot_actions/_expire_seat — a human
    # action must not interleave with the bot loop or the grace surgery.
    async with session.lock:
        session.game_state = execute(session.game_state, action)
        session.consecutive_timeouts[seat_idx] = 0  # 主动行动清零连续超时计数

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
    max_iterations = 40  # safety limit (runout streets each consume one)

    for _ in range(max_iterations):
        session = await get_table(table_id)
        if session is None:
            break

        # The whole loop body is one critical section: a grace-expiry
        # (_expire_seat) or a second auto_bot_actions loop must never
        # interleave with our read → step → write cycle, or both sides
        # step from stale snapshots (duplicated streets, the pot resolved
        # twice, or a stale write resurrecting pre-surgery state).  The
        # runout sleep stays inside the lock on purpose — the all-in
        # runout is a single critical section.
        async with session.lock:
            gs = session.game_state
            if gs.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
                break

            cur_idx = gs.current_player_idx
            if cur_idx is None:
                # All-in runout: delay, then deal the next street and
                # broadcast it live from inside the loop — appending streets
                # to `broadcasts` would hold them until this coroutine
                # returns and deliver the whole runout in one burst.
                # Sleeping before each step (including the first) keeps the
                # cadence uniform:
                # FLOP → delay → TURN → delay → RIVER → delay → result.
                #
                # Flush any queued bot-action broadcasts first so a client
                # never sees a street before the action that triggered the
                # runout (e.g. a bot's all-in/call in solo play).
                for pending in broadcasts:
                    await broadcast(table_id, pending)
                broadcasts.clear()
                await asyncio.sleep(app_config.game.runout_delay_seconds)
                session.game_state = runout_step(gs)
                gs = session.game_state
                if gs.phase == GamePhase.SHOWDOWN:
                    result = _resolve_showdown(session)
                    await broadcast(table_id, _state_broadcast(session, result))
                    break
                await broadcast(table_id, _state_broadcast(session))
                continue

            player = gs.player(cur_idx)
            if player is None or not player.is_active or player.is_all_in:
                break

            if player.is_human:
                break  # it's a human's turn — stop auto-play

            # Bot's turn — decide and execute.  A bot that crashes or
            # produces an illegal action must never freeze the game: fall
            # back to check (free) or fold (facing a bet) and carry on.
            bot_name = session.player_names.get(cur_idx, f"Bot{cur_idx}")
            level = session.bot_levels.get(cur_idx, 2)
            try:
                bot = create_bot(f"rule_lv{level}")
                action = bot.decide(gs, cur_idx)
                gs = execute(gs, action)
            except GameError:
                logger.warning(
                    "Bot %s produced an illegal action at table %s — falling back",
                    bot_name, table_id, exc_info=True,
                )
                gs = _bot_fallback(gs, cur_idx, player)
            except Exception:
                # Any other exception (a buggy decide() crashing, a broken
                # bot factory) would otherwise propagate through
                # after_action and strand the hand with no driver and no
                # action timer — a permanently frozen table.
                logger.exception(
                    "Bot %s crashed at table %s — falling back",
                    bot_name, table_id,
                )
                gs = _bot_fallback(gs, cur_idx, player)
            session.game_state = gs

            result = None
            if gs.phase == GamePhase.SHOWDOWN:
                result = _resolve_showdown(session)

            msg = _state_broadcast(session, result)
            broadcasts.append(msg)

    return broadcasts


# ---------------------------------------------------------------------------
# Action timeout + unified after-action pipeline
# ---------------------------------------------------------------------------


def schedule_action_timeout(session: TableSession) -> None:
    """(Re)arm the action timer if a human is to act in a betting round."""
    if session.action_timer is not None:
        session.action_timer.cancel()
        session.action_timer = None
    gs = session.game_state
    if gs.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        return
    cur = gs.current_player_idx
    if cur is None:
        return
    p = gs.player(cur)
    if p is None or not p.is_human:
        return
    session.action_timer = asyncio.create_task(_action_timeout(session.table_id, cur))


async def _action_timeout(table_id: str, seat_idx: int) -> None:
    try:
        await asyncio.sleep(app_config.game.action_timeout_seconds)
    except asyncio.CancelledError:
        return
    session = await get_table(table_id)
    if session is None:
        return
    # This task IS session.action_timer, and it has now fired.  Clear the
    # reference so schedule_action_timeout (reached via after_action below)
    # doesn't cancel the currently-running task — the CancelledError would
    # otherwise be delivered at the next await, i.e. inside the kick path.
    if session.action_timer is asyncio.current_task():
        session.action_timer = None
    gs = session.game_state
    if gs.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        return
    if gs.current_player_idx != seat_idx:
        return
    player = gs.player(seat_idx)
    if player is None or not player.is_human:
        return
    to_call = gs.current_bet - player.current_bet
    action_type = "CHECK" if to_call == 0 else "FOLD"
    logger.info("action timeout: auto %s for seat %s at table %s",
                action_type, seat_idx, table_id)
    # Capture the count before the auto-action: handle_player_action zeroes
    # the counter (it can't distinguish auto from manual actions), so reading
    # it afterwards would always yield 1 and the kick would never fire.
    prev = session.consecutive_timeouts.get(seat_idx, 0)
    try:
        msg = await handle_player_action(table_id, seat_idx, action_type)
        await broadcast(table_id, msg)
        await after_action(table_id)
        # Count only after the auto-action has been processed and broadcast,
        # so the hand has fully advanced (or ended) before we kick.
        count = prev + 1
        session.consecutive_timeouts[seat_idx] = count
        if count >= app_config.game.max_consecutive_timeouts:
            logger.info("seat %s kicked after %s consecutive timeouts at table %s",
                        seat_idx, count, table_id)
            await _expire_seat(table_id, seat_idx, force=True)
            return
    except GameError:
        # Lost a race (e.g. the player acted or the hand ended between the
        # checks above and the execute) — nothing to do, and the task must
        # not die with an unretrieved exception.
        pass


async def after_action(table_id: str) -> None:
    """Drive bots, push fresh stats at hand end, re-arm the action timer."""
    try:
        for msg in await auto_bot_actions(table_id):
            await broadcast(table_id, msg)
    except Exception:
        # auto_bot_actions is defensive, but if anything else throws the
        # timer must still get armed — otherwise a human-to-act hand has
        # no timeout safety net and the table wedges silently.
        logger.exception("after_action bot phase failed at table %s", table_id)
    session = await get_table(table_id)
    if session is None:
        return
    if session.game_state.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        await broadcast(table_id, _table_summary(session))
    schedule_action_timeout(session)


def _bot_fallback(gs: GameState, cur_idx: int, player: Player) -> GameState:
    """Least-damaging legal action when a bot misbehaves or crashes.

    Check when free, fold when facing a bet.  FOLD is always legal while
    it is the bot's turn, so this can only fail in a corrupt state.
    """
    to_call = gs.current_bet - player.current_bet
    try:
        return execute(
            gs,
            Action(cur_idx, ActionType.CHECK if to_call == 0 else ActionType.FOLD),
        )
    except GameError:
        logger.exception(
            "bot fallback rejected for seat %s — forcing fold", cur_idx,
        )
        return execute(gs, Action(cur_idx, ActionType.FOLD))


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------


async def broadcast(table_id: str, message: dict[str, Any]) -> None:
    """Send a JSON message to every connected client at the table."""
    session = await get_table(table_id)
    if session is None:
        return

    dead: list[int] = []
    # Snapshot: a sit_down/reclaim can mutate clients while we await
    # send_json below, and mutating a dict mid-iteration raises.
    for seat, ws in list(session.clients.items()):
        lock = session.send_locks.setdefault(seat, asyncio.Lock())
        try:
            async with lock:
                await ws.send_json(message)
        except Exception:
            dead.append(seat)

    for seat in dead:
        session.clients.pop(seat, None)
        session.send_locks.pop(seat, None)


async def send_to_player(table_id: str, seat_idx: int, message: dict[str, Any]) -> None:
    """Send a private message to a single player."""
    session = await get_table(table_id)
    if session is None:
        return
    ws = session.clients.get(seat_idx)
    if ws is not None:
        lock = session.send_locks.setdefault(seat_idx, asyncio.Lock())
        try:
            async with lock:
                await ws.send_json(message)
        except Exception:
            session.clients.pop(seat_idx, None)
            session.send_locks.pop(seat_idx, None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def table_info(session: TableSession) -> dict[str, Any]:
    """Serializable public table info — shared by REST and ws summary."""
    seats = []
    for seat, name in sorted(session.player_names.items()):
        p = session.game_state.player(seat)
        st = session.stats.get(seat)
        buyin = session.total_buyin.get(seat, p.stack if p is not None else 0)
        seats.append({
            "seat_idx": seat,
            "name": name,
            "is_human": p.is_human if p is not None else True,
            "bot_level": session.bot_levels.get(seat),
            "stack": p.stack if p is not None else 0,
            "hands": st.hands if st else 0,
            "wins": st.wins if st else 0,
            "net_chips": (p.stack if p is not None else 0) - buyin,
            "connected": seat not in session.disconnected,
            "is_owner": seat == session.owner_seat,
        })
    return {
        "table_id": session.table_id,
        "phase": session.game_state.phase.name,
        "max_seats": session.n_seats,
        "config": {
            "small_blind": session.config.small_blind,
            "big_blind": session.config.big_blind,
            "default_buyin": session.config.default_buyin,
            "max_seats": session.config.max_seats,
        },
        "seats": seats,
    }


def _table_summary(session: TableSession) -> dict[str, Any]:
    return {"type": "table_state", **table_info(session)}


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
        "sb_seat": session.game_state.sb_seat,
        "bb_seat": session.game_state.bb_seat,
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
        "dealer_idx": gs.dealer_idx,
        "sb_seat": gs.sb_seat,
        "bb_seat": gs.bb_seat,
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
    stacks_before = {p.seat_idx: p.stack for p in gs.players}

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
        awards_list = award_pot(pot, gs.players, hands, gs.dealer_idx)

    for seat in {a.winner_seat_idx for a in awards_list}:
        if seat in session.stats:
            session.stats[seat].wins += 1

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

    # Persist the completed hand (fire-and-forget; never blocks the game)
    winner_seats = {a.winner_seat_idx for a in awards_list}
    recorder.schedule_recording(recorder.record_hand(
        table_id=session.table_id,
        players_meta=[
            {
                "seat_idx": p.seat_idx, "name": p.name, "is_human": p.is_human,
                "stack_before": stacks_before[p.seat_idx],
                "stack_after": p.stack,
            }
            for p in players_list
        ],
        board=[str(c) for c in gs.community_cards],
        actions=[
            {"seat": a.player_idx, "action": a.type.name, "amount": a.amount}
            for a in gs.round_history
        ],
        awards=[
            {"seat_idx": a.winner_seat_idx, "amount": a.amount,
             "hand": a.hand_description}
            for a in awards_list
        ],
    ))
    recorder.schedule_recording(recorder.upsert_player_stats([
        {
            "name": p.name, "is_human": p.is_human,
            "won": p.seat_idx in winner_seats,
            "delta": p.stack - stacks_before[p.seat_idx],
        }
        for p in players_list
    ]))

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
