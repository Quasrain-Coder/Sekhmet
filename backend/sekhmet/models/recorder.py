"""Fire-and-forget persistence for completed hands."""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import db
from .records import HandRecord, PlayerStatsRecord, UserRecord, UserStatsRecord

logger = logging.getLogger(__name__)


async def record_hand(
    table_id, players_meta, board, actions, awards,
    small_blind: int | None = None, big_blind: int | None = None,
) -> None:
    """Persist one completed hand. Never raises."""
    try:
        async with db.SessionLocal() as s:
            s.add(HandRecord(
                table_id=table_id,
                players=json.dumps(players_meta),
                board=json.dumps(board),
                actions=json.dumps(actions),
                awards=json.dumps(awards),
                small_blind=small_blind,
                big_blind=big_blind,
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


async def upsert_user_stats(deltas: list[dict]) -> None:
    """Accumulate per-account stats for logged-in players.  Never raises.

    Guest seats (no ``user_id``) are skipped entirely — guest play is not
    counted anywhere.  The upsert is atomic for the same reason as
    upsert_player_stats: hands at different tables finish concurrently.
    """
    try:
        async with db.SessionLocal() as s:
            for d in deltas:
                user_id = d.get("user_id")
                if user_id is None:
                    continue
                username = (await s.execute(
                    select(UserRecord.username).where(UserRecord.id == user_id)
                )).scalar()
                stmt = sqlite_insert(UserStatsRecord).values(
                    user_id=user_id,
                    username=username if username is not None else d.get("username", ""),
                    hands=1,
                    wins=1 if d.get("won") else 0,
                    net_chips=d.get("delta", 0),
                    total_buyin=d.get("total_buyin", 0),
                    vpip_hands=1 if d.get("vpip") else 0,
                    pfr_hands=1 if d.get("pfr") else 0,
                    showdowns=1 if d.get("showdown") else 0,
                    showdown_wins=1 if d.get("showdown_win") else 0,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["user_id"],
                    set_={
                        "hands": UserStatsRecord.hands + stmt.excluded.hands,
                        "wins": UserStatsRecord.wins + stmt.excluded.wins,
                        "net_chips": UserStatsRecord.net_chips + stmt.excluded.net_chips,
                        "total_buyin": UserStatsRecord.total_buyin + stmt.excluded.total_buyin,
                        "vpip_hands": UserStatsRecord.vpip_hands + stmt.excluded.vpip_hands,
                        "pfr_hands": UserStatsRecord.pfr_hands + stmt.excluded.pfr_hands,
                        "showdowns": UserStatsRecord.showdowns + stmt.excluded.showdowns,
                        "showdown_wins": UserStatsRecord.showdown_wins + stmt.excluded.showdown_wins,
                    },
                )
                await s.execute(stmt)
            await s.commit()
    except Exception:
        logger.exception("failed to upsert user stats")


def schedule_recording(coro) -> None:
    """Fire-and-forget a recording coroutine (errors logged inside)."""
    asyncio.create_task(coro)
