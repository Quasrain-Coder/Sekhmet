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


# Columns added to existing tables after their first deployment.  The
# user's live SQLite file predates them — ``create_all`` never alters
# existing tables, so patch them in place.
_MIGRATIONS: dict[str, list[str]] = {
    "user_stats": [
        "total_buyin INTEGER NOT NULL DEFAULT 0",
        "vpip_hands INTEGER NOT NULL DEFAULT 0",
        "pfr_hands INTEGER NOT NULL DEFAULT 0",
        "showdowns INTEGER NOT NULL DEFAULT 0",
        "showdown_wins INTEGER NOT NULL DEFAULT 0",
    ],
    "hand_records": [
        "small_blind INTEGER",
        "big_blind INTEGER",
    ],
}


def _migrate_columns(conn) -> None:
    """Add any missing columns from ``_MIGRATIONS`` (idempotent)."""
    from sqlalchemy import text

    for table, columns in _MIGRATIONS.items():
        existing = {
            row[1]
            for row in conn.execute(text(f"PRAGMA table_info({table})"))
        }
        for column in columns:
            name = column.split()[0]
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column}"))


async def init_db() -> None:
    from . import records  # noqa: F401 — register models on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_columns)
