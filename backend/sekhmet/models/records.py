"""ORM models for hand history and persistent player stats."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HandRecord(Base):
    __tablename__ = "hand_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_id: Mapped[str] = mapped_column(String(16), index=True)
    players: Mapped[str] = mapped_column(Text)   # JSON array
    board: Mapped[str] = mapped_column(Text)     # JSON array of card strings
    actions: Mapped[str] = mapped_column(Text)   # JSON array
    awards: Mapped[str] = mapped_column(Text)    # JSON array
    # Blinds at deal time — enables per-stakes aggregation.  NULL on
    # rows recorded before this column existed.
    small_blind: Mapped[int | None] = mapped_column(Integer, nullable=True)
    big_blind: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PlayerStatsRecord(Base):
    __tablename__ = "player_stats"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    hands: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    net_chips: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class UserRecord(Base):
    """Registered account (username + password)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class UserStatsRecord(Base):
    """Per-account lifetime stats — only logged-in players are recorded;
    guest-mode play never reaches this table."""

    __tablename__ = "user_stats"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    hands: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    net_chips: Mapped[int] = mapped_column(Integer, default=0)
    # Poker-tracking metrics (accumulated per hand at showdown):
    total_buyin: Mapped[int] = mapped_column(Integer, default=0)     # chips bought (incl. rebuys)
    vpip_hands: Mapped[int] = mapped_column(Integer, default=0)      # hands with a voluntary preflop chip
    pfr_hands: Mapped[int] = mapped_column(Integer, default=0)       # hands with a preflop raise
    showdowns: Mapped[int] = mapped_column(Integer, default=0)       # hands reaching showdown
    showdown_wins: Mapped[int] = mapped_column(Integer, default=0)   # of those, won the pot
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
