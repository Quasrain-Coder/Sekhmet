"""Fire-and-forget persistence for completed hands."""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from . import db
from .records import HandRecord, PlayerStatsRecord

logger = logging.getLogger(__name__)


async def record_hand(table_id, players_meta, board, actions, awards) -> None:
    """Persist one completed hand. Never raises."""
    try:
        async with db.SessionLocal() as s:
            s.add(HandRecord(
                table_id=table_id,
                players=json.dumps(players_meta),
                board=json.dumps(board),
                actions=json.dumps(actions),
                awards=json.dumps(awards),
            ))
            await s.commit()
    except Exception:
        logger.exception("failed to record hand for table %s", table_id)


async def upsert_player_stats(deltas: list[dict]) -> None:
    """Accumulate per-name stats for human players. Never raises."""
    try:
        async with db.SessionLocal() as s:
            for d in deltas:
                if not d.get("is_human"):
                    continue
                row = (await s.execute(
                    select(PlayerStatsRecord).where(
                        PlayerStatsRecord.name == d["name"])
                )).scalar_one_or_none()
                if row is None:
                    row = PlayerStatsRecord(name=d["name"], hands=0, wins=0, net_chips=0)
                    s.add(row)
                row.hands += 1
                row.wins += 1 if d.get("won") else 0
                row.net_chips += d.get("delta", 0)
            await s.commit()
    except Exception:
        logger.exception("failed to upsert player stats")


def schedule_recording(coro) -> None:
    """Fire-and-forget a recording coroutine (errors logged inside)."""
    asyncio.create_task(coro)
