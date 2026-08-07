"""WebSocket endpoint — real-time game and trainer interaction.

Single endpoint ``/ws/{table_id}`` handles all in-game communication.
Messages are JSON with a ``type`` field (see protocol below).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..game_engine import GameError
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

            msg_type = msg.get("type", "")

            try:
                if msg_type == "sit_down":
                    seat_idx = int(msg["seat_idx"])
                    name = str(msg.get("name", f"Player{seat_idx}"))
                    buyin = msg.get("buyin")
                    is_human = bool(msg.get("is_human", True))

                    session = await tm.get_table(table_id)
                    if session is None:
                        await websocket.send_json({"type": "error", "message": "Table not found"})
                        continue

                    session.clients[seat_idx] = websocket
                    my_seat = seat_idx

                    summary = await tm.sit_down(table_id, seat_idx, name, buyin, is_human)
                    await tm.broadcast(table_id, summary)

                elif msg_type == "stand_up":
                    if my_seat is not None:
                        summary = await tm.stand_up(table_id, my_seat)
                        await tm.broadcast(table_id, summary)
                        my_seat = None

                elif msg_type == "start_hand":
                    broadcast_msg = await tm.start_hand(table_id)
                    await tm.broadcast(table_id, broadcast_msg)

                    # Send private hole cards to each player
                    session = await tm.get_table(table_id)
                    if session:
                        for p in session.game_state.players:
                            if p.hole_cards is not None and p.is_human:
                                await tm.send_to_player(table_id, p.seat_idx, {
                                    "type": "hole_cards",
                                    "cards": [str(c) for c in p.hole_cards],
                                })

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
                await tm.stand_up(table_id, my_seat)
            except Exception:
                pass
    except Exception:
        logger.exception("Unexpected error in WebSocket for table %s", table_id)
