"""Read-only REST endpoints for persisted hand history and player stats."""

import json

from fastapi import APIRouter
from sqlalchemy import select

from ..models import db
from ..models.records import HandRecord, PlayerStatsRecord

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/hands")
async def list_hands(limit: int = 20, table_id: str | None = None):
    async with db.SessionLocal() as s:
        q = select(HandRecord).order_by(HandRecord.id.desc()).limit(min(limit, 100))
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


@router.get("/players")
async def list_players():
    async with db.SessionLocal() as s:
        rows = (await s.execute(
            select(PlayerStatsRecord).order_by(PlayerStatsRecord.net_chips.desc())
        )).scalars().all()
    return {"players": [
        {"name": r.name, "hands": r.hands, "wins": r.wins,
         "net_chips": r.net_chips, "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]}
