"""Account registration, login and personal profile.

Passwords are hashed with PBKDF2-HMAC-SHA256 (per-user random salt, no
extra dependencies).  Sessions are in-memory tokens — a server restart
logs everyone out, which is fine at this scale.  Logged-in players get
their results recorded against their account; guest play is not counted.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..models import db
from ..models.records import UserRecord, UserStatsRecord

router = APIRouter(prefix="/api/auth", tags=["auth"])

# token → user id (in-memory session store)
_tokens: dict[str, int] = {}

_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS,
    ).hex()


def resolve_token(token: str | None) -> int | None:
    """Map a session token to a user id, or None (guest / invalid)."""
    if not token:
        return None
    return _tokens.get(token)


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

    token = secrets.token_hex(24)
    _tokens[token] = user.id
    return {"token": token, "username": username}


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

    token = secrets.token_hex(24)
    _tokens[token] = user.id
    return {"token": token, "username": user.username}


@router.get("/me")
async def me(token: str):
    user_id = _tokens.get(token)
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

    return {
        "username": user.username,
        "stats": {
            "hands": stats.hands if stats is not None else 0,
            "wins": stats.wins if stats is not None else 0,
            "net_chips": stats.net_chips if stats is not None else 0,
        },
    }
