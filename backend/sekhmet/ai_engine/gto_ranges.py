"""Preflop range charts for the GTO-style Level 4 bot.

The charts are simplified approximations of public GTO solver outputs
(open-raise / 3-bet / call / BB-defend ranges by position), stored as
compact range strings plus optional mixed frequencies.  They are data,
not logic: the decision code only asks "is this hand in that range,
and at what frequency?".

Range spec grammar (handled by ``expand_range_spec``)::

    "77+"     pairs 77..AA
    "TT-88"   pair span (TT, 99, 88)
    "A9s+"    kicker-plus, high card fixed: A9s..AKs
    "97s+"    connected-plus, both cards ascend: 97s, T8s, J9s, QTs, KJs
    "ATo+"    kicker-plus offsuit: ATo..AKo
    "JTs"     exact hand
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game_engine.deck import Card

RANK_CHARS = "23456789TJQKA"

# Hand key: (high_rank, low_rank, kind) where kind is "s" | "o" | "p".
HandKey = tuple[int, int, str]
Range = dict[HandKey, float]


def _rank_value(ch: str) -> int:
    return RANK_CHARS.index(ch) + 2


def expand_range_spec(spec: str) -> set[HandKey]:
    """Expand one range spec ("A9s+", "77+", "TT-88", "JTs", ...)."""
    spec = spec.strip()
    if "-" in spec:  # pair span, e.g. "TT-88"
        hi_ch, lo_ch = spec.split("-")
        hi = _rank_value(hi_ch[0])
        lo = _rank_value(lo_ch[0])
        return {(v, v, "p") for v in range(lo, hi + 1)}
    plus = spec.endswith("+")
    if plus:
        spec = spec[:-1]
    kind = "o"
    if spec.endswith("s"):
        kind, spec = "s", spec[:-1]
    elif spec.endswith("o"):
        kind, spec = "o", spec[:-1]
    hi, lo = _rank_value(spec[0]), _rank_value(spec[1])
    if hi == lo:  # pair
        top = 14 if plus else hi
        return {(v, v, "p") for v in range(hi, top + 1)}
    if not plus:
        return {(hi, lo, kind)}
    if hi <= 10:  # T-high or lower: both cards ascend (97s+ → T8s → J9s…)
        hands: set[HandKey] = set()
        h, l = hi, lo
        while h <= 14 and l >= 2:
            hands.add((h, l, kind))
            h += 1
            l += 1
        return hands
    # J-high or higher: kicker-plus (A9s+ → A9s..AKs, Q6s+ → Q6s..QJs)
    return {(hi, l, kind) for l in range(lo, hi)}


def make_range(specs: str, weights: dict[str, float] | None = None) -> Range:
    """Build a range dict: listed hands at weight 1.0, overrides from
    *weights* (mixed strategies at their frequency)."""
    rng: Range = {}
    for spec in specs.split(","):
        for hand in expand_range_spec(spec):
            rng[hand] = 1.0
    for spec, freq in (weights or {}).items():
        for hand in expand_range_spec(spec):
            rng[hand] = freq
    return rng


def hand_key(c1: "Card", c2: "Card") -> HandKey:
    """Key for the exact hole-card pair held."""
    r1, r2 = c1.rank.value, c2.rank.value
    hi, lo = max(r1, r2), min(r1, r2)
    if hi == lo:
        return (hi, lo, "p")
    return (hi, lo, "s" if c1.suit == c2.suit else "o")


def range_frequency(rng: Range, c1: "Card", c2: "Card") -> float:
    """0.0–1.0 play frequency of this exact hand in *rng*."""
    return rng.get(hand_key(c1, c2), 0.0)


# ---------------------------------------------------------------------------
# Charts (approximations of public GTO solver outputs, simplified)
# ---------------------------------------------------------------------------

# Open-raise (RFI) by position.
RFI: dict[str, Range] = {
    "utg": make_range(
        "77+, A9s+, KTs+, QTs+, JTs, T9s, AQo+, KQo",
        {"66": .5, "A8s": .5, "A5s": .5, "A4s": .5, "KJo": .5},
    ),
    "mp": make_range(
        "66+, A8s+, A5s, A4s, K9s+, QTs+, JTs, T9s, AJo+, KQo",
        {"55": .5, "A6s": .5, "Q9s": .5, "KJo": .5},
    ),
    "co": make_range(
        "55+, A2s+, K7s+, Q9s+, J9s+, T9s, 98s, ATo+, KTo, KJo+, QJo",
        {"54s": .5, "87s": .5, "JTo": .5},
    ),
    "btn": make_range(
        "22+, A2s+, K2s+, Q6s+, J7s+, T7s+, 97s+, 86s+, 75s+, 65s, 54s, "
        "A8o+, KTo+, QTo+, JTo, T9o",
        {"A7o": .5, "K9o": .5, "Q9o": .5, "98o": .5},
    ),
    "sb": make_range(
        "22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 97s+, 87s, 76s, "
        "A9o+, KTo+, QTo+, JTo",
        {"A2o": .5, "A3o": .5, "A4o": .5, "A5o": .5,
         "A6o": .5, "A7o": .5, "A8o": .5},
    ),
}

# 3-bet vs an open, keyed by the opener's position bucket.
THREE_BET: dict[str, Range] = {
    "utg": make_range("QQ+, AKs, AKo", {"AQs": .5, "JJ": .5}),
    "mp": make_range("QQ+, AKs, AQs, AKo",
                     {"JJ": .5, "AQo": .5, "A5s": .25, "A4s": .25}),
    "co": make_range("JJ+, AQs+, AQo+, A5s, A4s",
                     {"TT": .5, "KQs": .5, "AJo": .25}),
    "btn": make_range("JJ+, AQs+, AQo+, A5s, A4s, KQs",
                      {"TT": .5, "AJo": .5, "KJs": .5, "76s": .25, "65s": .25}),
    "sb": make_range("JJ+, AQs+, AQo+, A5s, A4s, KQs",
                     {"TT": .5, "AJo": .5, "KJs": .5, "76s": .25, "65s": .25}),
}

# Flat-call vs an open (in position), keyed by the opener's bucket.
CALL_VS_OPEN: dict[str, Range] = {
    "utg": make_range("TT-88, AQs, AJs, KQs, QJs, JTs, T9s, 98s, AQo",
                      {"AJo": .25}),
    "mp": make_range("TT-77, AQs, AJs, KQs, QJs, JTs, T9s, 98s, AQo",
                     {"AJo": .5, "KQo": .5}),
    "co": make_range("TT-66, AJs, ATs, KQs, KJs, KTs, QJs, JTs, T9s, 98s, "
                     "87s, AQo, AJo, KQo", {}),
    "btn": make_range("77-22, ATs, A9s, A8s, KTs, QTs, JTs, T9s, 98s, "
                      "AJo, ATo, KQo, KJo, QJo", {}),
    "sb": make_range("88-22, AQs, AJs, ATs, KQs, KJs, QJs, JTs, T9s, "
                     "AQo, AJo", {"KQo": .5}),
}

# Big blind defense vs an open.
BB_DEFEND_CALL: Range = make_range(
    "22+, A2s+, K2s+, Q2s+, J5s+, T6s+, 96s+, 86s+, 76s, 65s, 54s, "
    "A2o+, K5o+, Q8o+, J8o+, T8o+, 98o, 87o, 76o", {}
)
BB_DEFEND_3BET: Range = make_range(
    "JJ+, AQs+, AQo+, KQs",
    {"TT": .5, "A5s": .5, "A4s": .5, "KQo": .5},
)

# 4-bet and call-vs-3bet ranges.
FOUR_BET: Range = make_range("KK+, AKs", {"QQ": .5, "AKo": .5, "A5s": .25})
CALL_VS_3BET: Range = make_range(
    "TT-66, AQs, AJs, KQs, QJs, JTs, T9s, 98s, AQo",
    {"AJo": .5, "KQo": .5},
)

# Limped pots: model limpers with the BB defense range.
LIMP_RANGE: Range = BB_DEFEND_CALL
