"""Account registration, login and personal profile.

Passwords are hashed with PBKDF2-HMAC-SHA256 (per-user random salt, no
extra dependencies).  Sessions are signed stateless tokens
(``base64(payload).hmac``) with an expiry — they survive backend
restarts, so a redeploy no longer logs everyone out.  Logged-in players
get their results recorded against their account; guest play is not
counted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..config import app_config
from ..models import db
from ..models import records
from ..models.records import UserRecord, UserStatsRecord

router = APIRouter(prefix="/api/auth", tags=["auth"])

_PBKDF2_ITERATIONS = 100_000

# Signing key: env override for deployment, stable default otherwise.
_AUTH_SECRET = os.environ.get("SEKHMET_AUTH_SECRET", "sekhmet-dev-secret")


def _issue_token(user_id: int) -> str:
    """Signed token carrying user id + expiry."""
    exp = int(time.time()) + app_config.game.auth_token_ttl_seconds
    payload = base64.urlsafe_b64encode(f"{user_id}:{exp}".encode()).decode()
    sig = hmac.new(_AUTH_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    return f"{payload}.{sig}"


def resolve_token(token: str | None) -> int | None:
    """Map a session token to a user id, or None (guest / invalid)."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(_AUTH_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        user_id, exp = decoded.split(":", 1)
        if int(exp) < time.time():
            return None
        return int(user_id)
    except Exception:
        return None


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS,
    ).hex()


@router.post("/register")
async def register(body: dict):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not (2 <= len(username) <= 32):
        raise HTTPException(status_code=400, detail="Username must be 2-32 characters")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    async with db.SessionLocal() as s:
        exists = (await s.execute(
            select(UserRecord.id).where(UserRecord.username == username)
        )).scalar()
        if exists is not None:
            raise HTTPException(status_code=409, detail="Username already taken")
        salt = secrets.token_hex(16)
        user = UserRecord(
            username=username,
            password_hash=hash_password(password, salt),
            salt=salt,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)

    return {"token": _issue_token(user.id), "username": username}


@router.post("/login")
async def login(body: dict):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))

    async with db.SessionLocal() as s:
        user = (await s.execute(
            select(UserRecord).where(UserRecord.username == username)
        )).scalar_one_or_none()

    if user is None or not secrets.compare_digest(
        user.password_hash, hash_password(password, user.salt)
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {"token": _issue_token(user.id), "username": user.username}


@router.get("/me")
async def me(token: str):
    user_id = resolve_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not logged in")

    async with db.SessionLocal() as s:
        user = (await s.execute(
            select(UserRecord).where(UserRecord.id == user_id)
        )).scalar_one_or_none()
        stats = (await s.execute(
            select(UserStatsRecord).where(UserStatsRecord.user_id == user_id)
        )).scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")

    hands = stats.hands if stats is not None else 0
    return {
        "username": user.username,
        "stats": {
            "hands": hands,
            "wins": stats.wins if stats is not None else 0,
            "net_chips": stats.net_chips if stats is not None else 0,
        },
        # Full profile shape — matches the in-game profile endpoint so
        # the lobby's "My Profile" can render the same metrics.
        "profile": {
            "total_buyin": stats.total_buyin if stats is not None else 0,
            "vpip_rate": (stats.vpip_hands / hands)
                         if stats is not None and hands else None,
            "pfr_rate": (stats.pfr_hands / hands)
                        if stats is not None and hands else None,
            "wtsd": (stats.showdown_wins / stats.showdowns)
                    if stats is not None and stats.showdowns else None,
            "last_active": (stats.updated_at.isoformat()
                            if stats is not None and stats.updated_at
                            else None),
            "recent_hands": await records.recent_hands_for(s, user.username),
            "by_blinds": await records.stats_by_blinds(s, user.username),
        },
    }
