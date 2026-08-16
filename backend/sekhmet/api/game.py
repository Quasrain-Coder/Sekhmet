"""REST endpoints for game table management."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from . import table_manager as tm
from ..models import db, records

router = APIRouter(prefix="/api/game", tags=["game"])


@router.post("/tables")
async def create_table(body: dict | None = None):
    """Create a new poker table, optionally with a room config."""
    try:
        cfg = tm.TableConfig.from_dict(body or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except tm.GameError as e:
        raise HTTPException(status_code=429, detail=str(e))
    tid = await tm.create_table(cfg)
    session = await tm.get_table(tid)
    return {"table_id": tid, "owner_token": session.owner_token}


@router.get("/tables/{table_id}")
async def get_table(table_id: str):
    """Get the current state of a table."""
    from fastapi.responses import JSONResponse

    session = await tm.get_table(table_id)
    if session is None:
        return JSONResponse(status_code=404, content={"error": "Table not found"})

    return tm.table_info(session)


@router.get("/tables/{table_id}/players/{seat_idx}/profile")
async def player_profile(table_id: str, seat_idx: int):
    """Profile for one seat.

    Logged-in players get their account lifetime stats (user_stats);
    guests and bots get the table-local record only.
    """
    from fastapi.responses import JSONResponse

    session = await tm.get_table(table_id)
    if session is None:
        return JSONResponse(status_code=404, content={"error": "Table not found"})
    if seat_idx not in session.player_names:
        return JSONResponse(status_code=404, content={"error": "Seat not found"})

    gs = session.game_state
    p = gs.player(seat_idx)
    st = session.stats.get(seat_idx)
    buyin = session.total_buyin.get(seat_idx, p.stack if p is not None else 0)

    profile = {
        "seat_idx": seat_idx,
        "name": session.player_names[seat_idx],
        "is_human": p.is_human if p is not None else True,
        "bot_level": session.bot_levels.get(seat_idx),
        "stack": p.stack if p is not None else buyin,
        "buyin": buyin,
        "hands": st.hands if st else 0,
        "wins": st.wins if st else 0,
        "net_chips": (p.stack if p is not None else buyin) - buyin,
        "account": None,
    }

    user_id = session.user_ids.get(seat_idx)
    if user_id is not None:
        async with db.SessionLocal() as s:
            user = (await s.execute(
                select(records.UserRecord).where(records.UserRecord.id == user_id)
            )).scalar_one_or_none()
            stats = (await s.execute(
                select(records.UserStatsRecord)
                .where(records.UserStatsRecord.user_id == user_id)
            )).scalar_one_or_none()
        if user is not None:
            profile["account"] = {
                "username": user.username,
                "hands": stats.hands if stats is not None else 0,
                "wins": stats.wins if stats is not None else 0,
                "net_chips": stats.net_chips if stats is not None else 0,
            }
    return profile


@router.get("/tables")
async def list_tables():
    """List all active tables."""
    # tm._tables is private; we'll expose a proper list method
    tables = []
    for tid in tm._tables:
        session = await tm.get_table(tid)
        if session:
            tables.append(tm.table_info(session))
    return {"tables": tables}
