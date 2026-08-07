"""Blind structures for cash games and multi-table tournaments (MTT)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlindLevel:
    """A single blind level in a tournament structure."""

    level: int
    small_blind: int
    big_blind: int
    ante: int = 0
    duration_minutes: int = 10  # how long this level lasts


# ---------------------------------------------------------------------------
# Cash game — fixed blinds
# ---------------------------------------------------------------------------


def cash_game_blinds(
    small_blind: int = 5,
    big_blind: int = 10,
) -> tuple[int, int]:
    """Return (sb, bb) for a cash game.  Blinds are constant."""
    return (small_blind, big_blind)


# ---------------------------------------------------------------------------
# MTT — escalating blinds
# ---------------------------------------------------------------------------


# Standard online MTT structure (starting 1500 chips, 10-min levels)
STANDARD_MTT_STRUCTURE: tuple[BlindLevel, ...] = (
    BlindLevel(level=1,  small_blind=5,   big_blind=10),
    BlindLevel(level=2,  small_blind=10,  big_blind=20),
    BlindLevel(level=3,  small_blind=15,  big_blind=30),
    BlindLevel(level=4,  small_blind=20,  big_blind=40),
    BlindLevel(level=5,  small_blind=30,  big_blind=60),
    BlindLevel(level=6,  small_blind=40,  big_blind=80),
    BlindLevel(level=7,  small_blind=50,  big_blind=100),
    BlindLevel(level=8,  small_blind=75,  big_blind=150),
    BlindLevel(level=9,  small_blind=100, big_blind=200, ante=25),
    BlindLevel(level=10, small_blind=150, big_blind=300, ante=25),
    BlindLevel(level=11, small_blind=200, big_blind=400, ante=50),
    BlindLevel(level=12, small_blind=300, big_blind=600, ante=75),
    BlindLevel(level=13, small_blind=400, big_blind=800, ante=100),
    BlindLevel(level=14, small_blind=500, big_blind=1000, ante=125),
    BlindLevel(level=15, small_blind=750, big_blind=1500, ante=150),
)

# Fast turbo structure (5-min levels)
TURBO_MTT_STRUCTURE: tuple[BlindLevel, ...] = tuple(
    BlindLevel(level=bl.level, small_blind=bl.small_blind,
               big_blind=bl.big_blind, ante=bl.ante, duration_minutes=5)
    for bl in STANDARD_MTT_STRUCTURE
)


def get_mtt_blinds(
    level: int,
    structure: tuple[BlindLevel, ...] = STANDARD_MTT_STRUCTURE,
) -> BlindLevel | None:
    """Return the blind level config for a given MTT level (1-indexed)."""
    for bl in structure:
        if bl.level == level:
            return bl
    return None


def blinds_for_level(level: int, base_big_blind: int = 10) -> tuple[int, int]:
    """Convenience: return (sb, bb) for an MTT-like escalating structure.

    Simple doubling every 3 levels, capped.
    """
    doubling = (level - 1) // 3
    mult = 2 ** doubling
    bb = min(base_big_blind * mult, 100_000)
    sb = bb // 2
    return sb, bb
