"""Read-only REST endpoints for persisted hand history and player stats."""

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..game_engine.game_state import GameState
from ..models import db
from ..models.records import HandRecord, UserStatsRecord
from ..trainer.hand_to_scenario import replay_full

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/hands")
async def list_hands(limit: int = 20, table_id: str | None = None):
    async with db.SessionLocal() as s:
        q = select(HandRecord).order_by(HandRecord.id.desc()).limit(max(0, min(limit, 100)))
        if table_id:
            q = q.where(HandRecord.table_id == table_id)
        rows = (await s.execute(q)).scalars().all()
    return {"hands": [
        {
            "id": r.id, "table_id": r.table_id,
            "players": json.loads(r.players), "board": json.loads(r.board),
            "actions": json.loads(r.actions), "awards": json.loads(r.awards),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]}


def _frame(gs: GameState, last_action: dict | None) -> dict:
    """Serialize one replay frame: the state *after* last_action was applied."""
    return {
        "phase": gs.phase.name,
        "board": [str(c) for c in gs.community_cards],
        "pot": gs.pot.total,
        "to_act": gs.current_player_idx,
        "players": [
            {
                "seat_idx": p.seat_idx, "name": p.name, "is_human": p.is_human,
                "stack": p.stack, "current_bet": p.current_bet,
                "is_active": p.is_active, "is_all_in": p.is_all_in,
                "hole_cards": ([str(c) for c in p.hole_cards]
                               if p.hole_cards else None),
            }
            for p in gs.players
        ],
        "last_action": last_action,
    }


@router.get("/hands/{hand_id}/replay")
async def replay_hand(hand_id: int):
    """Frame-by-frame replay of a recorded hand.

    The recorded action log is re-executed through the immutable engine,
    so every frame is an exact state of the original hand.  ``frames``
    has one entry per action plus the initial dealt state (frame 0);
    each frame's ``last_action`` is the action that produced it.
    """
    async with db.SessionLocal() as s:
        r = await s.get(HandRecord, hand_id)
    if r is None:
        raise HTTPException(status_code=404, detail="hand not found")

    players = json.loads(r.players)
    actions = json.loads(r.actions)
    points, final, executed = replay_full(
        players, json.loads(r.board), actions,
        r.small_blind or 5, r.big_blind or 10,
    )
    frames = []
    if executed == 0:
        frames.append(_frame(final, None))
    else:
        frames.append(_frame(points[0][0], None))
        for i in range(1, executed):
            frames.append(_frame(points[i][0], actions[i - 1]))
        frames.append(_frame(final, actions[executed - 1]))
    return {
        "id": r.id, "table_id": r.table_id,
        "created_at": r.created_at.isoformat(),
        "small_blind": r.small_blind, "big_blind": r.big_blind,
        "awards": json.loads(r.awards),
        "frames": frames,
    }


@router.get("/players")
async def list_players():
    """Ranked per-account stats — guest play is never recorded."""
    async with db.SessionLocal() as s:
        rows = (await s.execute(
            select(UserStatsRecord).order_by(UserStatsRecord.net_chips.desc())
        )).scalars().all()
    return {"players": [
        {"name": r.username, "hands": r.hands, "wins": r.wins,
         "net_chips": r.net_chips, "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]}
