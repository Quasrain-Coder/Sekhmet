"""FastAPI application entry point.

Start with::

    cd backend && source .venv/bin/activate
    uvicorn sekhmet.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from .api import auth, game, history, trainer, ws
from .api import table_manager as tm


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .models.db import init_db
    await init_db()
    sweeper = asyncio.create_task(tm.sweeper_loop())
    try:
        yield
    finally:
        sweeper.cancel()


app = FastAPI(
    title="Sekhmet",
    description="Texas Hold'em game & training platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router)
app.include_router(game.router)
app.include_router(trainer.router)
app.include_router(history.router)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


def mount_spa(application: FastAPI, static_dir: Path) -> bool:
    """Serve a built SPA from *static_dir*; unknown paths fall back to
    index.html so client-side routes (/history/42, ...) load directly.

    Returns False (and mounts nothing) when no build exists — the dev
    flow (vite dev server on 5173) keeps working unchanged.
    """
    index = static_dir / "index.html"
    if not index.is_file():
        return False
    root = static_dir.resolve()

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path:
            candidate = (static_dir / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        return FileResponse(index)

    return True


_SPA_DIR = Path(os.environ["SEKHMET_STATIC_DIR"]) if os.environ.get("SEKHMET_STATIC_DIR") \
    else Path(__file__).resolve().parents[2] / "frontend" / "dist"
mount_spa(app, _SPA_DIR)
