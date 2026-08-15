"""Fire-and-forget persistence for completed hands."""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

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
                # Atomic UPSERT: a read-modify-write (select → mutate → commit)
                # loses updates when hands at different tables finish
                # concurrently — all readers see the same stale row.  The
                # database does the increment in one statement instead.
                stmt = sqlite_insert(PlayerStatsRecord).values(
                    name=d["name"],
                    hands=1,
                    wins=1 if d.get("won") else 0,
                    net_chips=d.get("delta", 0),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["name"],
                    set_={
                        "hands": PlayerStatsRecord.hands + stmt.excluded.hands,
                        "wins": PlayerStatsRecord.wins + stmt.excluded.wins,
                        "net_chips": PlayerStatsRecord.net_chips + stmt.excluded.net_chips,
                    },
                )
                await s.execute(stmt)
            await s.commit()
    except Exception:
        logger.exception("failed to upsert player stats")


def schedule_recording(coro) -> None:
    """Fire-and-forget a recording coroutine (errors logged inside)."""
    asyncio.create_task(coro)
