"""ORM models for hand history and persistent player stats."""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, select
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



async def recent_hands_for(session, username: str, limit: int = 10) -> list[dict]:
    """Last *limit* recorded hands the account played in, with their
    own net result derived from stack_before/stack_after."""
    q = (select(HandRecord)
         .where(HandRecord.players.contains(f'"name": "{username}"'))
         .order_by(HandRecord.id.desc())
         .limit(max(0, min(limit, 20))))
    rows = (await session.execute(q)).scalars().all()
    out = []
    for r in rows:
        players = _json.loads(r.players)
        me = next((pl for pl in players if pl.get("name") == username), None)
        if me is None:
            continue
        winners = {a["seat_idx"] for a in _json.loads(r.awards)}
        net = None
        if "stack_before" in me and "stack_after" in me:
            net = me["stack_after"] - me["stack_before"]
        out.append({
            "table_id": r.table_id,
            "board": _json.loads(r.board),
            "won": me["seat_idx"] in winners,
            "net": net,
            "small_blind": r.small_blind,
            "big_blind": r.big_blind,
            "created_at": r.created_at.isoformat(),
        })
    return out


async def stats_by_blinds(session, username: str, cap: int = 500) -> list[dict]:
    """Lifetime results grouped by blind level (over the last *cap*
    hands containing the account)."""
    q = (select(HandRecord)
         .where(HandRecord.players.contains(f'"name": "{username}"'))
         .order_by(HandRecord.id.desc())
         .limit(max(0, min(cap, 1000))))
    rows = (await session.execute(q)).scalars().all()
    groups: dict[tuple[int | None, int | None], dict] = {}
    for r in rows:
        players = _json.loads(r.players)
        me = next((pl for pl in players if pl.get("name") == username), None)
        if me is None:
            continue
        key = (r.small_blind, r.big_blind)
        g = groups.setdefault(key, {"hands": 0, "wins": 0, "net_chips": 0})
        g["hands"] += 1
        winners = {a["seat_idx"] for a in _json.loads(r.awards)}
        if me["seat_idx"] in winners:
            g["wins"] += 1
        if "stack_before" in me and "stack_after" in me:
            g["net_chips"] += me["stack_after"] - me["stack_before"]
    return [
        {"small_blind": sb, "big_blind": bb, **g}
        for (sb, bb), g in sorted(groups.items(), key=lambda kv: kv[0][1] or 0)
    ]


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


class TrainingAttemptRecord(Base):
    """One scored training decision by a logged-in account.

    Guests are never recorded — same policy as game hands.  One row per
    submit (retries included), so "latest attempt per scenario" is a
    group-by rather than an update-in-place; full history doubles as the
    progress-curve data source.
    """

    __tablename__ = "training_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(64))
    scenario_id: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(32))
    difficulty: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(Text)          # JSON {"type", "amount"}
    score_total: Mapped[float] = mapped_column(Float)
    action_match: Mapped[float] = mapped_column(Float)
    sizing_precision: Mapped[float] = mapped_column(Float)
    timing_judgment: Mapped[float] = mapped_column(Float)
    is_optimal: Mapped[bool] = mapped_column(Boolean, default=False)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    time_taken_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


async def attempts_recent(session, user_id: int, limit: int = 50) -> list[dict]:
    """Most recent *limit* attempts, oldest first (chart x-axis order)."""
    q = (select(TrainingAttemptRecord)
         .where(TrainingAttemptRecord.user_id == user_id)
         .order_by(TrainingAttemptRecord.id.desc())
         .limit(max(1, min(limit, 200))))
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "scenario_id": r.scenario_id,
            "category": r.category,
            "score": r.score_total,
            "is_optimal": r.is_optimal,
            "created_at": r.created_at.isoformat(),
        }
        for r in reversed(rows)
    ]


async def category_breakdown(session, user_id: int) -> list[dict]:
    """Per-category aggregate: attempt count, mean score, optimal rate."""
    q = select(TrainingAttemptRecord).where(TrainingAttemptRecord.user_id == user_id)
    rows = (await session.execute(q)).scalars().all()
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(
            r.category, {"attempts": 0, "score_sum": 0.0, "optimal": 0})
        g["attempts"] += 1
        g["score_sum"] += r.score_total
        if r.is_optimal:
            g["optimal"] += 1
    return [
        {
            "category": cat,
            "attempts": g["attempts"],
            "avg_score": round(g["score_sum"] / g["attempts"], 1),
            "optimal_rate": round(g["optimal"] / g["attempts"], 3),
        }
        for cat, g in sorted(groups.items(), key=lambda kv: kv[1]["score_sum"] / kv[1]["attempts"])
    ]


async def mistake_scenarios(session, user_id: int, limit: int = 50) -> list[dict]:
    """Wrong-answer book: latest attempt per scenario, keep the ones
    whose *latest* try is still non-optimal (fixed ones drop out).
    Ordered most-recently-wrong first."""
    q = (select(TrainingAttemptRecord)
         .where(TrainingAttemptRecord.user_id == user_id)
         .order_by(TrainingAttemptRecord.id.desc()))
    rows = (await session.execute(q)).scalars().all()
    latest: dict[str, TrainingAttemptRecord] = {}
    counts: dict[str, int] = {}
    for r in rows:  # newest → oldest, so first sight of a scenario is its latest
        counts[r.scenario_id] = counts.get(r.scenario_id, 0) + 1
        latest.setdefault(r.scenario_id, r)
    out = [
        {
            "scenario_id": r.scenario_id,
            "category": r.category,
            "difficulty": r.difficulty,
            "last_score": r.score_total,
            "attempts": counts[r.scenario_id],
            "last_tried_at": r.created_at.isoformat(),
        }
        for r in latest.values() if not r.is_optimal
    ]
    return out[:max(1, min(limit, 100))]


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
