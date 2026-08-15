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
