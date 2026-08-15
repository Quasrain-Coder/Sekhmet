"""WebSocket endpoint — real-time game and trainer interaction.

Single endpoint ``/ws/{table_id}`` handles all in-game communication.
Messages are JSON with a ``type`` field (see protocol below).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..game_engine import GameError, GamePhase
from . import table_manager as tm

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{table_id}")
async def game_websocket(websocket: WebSocket, table_id: str):
    await websocket.accept()
    logger.info("WebSocket connected to table %s", table_id)

    my_seat: int | None = None

    try:
        async for raw in websocket.iter_text():
            import json

            try:
                msg: dict = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            await tm.touch(table_id)

            msg_type = msg.get("type", "")

            try:
                if msg_type == "sit_down":
                    seat_idx = int(msg["seat_idx"])
                    name = str(msg.get("name", f"Player{seat_idx}"))
                    buyin = msg.get("buyin")
                    is_human = bool(msg.get("is_human", True))
                    bot_level = msg.get("bot_level")
                    owner_token = msg.get("owner_token")

                    session = await tm.get_table(table_id)
                    if session is None:
                        await websocket.send_json({"type": "error", "message": "Table not found"})
                        continue

                    # Reconnect path: a name + token matching a disconnected
                    # seat reclaims it (works mid-hand — the player never
                    # left).  Without a valid token this falls through to the
                    # normal sit_down, where "Seat is already occupied"
                    # rejects the impostor.
                    reclaimed = await tm.try_reclaim(
                        table_id, name, msg.get("reclaim_token")
                    )
                    if reclaimed is not None:
                        seat, new_token = reclaimed
                        session.clients[seat] = websocket
                        my_seat = seat
                        await websocket.send_json({
                            "type": "reclaim_token", "token": new_token,
                            "seat": seat,
                        })
                        await tm.broadcast(table_id, tm._table_summary(session))
                        # Re-send private state so the reclaimer catches up
                        p = session.game_state.player(seat)
                        if p is not None and p.hole_cards:
                            await tm.send_to_player(table_id, seat, {
                                "type": "hole_cards",
                                "cards": [str(c) for c in p.hole_cards],
                            })
                        # Re-send the public game state (board, pot, bets,
                        # current player) or a mid-hand reclaimer stays blind
                        # until the next broadcast.
                        await tm.send_to_player(
                            table_id, seat, tm._state_broadcast(session),
                        )
                        # Re-arm the action timer: the countdown kept ticking
                        # through the disconnect, and the auto check/fold
                        # would otherwise fire mid-thought (still counting
                        # as a timeout against the reclaimer).
                        tm.schedule_action_timeout(session)
                        continue

                    # Only the room owner may fill seats with bots —
                    # otherwise any passer-by could spam a stranger's table
                    # full of bot seats (the owner is the only one who can
                    # remove them).  An ownerless table is fair game: the
                    # first human to sit becomes owner and can clean up.
                    if not is_human and session.owner_seat is not None and (
                        my_seat is None or my_seat != session.owner_seat
                    ):
                        await websocket.send_json({
                            "type": "error",
                            "message": "Only the table owner can add bots",
                        })
                        continue

                    # Validate first: a rejected sit_down (seat occupied /
                    # mid-hand) must NOT touch the clients map — otherwise the
                    # loser's socket hijacks the real occupant's broadcasts.
                    summary = await tm.sit_down(
                        table_id, seat_idx, name, buyin, is_human,
                        bot_level=bot_level, owner_token=owner_token,
                    )

                    # Only human seats claim the connection.  A bot seated
                    # through the same connection (solo-play auto-add) must
                    # NOT overwrite my_seat — otherwise every player_action
                    # would execute as the bot and fail with NotYourTurnError.
                    if is_human:
                        session.clients[seat_idx] = websocket
                        my_seat = seat_idx
                        token = session.reclaim_tokens.get(seat_idx)
                        if token:
                            await websocket.send_json({
                                "type": "reclaim_token", "token": token,
                                "seat": seat_idx,
                            })

                    await tm.broadcast(table_id, summary)

                elif msg_type == "stand_up":
                    target = msg.get("seat_idx", my_seat)
                    if target is None:
                        continue
                    target = int(target)
                    if target == my_seat:
                        # Mid-hand a manual stand_up would rip the player out
                        # of game_state.players and wedge the hand (action
                        # timer finds no player, bots stop).  The graceful
                        # path is: close the tab → disconnect → grace expiry
                        # folds them out.
                        session = await tm.get_table(table_id)
                        if session is not None and session.game_state.phase not in (
                            GamePhase.WAITING, GamePhase.SHOWDOWN,
                        ):
                            await websocket.send_json({
                                "type": "error",
                                "message": "Cannot leave mid-hand — close the "
                                           "tab and you'll be folded out",
                            })
                            continue
                        summary = await tm.stand_up(table_id, my_seat)
                        my_seat = None
                        await tm.broadcast(table_id, summary)
                    else:
                        session = await tm.get_table(table_id)
                        if session is None or my_seat is None or my_seat != session.owner_seat:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Only the table owner can remove bots",
                            })
                            continue
                        p = session.game_state.player(target)
                        mid_hand = session is not None and session.game_state.phase not in (
                            GamePhase.WAITING, GamePhase.SHOWDOWN,
                        )
                        if p is None or p.is_human:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Can only remove bot seats",
                            })
                            continue
                        if mid_hand:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Cannot remove players mid-hand",
                            })
                            continue
                        summary = await tm.stand_up(table_id, target)
                        await tm.broadcast(table_id, summary)

                elif msg_type == "start_hand":
                    session = await tm.get_table(table_id)
                    if session is None or my_seat is None or my_seat != session.owner_seat:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Only the table owner can start a hand",
                        })
                        continue
                    broadcast_msg = await tm.start_hand(table_id)
                    await tm.broadcast(table_id, broadcast_msg)

                    # Send private hole cards to each human player
                    session = await tm.get_table(table_id)
                    if session:
                        for p in session.game_state.players:
                            if p.hole_cards is not None and p.is_human:
                                await tm.send_to_player(table_id, p.seat_idx, {
                                    "type": "hole_cards",
                                    "cards": [str(c) for c in p.hole_cards],
                                })
                        # Drive bots, push end-of-hand stats, re-arm timer
                        await tm.after_action(table_id)

                elif msg_type == "rebuy":
                    if my_seat is None:
                        await websocket.send_json({"type": "error", "message": "Sit down first"})
                        continue
                    amount = int(msg.get("amount", 0))
                    summary = await tm.rebuy(table_id, my_seat, amount)
                    await tm.broadcast(table_id, summary)

                elif msg_type == "player_action":
                    if my_seat is None:
                        await websocket.send_json({"type": "error", "message": "Sit down first"})
                        continue

                    action_type = str(msg["action"]).upper()
                    amount = int(msg.get("amount", 0))
                    state_msg = await tm.handle_player_action(
                        table_id, my_seat, action_type, amount,
                    )
                    await tm.broadcast(table_id, state_msg)
                    await tm.after_action(table_id)

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })

            except GameError as e:
                await websocket.send_json({"type": "error", "message": str(e)})
            except (KeyError, ValueError) as e:
                await websocket.send_json({"type": "error", "message": f"Bad request: {e}"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected from table %s (seat %s)", table_id, my_seat)
        if my_seat is not None:
            try:
                await tm.handle_disconnect(table_id, my_seat)
            except Exception:
                logger.exception("handle_disconnect failed for seat %s", my_seat)
    except Exception:
        logger.exception("Unexpected error in WebSocket for table %s", table_id)
