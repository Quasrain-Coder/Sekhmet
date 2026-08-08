"""FastAPI application entry point.

Start with::

    cd backend && source .venv/bin/activate
    uvicorn sekhmet.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import game, trainer, ws

app = FastAPI(
    title="Sekhmet",
    description="Texas Hold'em game & training platform",
    version="0.1.0",
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
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
