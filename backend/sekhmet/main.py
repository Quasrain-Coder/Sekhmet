"""FastAPI application entry point.

Start with::

    cd backend && source .venv/bin/activate
    uvicorn sekhmet.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import asyncio
from contextlib import asynccontextmanager

from .api import game, history, trainer, ws
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
app.include_router(game.router)
app.include_router(trainer.router)
app.include_router(history.router)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
