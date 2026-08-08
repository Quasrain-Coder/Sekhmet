"""REST endpoints for game table management."""

from fastapi import APIRouter, HTTPException

from . import table_manager as tm

router = APIRouter(prefix="/api/game", tags=["game"])


@router.post("/tables")
async def create_table(body: dict | None = None):
    """Create a new poker table, optionally with a room config."""
    try:
        cfg = tm.TableConfig.from_dict(body or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    tid = await tm.create_table(cfg)
    return {"table_id": tid}


@router.get("/tables/{table_id}")
async def get_table(table_id: str):
    """Get the current state of a table."""
    from fastapi.responses import JSONResponse

    session = await tm.get_table(table_id)
    if session is None:
        return JSONResponse(status_code=404, content={"error": "Table not found"})

    gs = session.game_state
    return {
        "table_id": table_id,
        "phase": gs.phase.name,
        "players": [
            {"seat_idx": p.seat_idx, "name": p.name, "stack": p.stack}
            for p in gs.players
        ],
        "max_seats": session.n_seats,
        "small_blind": gs.small_blind,
        "big_blind": gs.big_blind,
    }


@router.get("/tables")
async def list_tables():
    """List all active tables."""
    # tm._tables is private; we'll expose a proper list method
    tables = []
    for tid in tm._tables:
        session = await tm.get_table(tid)
        if session:
            tables.append({
                "table_id": tid,
                "phase": session.game_state.phase.name,
                "n_players": len(session.player_names),
                "max_seats": session.n_seats,
            })
    return {"tables": tables}
