"""Async database engine and session factory (SQLite via aiosqlite)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..config import app_config


class Base(DeclarativeBase):
    pass


engine = create_async_engine(app_config.database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def configure(url: str) -> None:
    """Rebuild engine/session factory — used by tests to point at a temp DB."""
    global engine, SessionLocal
    engine = create_async_engine(url)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from . import records  # noqa: F401 — register models on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
