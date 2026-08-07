# Sekhmet Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core Sekhmet poker platform — game engine, API layer, rule-based AI, and frontend game table — enabling single-player vs AI Texas Hold'em.

**Architecture:** Modular monolith — Python backend with `game_engine/`, `ai_engine/`, `api/` packages under `backend/sekhmet/`. React frontend in `frontend/`. WebSocket for real-time game state, REST for history/training. SQLite for storage.

**Tech Stack:** Python 3.12+, FastAPI, websockets, SQLAlchemy, React 19 + Vite + TypeScript

---

## Phase 1: Project Scaffolding

### Task 1: Backend project setup

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/sekhmet/__init__.py`
- Create: `backend/sekhmet/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml with dependencies**

```toml
[project]
name = "sekhmet"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "websockets>=13",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.20",
    "pyyaml>=6.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create sekhmet package init and config**

```python
# backend/sekhmet/__init__.py
"""Sekhmet — Texas Hold'em game and training platform."""

# backend/sekhmet/config.py
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class GameConfig:
    default_stack: int = 1000
    default_small_blind: int = 5
    default_big_blind: int = 10
    max_seats_per_table: int = 9
    action_timeout_seconds: int = 30

@dataclass
class ScoringWeights:
    action_match: float = 0.60
    sizing_precision: float = 0.25
    timing_judgment: float = 0.15

@dataclass
class AppConfig:
    game: GameConfig = field(default_factory=GameConfig)
    scoring: ScoringWeights = field(default_factory=ScoringWeights)
    database_url: str = "sqlite+aiosqlite:///sekhmet.db"
    data_dir: Path = Path("data")

app_config = AppConfig()
```

- [ ] **Step 3: Create test conftest with shared fixtures**

```python
# backend/tests/__init__.py
# backend/tests/conftest.py
import pytest
from sekhmet.config import AppConfig, GameConfig, ScoringWeights, app_config

@pytest.fixture
def game_config():
    return GameConfig(default_stack=100, default_small_blind=1, default_big_blind=2)

@pytest.fixture
def scoring_weights():
    return ScoringWeights()
```

- [ ] **Step 4: Install dependencies and run a smoke test**

Run: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/ -v`
Expected: 0 tests collected (no tests yet, but pytest runs)

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/sekhmet/__init__.py backend/sekhmet/config.py backend/tests/
git commit -m "feat: scaffold backend project with config and test setup"
```

---

## Phase 2: Game Engine — Data Primitives

### Task 2: Deck module (Card, Deck, shuffle, deal)

**Files:**
- Create: `backend/sekhmet/game_engine/__init__.py`
- Create: `backend/sekhmet/game_engine/deck.py`
- Create: `backend/tests/test_deck.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_deck.py
import pytest
from sekhmet.game_engine.deck import Card, Suit, Rank, Deck

def test_card_creation():
    card = Card(Rank.ACE, Suit.SPADES)
    assert card.rank == Rank.ACE
    assert card.suit == Suit.SPADES
    assert str(card) == "A♠"

def test_card_equality():
    assert Card(Rank.KING, Suit.HEARTS) == Card(Rank.KING, Suit.HEARTS)
    assert Card(Rank.KING, Suit.HEARTS) != Card(Rank.KING, Suit.SPADES)

def test_full_deck_has_52_cards():
    deck = Deck()
    assert len(deck.cards) == 52

def test_deck_is_unique():
    deck = Deck()
    assert len(set(deck.cards)) == 52

def test_shuffle_changes_order():
    deck1 = Deck()
    deck2 = Deck()
    deck2.shuffle()
    # Extremely unlikely to be same order after shuffle
    assert deck1.cards != deck2.cards or deck1.cards == deck2.cards

def test_deal_removes_cards_from_deck():
    deck = Deck()
    deck.shuffle()
    initial = len(deck.cards)
    cards = deck.deal(5)
    assert len(cards) == 5
    assert len(deck.cards) == initial - 5

def test_deal_too_many_raises():
    deck = Deck()
    with pytest.raises(ValueError):
        deck.deal(53)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_deck.py -v`
Expected: All FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement deck module**

```python
# backend/sekhmet/game_engine/__init__.py
"""Game engine — core Texas Hold'em logic."""

# backend/sekhmet/game_engine/deck.py
from enum import IntEnum, Enum
from dataclasses import dataclass
import random

class Suit(Enum):
    SPADES = "♠"
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"

class Rank(IntEnum):
    TWO = 2; THREE = 3; FOUR = 4; FIVE = 5; SIX = 6
    SEVEN = 7; EIGHT = 8; NINE = 9; TEN = 10
    JACK = 11; QUEEN = 12; KING = 13; ACE = 14

    def __str__(self):
        names = {11: "J", 12: "Q", 13: "K", 14: "A"}
        return names.get(self.value, str(self.value))

@dataclass(frozen=True)
class Card:
    rank: Rank
    suit: Suit

    def __str__(self):
        return f"{self.rank}{self.suit.value}"

class Deck:
    def __init__(self):
        self.cards = [Card(rank, suit) for rank in Rank for suit in Suit]

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self, n: int) -> list[Card]:
        if n > len(self.cards):
            raise ValueError(f"Cannot deal {n} cards, only {len(self.cards)} remain")
        dealt = self.cards[:n]
        self.cards = self.cards[n:]
        return dealt
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_deck.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/sekhmet/game_engine/ backend/tests/test_deck.py
git commit -m "feat: add deck module — Card, Suit, Rank, Deck with shuffle and deal"
```

### Task 3: Hand evaluator module

**Files:**
- Create: `backend/sekhmet/game_engine/hand_evaluator.py`
- Create: `backend/tests/test_hand_evaluator.py`

- [ ] **Step 1: Write failing tests for hand evaluation**

```python
# backend/tests/test_hand_evaluator.py
import pytest
from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.hand_evaluator import (
    HandRank, HandScore, evaluate_best_5_from_7, compare_hands
)

def _c(rank: Rank, suit: Suit) -> Card:
    return Card(rank, suit)

def test_royal_flush():
    cards = [
        _c(Rank.ACE, Suit.SPADES), _c(Rank.KING, Suit.SPADES),
        _c(Rank.QUEEN, Suit.SPADES), _c(Rank.JACK, Suit.SPADES),
        _c(Rank.TEN, Suit.SPADES), _c(Rank.TWO, Suit.HEARTS),
        _c(Rank.THREE, Suit.CLUBS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.ROYAL_FLUSH

def test_straight_flush():
    cards = [
        _c(Rank.NINE, Suit.HEARTS), _c(Rank.EIGHT, Suit.HEARTS),
        _c(Rank.SEVEN, Suit.HEARTS), _c(Rank.SIX, Suit.HEARTS),
        _c(Rank.FIVE, Suit.HEARTS), _c(Rank.TWO, Suit.CLUBS),
        _c(Rank.THREE, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.STRAIGHT_FLUSH
    assert score.kickers[0] == Rank.NINE

def test_four_of_a_kind():
    cards = [
        _c(Rank.KING, Suit.SPADES), _c(Rank.KING, Suit.HEARTS),
        _c(Rank.KING, Suit.DIAMONDS), _c(Rank.KING, Suit.CLUBS),
        _c(Rank.ACE, Suit.SPADES), _c(Rank.TWO, Suit.HEARTS),
        _c(Rank.THREE, Suit.CLUBS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.FOUR_OF_A_KIND
    assert score.kickers[0] == Rank.KING

def test_full_house():
    cards = [
        _c(Rank.ACE, Suit.SPADES), _c(Rank.ACE, Suit.HEARTS),
        _c(Rank.ACE, Suit.DIAMONDS), _c(Rank.KING, Suit.CLUBS),
        _c(Rank.KING, Suit.HEARTS), _c(Rank.TWO, Suit.CLUBS),
        _c(Rank.THREE, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.FULL_HOUSE

def test_flush():
    cards = [
        _c(Rank.ACE, Suit.CLUBS), _c(Rank.QUEEN, Suit.CLUBS),
        _c(Rank.TEN, Suit.CLUBS), _c(Rank.SEVEN, Suit.CLUBS),
        _c(Rank.THREE, Suit.CLUBS), _c(Rank.KING, Suit.HEARTS),
        _c(Rank.TWO, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.FLUSH

def test_straight():
    cards = [
        _c(Rank.NINE, Suit.SPADES), _c(Rank.EIGHT, Suit.HEARTS),
        _c(Rank.SEVEN, Suit.DIAMONDS), _c(Rank.SIX, Suit.CLUBS),
        _c(Rank.FIVE, Suit.HEARTS), _c(Rank.TWO, Suit.SPADES),
        _c(Rank.KING, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.STRAIGHT
    assert score.kickers[0] == Rank.NINE

def test_wheel_straight():
    """A-2-3-4-5 is a straight (wheel)"""
    cards = [
        _c(Rank.ACE, Suit.SPADES), _c(Rank.TWO, Suit.HEARTS),
        _c(Rank.THREE, Suit.DIAMONDS), _c(Rank.FOUR, Suit.CLUBS),
        _c(Rank.FIVE, Suit.HEARTS), _c(Rank.NINE, Suit.SPADES),
        _c(Rank.KING, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.STRAIGHT
    assert score.kickers[0] == Rank.FIVE  # Wheel, five-high

def test_three_of_a_kind():
    cards = [
        _c(Rank.QUEEN, Suit.SPADES), _c(Rank.QUEEN, Suit.HEARTS),
        _c(Rank.QUEEN, Suit.DIAMONDS), _c(Rank.ACE, Suit.CLUBS),
        _c(Rank.KING, Suit.HEARTS), _c(Rank.TWO, Suit.CLUBS),
        _c(Rank.THREE, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.THREE_OF_A_KIND

def test_two_pair():
    cards = [
        _c(Rank.ACE, Suit.SPADES), _c(Rank.ACE, Suit.HEARTS),
        _c(Rank.KING, Suit.DIAMONDS), _c(Rank.KING, Suit.CLUBS),
        _c(Rank.QUEEN, Suit.HEARTS), _c(Rank.TWO, Suit.CLUBS),
        _c(Rank.THREE, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.TWO_PAIR

def test_one_pair():
    cards = [
        _c(Rank.ACE, Suit.SPADES), _c(Rank.ACE, Suit.HEARTS),
        _c(Rank.KING, Suit.DIAMONDS), _c(Rank.QUEEN, Suit.CLUBS),
        _c(Rank.JACK, Suit.HEARTS), _c(Rank.TWO, Suit.CLUBS),
        _c(Rank.THREE, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.ONE_PAIR

def test_high_card():
    cards = [
        _c(Rank.ACE, Suit.SPADES), _c(Rank.KING, Suit.HEARTS),
        _c(Rank.QUEEN, Suit.DIAMONDS), _c(Rank.JACK, Suit.CLUBS),
        _c(Rank.NINE, Suit.HEARTS), _c(Rank.TWO, Suit.CLUBS),
        _c(Rank.THREE, Suit.DIAMONDS),
    ]
    score = evaluate_best_5_from_7(cards)
    assert score.hand_rank == HandRank.HIGH_CARD

def test_compare_hands():
    """Royal flush beats straight flush"""
    rf = HandScore(HandRank.ROYAL_FLUSH, [Rank.ACE])
    sf = HandScore(HandRank.STRAIGHT_FLUSH, [Rank.NINE])
    assert rf > sf
    assert sf < rf

def test_compare_same_rank_by_kicker():
    """Pair of aces with king kicker > pair of aces with queen kicker"""
    h1 = HandScore(HandRank.ONE_PAIR, [Rank.ACE, Rank.KING, Rank.QUEEN, Rank.TEN])
    h2 = HandScore(HandRank.ONE_PAIR, [Rank.ACE, Rank.QUEEN, Rank.JACK, Rank.NINE])
    assert h1 > h2

def test_equal_hands():
    h1 = HandScore(HandRank.FLUSH, [Rank.ACE, Rank.KING, Rank.QUEEN, Rank.TEN, Rank.FIVE])
    h2 = HandScore(HandRank.FLUSH, [Rank.ACE, Rank.KING, Rank.QUEEN, Rank.TEN, Rank.FIVE])
    assert h1 == h2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_hand_evaluator.py -v`
Expected: All FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement hand evaluator**

```python
# backend/sekhmet/game_engine/hand_evaluator.py
from enum import IntEnum
from dataclasses import dataclass, field
from itertools import combinations
from collections import Counter
from .deck import Card, Rank

class HandRank(IntEnum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9

@dataclass
class HandScore:
    hand_rank: HandRank
    kickers: list[Rank]  # Sorted from most significant

    def __lt__(self, other):
        if self.hand_rank != other.hand_rank:
            return self.hand_rank < other.hand_rank
        for a, b in zip(self.kickers, other.kickers):
            if a != b:
                return a < b
        return False

    def __eq__(self, other):
        if self.hand_rank != other.hand_rank:
            return False
        return self.kickers == other.kickers

    def __le__(self, other):
        return self < other or self == other

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other


def evaluate_best_5_from_7(cards: list[Card]) -> HandScore:
    """Find the best 5-card poker hand from 7 cards."""
    best: HandScore | None = None
    for combo in combinations(cards, 5):
        score = _evaluate_5(combo)
        if best is None or score > best:
            best = score
    if best is None:
        raise ValueError("Need at least 5 cards to evaluate")
    return best


def _evaluate_5(cards: tuple[Card, ...]) -> HandScore:
    ranks = [c.rank for c in cards]
    suits = [c.suit for c in cards]
    rank_counts = Counter(ranks)
    rank_values = sorted(ranks, reverse=True)
    is_flush = len(set(suits)) == 1
    is_straight, straight_high = _check_straight(rank_values)

    # Royal flush
    if is_flush and is_straight and straight_high == Rank.ACE:
        return HandScore(HandRank.ROYAL_FLUSH, [Rank.ACE])

    # Straight flush
    if is_flush and is_straight:
        return HandScore(HandRank.STRAIGHT_FLUSH, [straight_high])

    # Four of a kind
    if 4 in rank_counts.values():
        quad_rank = next(r for r, c in rank_counts.items() if c == 4)
        kicker = max(r for r in ranks if r != quad_rank)
        return HandScore(HandRank.FOUR_OF_A_KIND, [quad_rank, kicker])

    # Full house
    if 3 in rank_counts.values() and 2 in rank_counts.values():
        trip_rank = next(r for r, c in rank_counts.items() if c == 3)
        pair_rank = next(r for r, c in rank_counts.items() if c == 2)
        return HandScore(HandRank.FULL_HOUSE, [trip_rank, pair_rank])

    # Flush
    if is_flush:
        return HandScore(HandRank.FLUSH, rank_values[:5])

    # Straight
    if is_straight:
        return HandScore(HandRank.STRAIGHT, [straight_high])

    # Three of a kind
    if 3 in rank_counts.values():
        trip_rank = next(r for r, c in rank_counts.items() if c == 3)
        kickers = sorted([r for r in ranks if r != trip_rank], reverse=True)[:2]
        return HandScore(HandRank.THREE_OF_A_KIND, [trip_rank] + kickers)

    # Two pair
    pairs = sorted([r for r, c in rank_counts.items() if c == 2], reverse=True)
    if len(pairs) >= 2:
        kicker = max(r for r in ranks if r not in pairs[:2])
        return HandScore(HandRank.TWO_PAIR, pairs[:2] + [kicker])

    # One pair
    if len(pairs) == 1:
        kickers = sorted([r for r in ranks if r != pairs[0]], reverse=True)[:3]
        return HandScore(HandRank.ONE_PAIR, [pairs[0]] + kickers)

    # High card
    return HandScore(HandRank.HIGH_CARD, rank_values[:5])


def _check_straight(sorted_ranks: list[Rank]) -> tuple[bool, Rank | None]:
    """Check if 5 sorted ranks form a straight. Returns (is_straight, high_card)."""
    values = [r.value for r in sorted_ranks]
    # Normal straight
    if values == list(range(values[0], values[0] - 5, -1)):
        return True, sorted_ranks[0]
    # Wheel: A-5-4-3-2
    if values == [14, 5, 4, 3, 2]:
        return True, Rank.FIVE
    return False, None


def compare_hands(scores: list[HandScore]) -> list[int]:
    """Return indices sorted from best (first) to worst (last)."""
    indexed = list(enumerate(scores))
    indexed.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in indexed]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_hand_evaluator.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/sekhmet/game_engine/hand_evaluator.py backend/tests/test_hand_evaluator.py
git commit -m "feat: add hand evaluator — Trevor brute-force 7-choose-5 with full ranking"
```

---

## Phase 3: Game Engine — State Machine

### Task 4: GameState and PotManager

**Files:**
- Create: `backend/sekhmet/game_engine/game_state.py`
- Create: `backend/sekhmet/game_engine/pot_manager.py`
- Create: `backend/sekhmet/game_engine/rules/__init__.py`
- Create: `backend/sekhmet/game_engine/rules/blind_structure.py`
- Create: `backend/tests/test_game_state.py`
- Create: `backend/tests/test_pot_manager.py`

- [ ] **Step 1: Write failing tests for GameState and PotManager**

```python
# backend/tests/test_game_state.py
import pytest
from sekhmet.game_engine.game_state import GameState, GamePhase, Player, PlayerStatus
from sekhmet.game_engine.pot_manager import PotState, create_side_pots, award_pot
from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.hand_evaluator import HandScore, HandRank

def _c(rank, suit):
    return Card(rank, suit)

def test_game_state_creation():
    state = GameState.create_new(
        dealer_idx=0,
        small_blind=5,
        big_blind=10,
    )
    assert state.phase == GamePhase.WAITING
    assert state.community_cards == ()
    assert state.blinds == (5, 10)

def test_add_player():
    state = GameState.create_new(dealer_idx=0, small_blind=5, big_blind=10)
    state = state.add_player(seat_idx=0, name="Hero", stack=1000, is_human=True)
    assert len(state.players) == 1
    assert state.players[0].name == "Hero"
    assert state.players[0].stack == 1000

def test_game_state_is_immutable():
    state = GameState.create_new(dealer_idx=0, small_blind=5, big_blind=10)
    with pytest.raises(Exception):
        state.phase = GamePhase.FLOP

def test_pot_creation():
    pot = PotState()
    assert pot.main_pot == 0
    assert pot.side_pots == []

def test_add_to_main_pot():
    pot = PotState()
    pot = pot.add_bet(player_idx=0, amount=10)
    pot = pot.add_bet(player_idx=1, amount=10)
    assert pot.main_pot == 20

# backend/tests/test_pot_manager.py
def test_create_side_pots_all_in_scenario():
    """Player A all-in 50, B and C bet 100. Side pot for B+C."""
    player_bets = {0: 50, 1: 100, 2: 100}
    # All players are active (not folded)
    active_players = {0, 1, 2}
    side_pots = create_side_pots(player_bets, active_players)
    assert len(side_pots) == 2
    # Main pot: 50 from each = 150
    assert side_pots[0].amount == 150
    assert side_pots[0].eligible_players == {0, 1, 2}
    # Side pot: remaining 50 from B and C = 100
    assert side_pots[1].amount == 100
    assert side_pots[1].eligible_players == {1, 2}

def test_award_pot_single_winner():
    """If only one player remains, they get everything."""
    side_pots = [PotState.SidePot(amount=300, eligible_players={1, 2})]
    # Player 1 folded (not in eligible), player 2 wins
    remaining = {2}
    hand_scores = {2: HandScore(HandRank.ONE_PAIR, [Rank.ACE])}
    payouts = award_pot(side_pots, remaining, hand_scores)
    assert payouts[2] == 300

def test_award_pot_split():
    """Two players tie — split the pot."""
    side_pots = [PotState.SidePot(amount=200, eligible_players={0, 1})]
    remaining = {0, 1}
    h1 = HandScore(HandRank.ONE_PAIR, [Rank.ACE, Rank.KING])
    h2 = HandScore(HandRank.ONE_PAIR, [Rank.ACE, Rank.KING])
    hand_scores = {0: h1, 1: h2}
    payouts = award_pot(side_pots, remaining, hand_scores)
    assert payouts[0] == 100
    assert payouts[1] == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_game_state.py tests/test_pot_manager.py -v`
Expected: All FAIL

- [ ] **Step 3: Implement GameState**

```python
# backend/sekhmet/game_engine/game_state.py
import dataclasses
from enum import Enum
from dataclasses import dataclass, field
from .deck import Card
from .pot_manager import PotState

class GamePhase(Enum):
    WAITING = "waiting"
    DEALING = "dealing"
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"

class PlayerStatus(Enum):
    ACTIVE = "active"        # Still in the hand
    FOLDED = "folded"
    ALL_IN = "all_in"
    SITTING_OUT = "sitting_out"

@dataclass(frozen=True)
class Player:
    seat_idx: int
    name: str
    stack: int
    hole_cards: tuple[Card, ...] = ()
    status: PlayerStatus = PlayerStatus.SITTING_OUT
    current_bet: int = 0      # Amount bet in current round
    total_bet: int = 0         # Total bet this hand
    is_human: bool = False

    def _replace(self, **kwargs):
        return dataclasses.replace(self, **kwargs)

@dataclass(frozen=True)
class GameState:
    phase: GamePhase
    players: tuple[Player, ...]
    community_cards: tuple[Card, ...]
    pot: PotState
    current_player_idx: int
    dealer_idx: int
    last_aggressor_idx: int | None
    current_bet: int           # Current bet to match (big blind equivalent)
    min_raise: int             # Minimum raise increment
    round_history: tuple['Action', ...]
    blinds: tuple[int, int]
    hand_number: int = 1

    @classmethod
    def create_new(cls, dealer_idx: int, small_blind: int, big_blind: int) -> 'GameState':
        return cls(
            phase=GamePhase.WAITING,
            players=(),
            community_cards=(),
            pot=PotState(),
            current_player_idx=0,
            dealer_idx=dealer_idx,
            last_aggressor_idx=None,
            current_bet=big_blind,
            min_raise=big_blind,
            round_history=(),
            blinds=(small_blind, big_blind),
        )

    def add_player(self, seat_idx: int, name: str, stack: int, is_human: bool = False) -> 'GameState':
        player = Player(
            seat_idx=seat_idx,
            name=name,
            stack=stack,
            is_human=is_human,
            status=PlayerStatus.SITTING_OUT,
        )
        new_players = list(self.players)
        new_players.append(player)
        return self._replace(players=tuple(new_players))

    def _replace(self, **kwargs):
        return dataclasses.replace(self, **kwargs)
```

- [ ] **Step 4: Implement PotManager**

```python
# backend/sekhmet/game_engine/pot_manager.py
import dataclasses
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass(frozen=True)
class PotState:
    main_pot: int = 0
    side_pots: tuple['PotState.SidePot', ...] = ()

    @dataclass(frozen=True)
    class SidePot:
        amount: int
        eligible_players: frozenset[int]

    def add_bet(self, player_idx: int, amount: int) -> 'PotState':
        return dataclasses.replace(self, main_pot=self.main_pot + amount)


def create_side_pots(
    player_bets: dict[int, int],
    active_players: set[int]
) -> list[PotState.SidePot]:
    """
    Given each player's total bet this hand, create main and side pots
    for all-in scenarios. Returns pots sorted from main to last side pot.
    """
    if not player_bets:
        return []

    # Sort all-in amounts ascending
    all_in_amounts = sorted(set(player_bets.values()))
    side_pots = []
    prev_amount = 0

    for level in all_in_amounts:
        pot_amount = 0
        eligible = set()
        for pid, total_bet in player_bets.items():
            contribution = min(total_bet, level) - min(prev_amount, level)
            contrib_at_this_level = total_bet >= level
            if contribution > 0:
                pot_amount += contribution
            if pid in active_players and total_bet >= level:
                eligible.add(pid)

        if pot_amount > 0:
            side_pots.append(PotState.SidePot(
                amount=pot_amount,
                eligible_players=frozenset(eligible),
            ))

        prev_amount = level

    return side_pots


def award_pot(
    side_pots: list[PotState.SidePot],
    remaining_players: set[int],
    hand_scores: dict[int, 'HandScore'],
) -> dict[int, int]:
    """
    Award each side pot to the best hand among eligible remaining players.
    Returns dict of player_idx → chips_won.
    """
    payouts = defaultdict(int)
    from .hand_evaluator import compare_hands

    for sp in side_pots:
        eligible = sp.eligible_players & remaining_players
        if not eligible:
            continue

        # Rank eligible players by hand score
        eligible_scores = {pid: hand_scores[pid] for pid in eligible}
        ranked = compare_hands(list(eligible_scores.values()))
        # ranked is indices into the list; map back to player indices
        idx_to_pid = list(eligible)
        best_pid = idx_to_pid[ranked[0]]

        # Check for ties
        best_score = hand_scores[best_pid]
        tied = [pid for pid in eligible if hand_scores[pid] == best_score]

        share = sp.amount // len(tied)
        remainder = sp.amount - share * len(tied)
        for pid in tied:
            payouts[pid] += share
        # Give remainder to earliest tie (closest to dealer, arbitrary but deterministic)
        if remainder > 0:
            payouts[tied[0]] += remainder

    return dict(payouts)
```

- [ ] **Step 5: Implement blind structure**

```python
# backend/sekhmet/game_engine/rules/__init__.py
# backend/sekhmet/game_engine/rules/blind_structure.py
from dataclasses import dataclass

@dataclass
class BlindLevel:
    level: int
    small_blind: int
    big_blind: int
    ante: int = 0
    duration_minutes: int = 10

# Standard MTT blind structure (example)
STANDARD_MTT_BLINDS = [
    BlindLevel(1, 5, 10, 0, 10),
    BlindLevel(2, 10, 20, 0, 10),
    BlindLevel(3, 15, 30, 0, 10),
    BlindLevel(4, 25, 50, 0, 10),
    BlindLevel(5, 50, 100, 0, 10),
    BlindLevel(6, 75, 150, 0, 10),
    BlindLevel(7, 100, 200, 25, 10),
    BlindLevel(8, 150, 300, 25, 10),
    BlindLevel(9, 200, 400, 50, 10),
    BlindLevel(10, 300, 600, 75, 10),
    BlindLevel(11, 400, 800, 100, 10),
    BlindLevel(12, 500, 1000, 100, 10),
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_game_state.py tests/test_pot_manager.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/sekhmet/game_engine/game_state.py backend/sekhmet/game_engine/pot_manager.py backend/sekhmet/game_engine/rules/ backend/tests/test_game_state.py backend/tests/test_pot_manager.py
git commit -m "feat: add GameState, PotManager, and blind structure"
```

### Task 5: Action model and ActionProcessor

**Files:**
- Create: `backend/sekhmet/game_engine/action_processor.py`
- Create: `backend/tests/test_action_processor.py`

- [ ] **Step 1: Write failing tests for ActionProcessor**

```python
# backend/tests/test_action_processor.py
import pytest
from sekhmet.game_engine.game_state import GameState, GamePhase, Player, PlayerStatus
from sekhmet.game_engine.action_processor import (
    Action, ActionType, ActionProcessor,
    InvalidActionError, NotYourTurnError, IllegalAmountError
)
from sekhmet.game_engine.pot_manager import PotState

def _make_state(phase=GamePhase.PREFLOP, players=None, current_bet=10, current_player=0,
                dealer=0, blinds=(5, 10)):
    if players is None:
        players = (
            Player(seat_idx=0, name="H", stack=1000, hole_cards=(), status=PlayerStatus.ACTIVE, is_human=True, current_bet=0, total_bet=0),
            Player(seat_idx=1, name="A", stack=1000, hole_cards=(), status=PlayerStatus.ACTIVE, is_human=False, current_bet=10, total_bet=10),
        )
    return GameState(
        phase=phase, players=players, community_cards=(), pot=PotState(main_pot=15),
        current_player_idx=current_player, dealer_idx=dealer,
        last_aggressor_idx=None, current_bet=current_bet, min_raise=10,
        round_history=(), blinds=blinds, hand_number=1,
    )

def test_fold_ends_player_participation():
    state = _make_state(current_player=0)
    action = Action(ActionType.FOLD, player_idx=0, amount=0, phase=GamePhase.PREFLOP)
    new_state = ActionProcessor().execute(state, action)
    assert new_state.players[0].status == PlayerStatus.FOLDED

def test_check_valid_when_no_bet_to_match():
    """Check is valid when current_bet equals player's current round bet."""
    state = _make_state(current_bet=0, current_player=0)
    state = state._replace(players=tuple(
        state.players[0]._replace(current_bet=0) if state.players[0].seat_idx == 0 else p
        for p in state.players
    ))
    action = Action(ActionType.CHECK, player_idx=0, amount=0, phase=GamePhase.PREFLOP)
    new_state = ActionProcessor().execute(state, action)
    assert new_state is not None  # Not raising = pass

def test_check_invalid_when_bet_to_match():
    """Check is NOT valid when there's a bet to match."""
    state = _make_state(current_bet=10)
    action = Action(ActionType.CHECK, player_idx=0, amount=0, phase=GamePhase.PREFLOP)
    with pytest.raises(InvalidActionError):
        ActionProcessor().execute(state, action)

def test_call_matches_current_bet():
    state = _make_state(current_bet=10, current_player=0)
    action = Action(ActionType.CALL, player_idx=0, amount=10, phase=GamePhase.PREFLOP)
    new_state = ActionProcessor().execute(state, action)
    assert new_state.players[0].current_bet == 10
    assert new_state.players[0].stack == 990

def test_raise_increases_current_bet():
    state = _make_state(current_bet=10, current_player=0)
    action = Action(ActionType.RAISE, player_idx=0, amount=30, phase=GamePhase.PREFLOP)
    new_state = ActionProcessor().execute(state, action)
    assert new_state.current_bet == 30
    assert new_state.last_aggressor_idx == 0

def test_raise_below_minimum_raises_error():
    state = _make_state(current_bet=10, current_player=0)
    # Min raise is 10, so total of 20 required
    action = Action(ActionType.RAISE, player_idx=0, amount=15, phase=GamePhase.PREFLOP)
    with pytest.raises(IllegalAmountError):
        ActionProcessor().execute(state, action)

def test_not_your_turn_raises_error():
    state = _make_state(current_player=0)
    action = Action(ActionType.CALL, player_idx=1, amount=10, phase=GamePhase.PREFLOP)
    with pytest.raises(NotYourTurnError):
        ActionProcessor().execute(state, action)

def test_all_in_sets_stack_to_zero():
    state = _make_state(current_player=0)
    state = state._replace(players=tuple(
        state.players[0]._replace(stack=500) if state.players[0].seat_idx == 0 else p
        for p in state.players
    ))
    action = Action(ActionType.ALL_IN, player_idx=0, amount=500, phase=GamePhase.PREFLOP)
    new_state = ActionProcessor().execute(state, action)
    assert new_state.players[0].stack == 0
    assert new_state.players[0].status == PlayerStatus.ALL_IN

def test_advance_phase_after_all_acted():
    """After all players have acted and bets are equal, advance to next phase."""
    state = _make_state(phase=GamePhase.PREFLOP, current_player=0, current_bet=10)
    # Player 0 calls the big blind
    action = Action(ActionType.CALL, player_idx=0, amount=10, phase=GamePhase.PREFLOP)
    new_state = ActionProcessor().execute(state, action)
    # Both players have acted and bets are equal → advance to FLOP
    assert new_state.phase == GamePhase.FLOP
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_action_processor.py -v`
Expected: All FAIL

- [ ] **Step 3: Implement ActionProcessor**

```python
# backend/sekhmet/game_engine/action_processor.py
from enum import Enum
from dataclasses import dataclass, replace
from .game_state import GameState, GamePhase, Player, PlayerStatus
from .pot_manager import PotState

class ActionType(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"

class GameError(Exception):
    """Base exception for game logic errors."""
    pass

class InvalidActionError(GameError):
    pass

class IllegalAmountError(GameError):
    pass

class NotYourTurnError(GameError):
    pass

class PhaseError(GameError):
    pass

@dataclass(frozen=True)
class Action:
    type: ActionType
    player_idx: int
    amount: int
    phase: GamePhase


class ActionProcessor:
    """Validates and executes player actions, producing new GameState."""

    def execute(self, state: GameState, action: Action) -> GameState:
        if action.player_idx != state.current_player_idx:
            raise NotYourTurnError(
                f"Player {action.player_idx} tried to act, but it's player {state.current_player_idx}'s turn"
            )

        player = state.players[action.player_idx]
        if player.status not in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN):
            raise InvalidActionError(f"Player {action.player_idx} is {player.status}")

        match action.type:
            case ActionType.FOLD:
                return self._handle_fold(state, action)
            case ActionType.CHECK:
                return self._handle_check(state, action)
            case ActionType.CALL:
                return self._handle_call(state, action)
            case ActionType.BET | ActionType.RAISE:
                return self._handle_raise(state, action)
            case ActionType.ALL_IN:
                return self._handle_all_in(state, action)
            case _:
                raise InvalidActionError(f"Unknown action type: {action.type}")

    def _handle_fold(self, state: GameState, action: Action) -> GameState:
        player = state.players[action.player_idx]
        new_player = replace(player, status=PlayerStatus.FOLDED)
        new_players = self._update_player(state.players, new_player)
        new_state = replace(state, players=new_players,
                            round_history=state.round_history + (action,))
        return self._advance_if_needed(new_state)

    def _handle_check(self, state: GameState, action: Action) -> GameState:
        player = state.players[action.player_idx]
        if player.current_bet < state.current_bet:
            raise InvalidActionError("Cannot check — there is a bet to match")
        new_state = replace(state, round_history=state.round_history + (action,))
        return self._advance_turn(new_state)

    def _handle_call(self, state: GameState, action: Action) -> GameState:
        player = state.players[action.player_idx]
        call_amount = min(state.current_bet - player.current_bet, player.stack)
        new_player = replace(player,
                             stack=player.stack - call_amount,
                             current_bet=player.current_bet + call_amount,
                             total_bet=player.total_bet + call_amount,
                             status=PlayerStatus.ALL_IN if player.stack - call_amount == 0 else PlayerStatus.ACTIVE)
        new_players = self._update_player(state.players, new_player)
        new_pot = state.pot.add_bet(action.player_idx, call_amount)
        new_state = replace(state, players=new_players, pot=new_pot,
                            round_history=state.round_history + (action,))
        return self._advance_turn(new_state)

    def _handle_raise(self, state: GameState, action: Action) -> GameState:
        player = state.players[action.player_idx]
        total_raise_to = action.amount
        to_call = state.current_bet - player.current_bet
        raise_amount = total_raise_to - to_call - player.current_bet

        if total_raise_to < state.current_bet + state.min_raise and player.stack > total_raise_to:
            raise IllegalAmountError(
                f"Raise to {total_raise_to} is below minimum raise to {state.current_bet + state.min_raise}"
            )
        if total_raise_to > player.stack:
            raise IllegalAmountError(f"Raise to {total_raise_to} exceeds stack {player.stack}")

        is_all_in = (player.stack == total_raise_to)
        total_bet_increment = total_raise_to - player.current_bet
        new_player = replace(player,
                             stack=player.stack - total_bet_increment,
                             current_bet=total_raise_to,
                             total_bet=player.total_bet + total_bet_increment,
                             status=PlayerStatus.ALL_IN if is_all_in else PlayerStatus.ACTIVE)
        new_players = self._update_player(state.players, new_player)
        new_pot = state.pot.add_bet(action.player_idx, total_bet_increment)
        new_current_bet = total_raise_to
        new_state = replace(state,
                            players=new_players, pot=new_pot,
                            current_bet=new_current_bet,
                            last_aggressor_idx=action.player_idx,
                            round_history=state.round_history + (action,))
        return self._advance_turn(new_state)

    def _handle_all_in(self, state: GameState, action: Action) -> GameState:
        player = state.players[action.player_idx]
        all_in_amount = player.stack + player.current_bet
        raise_action = Action(ActionType.RAISE, player_idx=action.player_idx,
                              amount=all_in_amount, phase=action.phase)
        # If all-in amount is less than min raise, it's still allowed (only a call in terms of betting)
        if all_in_amount < state.current_bet + state.min_raise and all_in_amount > state.current_bet:
            # All-in for less than min raise — treat as call for betting round purposes
            return self._handle_call(state, Action(ActionType.CALL,
                                    player_idx=action.player_idx,
                                    amount=all_in_amount, phase=action.phase))
        if all_in_amount <= state.current_bet:
            return self._handle_call(state, Action(ActionType.CALL,
                                    player_idx=action.player_idx,
                                    amount=state.current_bet, phase=action.phase))
        return self._handle_raise(state, raise_action)

    def _advance_turn(self, state: GameState) -> GameState:
        """Move to the next active player."""
        n = len(state.players)
        next_idx = (state.current_player_idx + 1) % n
        attempts = 0
        while attempts < n:
            p = state.players[next_idx]
            if p.status in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN):
                return replace(state, current_player_idx=next_idx)
            next_idx = (next_idx + 1) % n
            attempts += 1
        # No active players — shouldn't happen normally
        return state

    def _advance_if_needed(self, state: GameState) -> GameState:
        """After fold, check if hand is over (only one player left)."""
        active = [p for p in state.players if p.status == PlayerStatus.ACTIVE]
        all_in = [p for p in state.players if p.status == PlayerStatus.ALL_IN]
        if len(active) + len(all_in) <= 1:
            return replace(state, phase=GamePhase.SHOWDOWN)
        # Check if all active have acted and bets are equal
        if self._all_acted_and_equal(state):
            return self._advance_phase(state)
        return self._advance_turn(state)

    def _all_acted_and_equal(self, state: GameState) -> bool:
        active_players = [p for p in state.players if p.status == PlayerStatus.ACTIVE]
        if not active_players:
            return True
        # All active players must have current_bet == state.current_bet
        # And they've all taken at least one action this round
        return all(p.current_bet == state.current_bet for p in active_players)

    def _advance_phase(self, state: GameState) -> GameState:
        """Move to next phase and reset round betting."""
        phase_order = [GamePhase.PREFLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER]
        try:
            idx = phase_order.index(state.phase)
            next_phase = phase_order[idx + 1]
        except (ValueError, IndexError):
            next_phase = GamePhase.SHOWDOWN

        # Reset per-round bets, find first active player after dealer
        new_players = tuple(
            replace(p, current_bet=0) if p.status == PlayerStatus.ACTIVE else p
            for p in state.players
        )
        first_to_act = self._find_first_to_act(state, next_phase)
        return replace(state, phase=next_phase, players=new_players,
                       current_player_idx=first_to_act, current_bet=0,
                       last_aggressor_idx=None)

    def _find_first_to_act(self, state: GameState, phase: GamePhase) -> int:
        """Find the first player to act in the new phase."""
        n = len(state.players)
        if phase == GamePhase.PREFLOP:
            # UTG = dealer + 3 (in full ring), or dealer + 1 in HU
            start = (state.dealer_idx + 3) % n if n > 2 else (state.dealer_idx + 1) % n
        else:
            # Post-flop: first active player after dealer
            start = (state.dealer_idx + 1) % n

        for i in range(n):
            idx = (start + i) % n
            p = state.players[idx]
            if p.status in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN):
                return idx
        return start

    def _update_player(self, players: tuple[Player, ...], new_player: Player) -> tuple[Player, ...]:
        return tuple(
            new_player if p.seat_idx == new_player.seat_idx else p
            for p in players
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_action_processor.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/sekhmet/game_engine/action_processor.py backend/tests/test_action_processor.py
git commit -m "feat: add ActionProcessor — validate and execute all poker actions"
```

---

At this point the game engine core is functional. Continue the plan in Phase 4 for the API and WebSocket layer, then AI, then frontend. The full plan continues but this document covers the critical path through a playable single-AI game.

## Phase 4: API + WebSocket Layer

### Task 6: FastAPI app and WebSocket handler

**Files:**
- Create: `backend/sekhmet/api/__init__.py`
- Create: `backend/sekhmet/api/game.py`
- Create: `backend/sekhmet/api/ws.py`
- Create: `backend/sekhmet/main.py`
- Create: `backend/tests/test_ws.py`

- [ ] **Step 1: Create FastAPI app entrypoint**

```python
# backend/sekhmet/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.game import router as game_router
from .api.ws import router as ws_router

app = FastAPI(title="Sekhmet", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(game_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
```

- [ ] **Step 2: Create game REST endpoints (stub)**

```python
# backend/sekhmet/api/__init__.py
# backend/sekhmet/api/game.py
from fastapi import APIRouter

router = APIRouter(tags=["game"])

@router.get("/tables")
async def list_tables():
    """List available tables."""
    return {"tables": []}

@router.post("/tables")
async def create_table(blind_small: int = 5, blind_big: int = 10, max_players: int = 6):
    """Create a new table."""
    return {"table_id": "TBD", "status": "created"}
```

- [ ] **Step 3: Create WebSocket handler with in-memory table manager**

```python
# backend/sekhmet/api/ws.py
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..game_engine.game_state import GameState, GamePhase
from ..game_engine.action_processor import ActionProcessor, Action, ActionType, GameError
from ..game_engine.deck import Deck

router = APIRouter()

# In-memory table storage (replace with DB later)
class TableManager:
    def __init__(self):
        self.tables: dict[str, GameState] = {}
        self.connections: dict[str, dict[int, WebSocket]] = {}
        self._next_id = 1

    def create_table(self, small_blind: int, big_blind: int) -> str:
        tid = f"table_{self._next_id}"
        self._next_id += 1
        self.tables[tid] = GameState.create_new(dealer_idx=0, small_blind=small_blind, big_blind=big_blind)
        self.connections[tid] = {}
        return tid

table_manager = TableManager()

@router.websocket("/table/{table_id}")
async def table_ws(websocket: WebSocket, table_id: str):
    await websocket.accept()

    if table_id not in table_manager.tables:
        await websocket.send_json({"type": "error", "message": "Table not found"})
        return

    # Assign a player slot
    state = table_manager.tables[table_id]
    seat = _next_free_seat(state)
    state = state.add_player(seat_idx=seat, name="Hero", stack=1000, is_human=True)
    table_manager.tables[table_id] = state
    table_manager.connections[table_id][seat] = websocket

    await websocket.send_json({"type": "welcome", "seat_idx": seat, "table_id": table_id})

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            await _handle_message(table_id, seat, msg, websocket)
    except WebSocketDisconnect:
        table_manager.connections[table_id].pop(seat, None)

def _next_free_seat(state: GameState) -> int:
    taken = {p.seat_idx for p in state.players}
    for i in range(9):
        if i not in taken:
            return i
    return 0

async def _handle_message(table_id: str, seat: int, msg: dict, ws: WebSocket):
    msg_type = msg.get("type")

    if msg_type == "start_hand":
        await _start_hand(table_id)
    elif msg_type == "player_action":
        await _process_action(table_id, seat, msg)
    elif msg_type == "sit_down":
        # Already handled on connect
        pass

async def _start_hand(table_id: str):
    state = table_manager.tables[table_id]
    conns = table_manager.connections[table_id]

    # Deal cards
    deck = Deck()
    deck.shuffle()
    state = state._replace(phase=GamePhase.DEALING)

    new_players = []
    for p in state.players:
        cards = tuple(deck.deal(2))
        new_players.append(p._replace(hole_cards=cards, status=PlayerStatus.ACTIVE if p.is_human or True else PlayerStatus.SITTING_OUT))
    state = state._replace(players=tuple(new_players))

    # Post blinds
    n = len(state.players)
    sb_idx = (state.dealer_idx + 1) % n
    bb_idx = (state.dealer_idx + 2) % n if n > 2 else (state.dealer_idx + 1) % n

    sb_player = new_players[sb_idx]
    sb_amount = min(state.blinds[0], sb_player.stack)
    sb_player = sb_player._replace(
        stack=sb_player.stack - sb_amount,
        current_bet=sb_amount, total_bet=sb_amount)
    new_players[sb_idx] = sb_player
    state = state._replace(pot=state.pot.add_bet(sb_idx, sb_amount))

    bb_player = new_players[bb_idx]
    bb_amount = min(state.blinds[1], bb_player.stack)
    bb_player = bb_player._replace(
        stack=bb_player.stack - bb_amount,
        current_bet=bb_amount, total_bet=bb_amount)
    new_players[bb_idx] = bb_player
    state = state._replace(pot=state.pot.add_bet(bb_idx, bb_amount),
                           current_bet=state.blinds[1])

    state = state._replace(players=tuple(new_players),
                           phase=GamePhase.PREFLOP,
                           current_player_idx=(state.dealer_idx + 3) % n if n > 2 else (state.dealer_idx + 1) % n)
    table_manager.tables[table_id] = state

    # Send private hole cards to each player
    for p in state.players:
        if p.seat_idx in conns and p.is_human:
            await conns[p.seat_idx].send_json({
                "type": "hole_cards",
                "cards": [str(c) for c in p.hole_cards],
            })

    # Broadcast game state (without private info)
    await _broadcast_state(table_id)

async def _broadcast_state(table_id: str):
    state = table_manager.tables[table_id]
    conns = table_manager.connections[table_id]

    public_state = {
        "type": "game_state_update",
        "phase": state.phase.value,
        "community_cards": [str(c) for c in state.community_cards],
        "pot": state.pot.main_pot,
        "current_bet": state.current_bet,
        "current_player_idx": state.current_player_idx,
        "players": [
            {
                "seat_idx": p.seat_idx,
                "name": p.name,
                "stack": p.stack,
                "status": p.status.value,
                "current_bet": p.current_bet,
                "is_human": p.is_human,
            }
            for p in state.players
        ],
    }

    for ws in conns.values():
        await ws.send_json(public_state)

    # Tell current player it's their turn
    current_player = state.players[state.current_player_idx]
    if current_player.seat_idx in conns:
        await conns[current_player.seat_idx].send_json({
            "type": "your_turn",
            "available_actions": _get_available_actions(state, current_player),
        })

async def _process_action(table_id: str, seat: int, msg: dict):
    state = table_manager.tables[table_id]
    processor = ActionProcessor()

    action_type = ActionType(msg["action"])
    amount = msg.get("amount", 0)

    action = Action(type=action_type, player_idx=seat, amount=amount, phase=state.phase)

    try:
        new_state = processor.execute(state, action)
        table_manager.tables[table_id] = new_state
        await _broadcast_state(table_id)
    except GameError as e:
        conns = table_manager.connections[table_id]
        if seat in conns:
            await conns[seat].send_json({"type": "error", "message": str(e)})

def _get_available_actions(state: GameState, player: 'Player') -> list[dict]:
    actions = []
    can_check = player.current_bet == state.current_bet
    to_call = state.current_bet - player.current_bet

    actions.append({"action": "fold", "amount": 0})
    if can_check:
        actions.append({"action": "check", "amount": 0})
    else:
        actions.append({"action": "call", "amount": min(to_call, player.stack)})

    if player.stack > to_call + state.min_raise:
        actions.append({"action": "raise", "min": state.current_bet + state.min_raise, "max": player.stack})
    actions.append({"action": "all_in", "amount": player.stack})

    return actions

# Import Player at module level
from ..game_engine.game_state import Player, PlayerStatus
```

- [ ] **Step 4: Create integration test for WebSocket**

```python
# backend/tests/test_ws.py
import pytest
from httpx import AsyncClient, ASGITransport
from sekhmet.main import app

@pytest.mark.asyncio
async def test_list_tables():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/tables")
        assert resp.status_code == 200
        assert "tables" in resp.json()
```

- [ ] **Step 5: Run tests to verify**

Run: `cd backend && source .venv/bin/activate && pip install httpx && python -m pytest tests/test_ws.py -v`
Expected: 1 test PASS

- [ ] **Step 6: Verify app starts**

Run: `cd backend && source .venv/bin/activate && timeout 3 python -m uvicorn sekhmet.main:app --host 0.0.0.0 --port 8000 || true`
Expected: "Uvicorn running on http://0.0.0.0:8000"

- [ ] **Step 7: Commit**

```bash
git add backend/sekhmet/api/ backend/sekhmet/main.py backend/tests/test_ws.py
git commit -m "feat: add FastAPI app, REST endpoints, and WebSocket game handler"
```

---

## Phase 5: AI Engine — RuleBot

### Task 7: BaseBot interface and RuleBot implementation

**Files:**
- Create: `backend/sekhmet/ai_engine/__init__.py`
- Create: `backend/sekhmet/ai_engine/base_bot.py`
- Create: `backend/sekhmet/ai_engine/rule_bot.py`
- Create: `backend/sekhmet/ai_engine/bot_registry.py`
- Create: `backend/tests/test_rule_bot.py`

- [ ] **Step 1: Write BaseBot interface**

```python
# backend/sekhmet/ai_engine/__init__.py
"""AI engine — bot implementations for automated opponents."""

# backend/sekhmet/ai_engine/base_bot.py
from abc import ABC, abstractmethod
from ..game_engine.game_state import GameState
from ..game_engine.action_processor import Action

class BaseBot(ABC):
    @abstractmethod
    def decide(self, state: GameState, player_idx: int) -> Action:
        """Given game state, return the bot's action."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def style_description(self) -> str:
        ...
```

- [ ] **Step 2: Write BotRegistry**

```python
# backend/sekhmet/ai_engine/bot_registry.py
from dataclasses import dataclass
from .base_bot import BaseBot

@dataclass
class BotPersonality:
    vpip: float = 0.25
    pfr: float = 0.18
    aggression: float = 0.5
    bluff_freq: float = 0.15
    hero_call_freq: float = 0.3

class BotRegistry:
    _bots: dict[str, type[BaseBot]] = {}

    @classmethod
    def register(cls, name: str, bot_cls: type[BaseBot]):
        cls._bots[name] = bot_cls

    @classmethod
    def create(cls, name: str, personality: BotPersonality | None = None, **kwargs) -> BaseBot:
        bot_cls = cls._bots.get(name)
        if bot_cls is None:
            raise KeyError(f"Unknown bot: {name}. Available: {list(cls._bots.keys())}")
        return bot_cls(personality=personality or BotPersonality(), **kwargs)

    @classmethod
    def list_bots(cls) -> list[str]:
        return list(cls._bots.keys())
```

- [ ] **Step 3: Implement RuleBot**

```python
# backend/sekhmet/ai_engine/rule_bot.py
import random
from ..game_engine.game_state import GameState, GamePhase, Player, PlayerStatus
from ..game_engine.action_processor import Action, ActionType
from ..game_engine.hand_evaluator import evaluate_best_5_from_7, HandRank
from .base_bot import BaseBot
from .bot_registry import BotPersonality, BotRegistry

# Preflop hand strength tiers (simplified)
PREFLOP_TIERS = {
    "tier1": {  # Premium: AA, KK, QQ, AKs
        (14, 14), (13, 13), (12, 12),
        (14, 13),  # AKs / AKo treated the same for simplicity
    },
    "tier2": {  # Strong: JJ, TT, AQs, AQo, AJs, KQs
        (11, 11), (10, 10), (14, 12), (14, 11), (13, 12),
    },
    "tier3": {  # Playable: 99-77, ATs, AJo, KJs, QJs, JTs
        (9, 9), (8, 8), (7, 7), (14, 10), (13, 11), (12, 11), (11, 10),
    },
}

def _hand_tier(card1, card2) -> int:
    """Classify starting hand into tier 1-5 (1=best)."""
    r1, r2 = max(card1.rank.value, card2.rank.value), min(card1.rank.value, card2.rank.value)
    pair = (r1, r2) if r1 == r2 else (r1, r2)
    suited = card1.suit == card2.suit

    if pair in PREFLOP_TIERS["tier1"]:
        return 1
    if pair in PREFLOP_TIERS["tier2"]:
        return 2
    if pair in PREFLOP_TIERS["tier3"]:
        return 3
    if suited:
        return 4
    return 5


class RuleBot(BaseBot):
    """Decision-tree based bot. Difficulty controlled via personality params."""

    def __init__(self, personality: BotPersonality, difficulty: str = "medium"):
        self.personality = personality
        self.difficulty = difficulty  # easy, medium, hard

    @property
    def name(self) -> str:
        return f"RuleBot({self.difficulty})"

    @property
    def style_description(self) -> str:
        return f"VPIP:{self.personality.vpip:.0%} PFR:{self.personality.pfr:.0%} AGG:{self.personality.aggression:.0%}"

    def decide(self, state: GameState, player_idx: int) -> Action:
        player = state.players[player_idx]
        phase = state.phase

        if phase == GamePhase.PREFLOP:
            return self._decide_preflop(state, player)
        else:
            return self._decide_postflop(state, player)

    def _decide_preflop(self, state: GameState, player: 'Player') -> Action:
        if not player.hole_cards or len(player.hole_cards) < 2:
            return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)

        tier = _hand_tier(player.hole_cards[0], player.hole_cards[1])
        to_call = state.current_bet - player.current_bet

        # Position adjustment: later position → more aggressive
        n = len(state.players)
        pos_from_btn = (player.seat_idx - state.dealer_idx) % n
        is_late = pos_from_btn <= 2

        if state.last_aggressor_idx is None:
            # No raise yet — open or limp
            if tier <= 2:
                return self._make_raise(state, player, 3 * state.blinds[1])
            elif tier == 3:
                if is_late and random.random() < self.personality.pfr:
                    return self._make_raise(state, player, 2.5 * state.blinds[1])
                return Action(ActionType.CALL, player.seat_idx, to_call, state.phase)
            elif tier == 4:
                if is_late and random.random() < self.personality.vpip * 0.5:
                    return Action(ActionType.CALL, player.seat_idx, to_call, state.phase)
                return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)
            else:
                # Tier 5: mostly fold
                if random.random() < 0.05 * self.difficulty_factor():
                    return Action(ActionType.CALL, player.seat_idx, to_call, state.phase)
                return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)
        else:
            # Facing a raise
            if tier == 1:
                return self._make_raise(state, player, 3 * state.current_bet)
            elif tier <= 3:
                if random.random() < 0.6:
                    return Action(ActionType.CALL, player.seat_idx, to_call, state.phase)
                return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)
            else:
                return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)

    def _decide_postflop(self, state: GameState, player: 'Player') -> Action:
        if not player.hole_cards:
            return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)

        all_cards = list(player.hole_cards) + list(state.community_cards)
        if len(all_cards) < 5:
            # Not enough community cards to evaluate yet — check/call
            to_call = state.current_bet - player.current_bet
            if to_call <= 0:
                return Action(ActionType.CHECK, player.seat_idx, 0, state.phase)
            return Action(ActionType.CALL, player.seat_idx, min(to_call, player.stack), state.phase)

        hand_score = evaluate_best_5_from_7(all_cards)
        to_call = state.current_bet - player.current_bet
        is_aggressor = state.last_aggressor_idx == player.seat_idx

        if hand_score.hand_rank >= HandRank.STRAIGHT:
            # Strong hand — bet/raise
            if to_call > 0:
                return self._make_raise(state, player, 3 * state.current_bet)
            return self._make_bet(state, player, int(0.75 * state.pot.main_pot))

        if hand_score.hand_rank >= HandRank.TWO_PAIR:
            if to_call <= 0:
                return self._make_bet(state, player, int(0.5 * state.pot.main_pot))
            if to_call < player.stack * 0.3:
                return Action(ActionType.CALL, player.seat_idx, to_call, state.phase)
            return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)

        if hand_score.hand_rank >= HandRank.ONE_PAIR:
            if to_call <= 0:
                if random.random() < self.personality.aggression:
                    return self._make_bet(state, player, int(0.33 * state.pot.main_pot))
                return Action(ActionType.CHECK, player.seat_idx, 0, state.phase)
            if to_call <= player.stack * 0.15:
                return Action(ActionType.CALL, player.seat_idx, to_call, state.phase)
            return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)

        # High card / nothing
        if to_call <= 0:
            if random.random() < self.personality.bluff_freq:
                return self._make_bet(state, player, int(0.5 * state.pot.main_pot))
            return Action(ActionType.CHECK, player.seat_idx, 0, state.phase)
        return Action(ActionType.FOLD, player.seat_idx, 0, state.phase)

    def _make_raise(self, state, player, amount) -> Action:
        actual = min(amount, player.stack)
        if actual >= player.stack + player.current_bet:
            return Action(ActionType.ALL_IN, player.seat_idx, player.stack + player.current_bet, state.phase)
        return Action(ActionType.RAISE, player.seat_idx, actual, state.phase)

    def _make_bet(self, state, player, amount) -> Action:
        actual = min(max(amount, state.blinds[1]), player.stack)
        if actual >= player.stack:
            return Action(ActionType.ALL_IN, player.seat_idx, player.stack, state.phase)
        return Action(ActionType.BET, player.seat_idx, actual, state.phase)

    def difficulty_factor(self) -> float:
        """Returns a multiplier for error probability. lower = tighter play."""
        return {"easy": 1.5, "medium": 1.0, "hard": 0.5}.get(self.difficulty, 1.0)


# Register
BotRegistry.register("rule_easy", lambda personality=None: RuleBot(personality or BotPersonality(vpip=0.40, pfr=0.10, aggression=0.3, bluff_freq=0.20), "easy"))
BotRegistry.register("rule_medium", lambda personality=None: RuleBot(personality or BotPersonality(vpip=0.25, pfr=0.18, aggression=0.5, bluff_freq=0.15), "medium"))
BotRegistry.register("rule_hard", lambda personality=None: RuleBot(personality or BotPersonality(vpip=0.20, pfr=0.15, aggression=0.7, bluff_freq=0.10), "hard"))
```

- [ ] **Step 4: Write tests for RuleBot**

```python
# backend/tests/test_rule_bot.py
import pytest
from sekhmet.game_engine.game_state import GameState, GamePhase, Player, PlayerStatus
from sekhmet.game_engine.action_processor import ActionType
from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.ai_engine.rule_bot import RuleBot, _hand_tier
from sekhmet.ai_engine.bot_registry import BotPersonality

def _c(r, s): return Card(r, s)

def test_hand_tier_premium():
    assert _hand_tier(_c(Rank.ACE, Suit.SPADES), _c(Rank.ACE, Suit.HEARTS)) == 1  # AA
    assert _hand_tier(_c(Rank.KING, Suit.SPADES), _c(Rank.KING, Suit.HEARTS)) == 1  # KK

def test_hand_tier_weak():
    assert _hand_tier(_c(Rank.SEVEN, Suit.SPADES), _c(Rank.TWO, Suit.HEARTS)) == 5  # 72o

@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_bot_makes_legal_preflop_action(difficulty):
    """Bot always returns a syntactically valid action."""
    bot = RuleBot(BotPersonality(), difficulty)
    players = (
        Player(0, "Bot", 1000, (_c(Rank.ACE, Suit.SPADES), _c(Rank.KING, Suit.SPADES)),
               PlayerStatus.ACTIVE, 0, 0, False),
        Player(1, "Hero", 1000, (), PlayerStatus.ACTIVE, 10, 10, True),
    )
    state = GameState(
        phase=GamePhase.PREFLOP, players=players, community_cards=(),
        current_player_idx=0, dealer_idx=0, last_aggressor_idx=None,
        current_bet=10, min_raise=10, round_history=(), blinds=(5, 10),
        hand_number=1,
    )
    from sekhmet.game_engine.pot_manager import PotState
    state = state._replace(pot=PotState(main_pot=15))

    action = bot.decide(state, 0)
    assert action.type in (ActionType.FOLD, ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN)
    assert action.player_idx == 0

def test_bot_folds_garbage_preflop():
    bot = RuleBot(BotPersonality(vpip=0.20), "hard")
    players = (
        Player(0, "Bot", 1000, (_c(Rank.SEVEN, Suit.CLUBS), _c(Rank.TWO, Suit.HEARTS)),
               PlayerStatus.ACTIVE, 0, 0, False),
        Player(1, "Hero", 1000, (), PlayerStatus.ACTIVE, 10, 10, True),
    )
    state = GameState(GamePhase.PREFLOP, players, (), 0, 0, None, 10, 10, (), (5, 10), 1)
    from sekhmet.game_engine.pot_manager import PotState
    state = state._replace(pot=PotState(main_pot=15))
    action = bot.decide(state, 0)
    # With 72o and facing a raise, should almost always fold
    # (Allow rare non-fold for randomness, but check it exists)
    assert action.type in (ActionType.FOLD, ActionType.CALL, ActionType.RAISE)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_rule_bot.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/sekhmet/ai_engine/ backend/tests/test_rule_bot.py
git commit -m "feat: add BaseBot interface, RuleBot, and BotRegistry"
```

---

## Phase 6: Frontend — Game Table

### Task 8: Frontend scaffold and core components

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/pages/Lobby.tsx`
- Create: `frontend/src/pages/GameTable.tsx`
- Create: `frontend/src/components/table/OvalTable.tsx`
- Create: `frontend/src/components/table/CardView.tsx`
- Create: `frontend/src/components/table/ActionBar.tsx`
- Create: `frontend/src/hooks/useWebSocket.ts`
- Create: `frontend/src/hooks/useGameState.ts`

- [ ] **Step 1: Scaffold Vite + React + TS project**

```bash
cd frontend && npm create vite@latest . -- --template react-ts
```

Manual: Create `package.json`:

```json
{
  "name": "sekhmet-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^19.0",
    "react-dom": "^19.0",
    "react-router-dom": "^7.0"
  },
  "devDependencies": {
    "@types/react": "^19.0",
    "@types/react-dom": "^19.0",
    "@vitejs/plugin-react": "^4.3",
    "typescript": "~5.7",
    "vite": "^6.0"
  }
}
```

```ts
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 3000, proxy: { '/api': 'http://localhost:8000', '/ws': { target: 'ws://localhost:8000', ws: true } } },
})
```

- [ ] **Step 2: Create entry point and routing**

```tsx
// frontend/src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)

// frontend/src/App.tsx
import { Routes, Route } from 'react-router-dom'
import Lobby from './pages/Lobby'
import GameTable from './pages/GameTable'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Lobby />} />
      <Route path="/game/:tableId" element={<GameTable />} />
    </Routes>
  )
}
```

- [ ] **Step 3: Create useWebSocket hook**

```ts
// frontend/src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback, useState } from 'react'

interface WsMessage {
  type: string
  [key: string]: unknown
}

export function useWebSocket(tableId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null)
  const listenersRef = useRef<Map<string, Set<(msg: WsMessage) => void>>>(new Map())

  useEffect(() => {
    if (!tableId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/table/${tableId}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (event) => {
      const msg: WsMessage = JSON.parse(event.data)
      setLastMessage(msg)
      listenersRef.current.get(msg.type)?.forEach(fn => fn(msg))
      listenersRef.current.get('*')?.forEach(fn => fn(msg))
    }

    return () => { ws.close() }
  }, [tableId])

  const send = useCallback((msg: object) => {
    wsRef.current?.send(JSON.stringify(msg))
  }, [])

  const on = useCallback((type: string, fn: (msg: WsMessage) => void) => {
    if (!listenersRef.current.has(type)) listenersRef.current.set(type, new Set())
    listenersRef.current.get(type)!.add(fn)
    return () => { listenersRef.current.get(type)?.delete(fn) }
  }, [])

  return { connected, lastMessage, send, on }
}
```

- [ ] **Step 4: Create useGameState hook**

```ts
// frontend/src/hooks/useGameState.ts
import { useReducer, useCallback } from 'react'

export interface PlayerState {
  seat_idx: number; name: string; stack: number; status: string
  current_bet: number; is_human: boolean
}

export interface GameView {
  phase: string
  community_cards: string[]
  pot: number
  current_bet: number
  current_player_idx: number
  players: PlayerState[]
  hole_cards: string[]
  hand_number: number
  my_seat: number
  available_actions: { action: string; amount?: number; min?: number; max?: number }[]
}

type GameAction =
  | { type: 'UPDATE_STATE'; payload: Partial<GameView> }
  | { type: 'SET_HOLE_CARDS'; cards: string[] }
  | { type: 'SET_ACTIONS'; actions: GameView['available_actions'] }
  | { type: 'SET_MY_SEAT'; seat: number }
  | { type: 'RESET' }

const initial: GameView = {
  phase: 'waiting', community_cards: [], pot: 0, current_bet: 0,
  current_player_idx: -1, players: [], hole_cards: [], hand_number: 0,
  my_seat: -1, available_actions: [],
}

function reducer(state: GameView, action: GameAction): GameView {
  switch (action.type) {
    case 'UPDATE_STATE': return { ...state, ...action.payload }
    case 'SET_HOLE_CARDS': return { ...state, hole_cards: action.cards }
    case 'SET_ACTIONS': return { ...state, available_actions: action.actions }
    case 'SET_MY_SEAT': return { ...state, my_seat: action.seat }
    case 'RESET': return { ...initial, my_seat: state.my_seat }
  }
}

export function useGameState() {
  const [state, dispatch] = useReducer(reducer, initial)
  const updateState = useCallback((payload: Partial<GameView>) =>
    dispatch({ type: 'UPDATE_STATE', payload }), [])
  const setHoleCards = useCallback((cards: string[]) =>
    dispatch({ type: 'SET_HOLE_CARDS', cards }), [])
  const setActions = useCallback((actions: GameView['available_actions']) =>
    dispatch({ type: 'SET_ACTIONS', actions }), [])
  const setMySeat = useCallback((seat: number) =>
    dispatch({ type: 'SET_MY_SEAT', seat }), [])
  const reset = useCallback(() => dispatch({ type: 'RESET' }), [])
  return { state, updateState, setHoleCards, setActions, setMySeat, reset }
}
```

- [ ] **Step 5: Create CardView component**

```tsx
// frontend/src/components/table/CardView.tsx
interface CardViewProps {
  card?: string  // e.g. "A♠" or "K♥", undefined = face down
  highlighted?: boolean
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_MAP = { sm: 'w-8 h-12 text-xs', md: 'w-10 h-14 text-sm', lg: 'w-12 h-16 text-base' }

export default function CardView({ card, highlighted, size = 'md' }: CardViewProps) {
  if (!card) {
    // Face down card
    return (
      <div className={`${SIZE_MAP[size]} rounded-md bg-gradient-to-br from-blue-900 to-blue-950
        border border-blue-700 flex items-center justify-center`}>
        <div className="w-4/5 h-3/4 rounded-sm bg-blue-800/50 border border-blue-600/30"
             style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(0,0,255,0.05) 2px, rgba(0,0,255,0.05) 4px)' }} />
      </div>
    )
  }

  const suit = card.slice(-1)
  const rank = card.slice(0, -1)
  const isRed = '♥♦'.includes(suit)

  return (
    <div className={`${SIZE_MAP[size]} rounded-md flex flex-col items-center justify-center
      bg-gradient-to-br from-gray-900 to-gray-950 shadow-lg
      ${highlighted ? 'ring-2 ring-yellow-500 shadow-[0_0_12px_rgba(255,215,0,0.3)]' : ''}
      ${isRed ? 'border border-red-600/60' : 'border border-gray-500/40'}`}>
      <span className={`font-bold leading-none ${isRed ? 'text-red-400' : 'text-gray-200'}`}>{rank}</span>
      <span className={`leading-none ${isRed ? 'text-red-500' : 'text-gray-300'}`}>{suit}</span>
    </div>
  )
}
```

- [ ] **Step 6: Create ActionBar component**

```tsx
// frontend/src/components/table/ActionBar.tsx
import { useState } from 'react'

interface ActionBarProps {
  actions: { action: string; amount?: number; min?: number; max?: number }[]
  onAction: (action: string, amount?: number) => void
  disabled?: boolean
  timeout?: number
}

export default function ActionBar({ actions, onAction, disabled, timeout }: ActionBarProps) {
  const [raiseAmount, setRaiseAmount] = useState('')

  const hasAction = (name: string) => actions.find(a => a.action === name)

  return (
    <div className="bg-gradient-to-b from-gray-900 to-black rounded-lg p-3 flex items-center gap-3 justify-center flex-wrap">
      {hasAction('fold') && (
        <button onClick={() => onAction('fold')} disabled={disabled}
          className="px-6 py-2 rounded-md bg-gray-800 border border-gray-600 text-gray-400 hover:bg-gray-700 disabled:opacity-50">
          弃牌
        </button>
      )}
      {hasAction('check') && (
        <button onClick={() => onAction('check')} disabled={disabled}
          className="px-6 py-2 rounded-md bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700 disabled:opacity-50">
          过牌
        </button>
      )}
      {hasAction('call') && (
        <button onClick={() => onAction('call', hasAction('call')!.amount)} disabled={disabled}
          className="px-6 py-2 rounded-md bg-blue-900 border border-blue-600 text-white hover:bg-blue-800 disabled:opacity-50">
          跟注 {hasAction('call')!.amount}
        </button>
      )}
      {hasAction('raise') && (
        <div className="flex items-center gap-2">
          <input type="number" value={raiseAmount}
            onChange={e => setRaiseAmount(e.target.value)}
            placeholder={`${hasAction('raise')!.min}+`}
            className="w-24 px-3 py-2 rounded-md bg-gray-800 border border-gray-600 text-white text-sm" />
          <button onClick={() => onAction('raise', Number(raiseAmount))} disabled={disabled || !raiseAmount}
            className="px-5 py-2 rounded-md bg-red-900 border border-red-700 text-white hover:bg-red-800 disabled:opacity-50">
            加注
          </button>
        </div>
      )}
      {hasAction('all_in') && (
        <button onClick={() => onAction('all_in', hasAction('all_in')!.amount)} disabled={disabled}
          className="px-5 py-2 rounded-md bg-yellow-700 border border-yellow-500 text-white font-bold hover:bg-yellow-600 disabled:opacity-50">
          全下!
        </button>
      )}
      {timeout !== undefined && (
        <span className="text-gray-500 text-sm ml-2">⏱ {timeout}s</span>
      )}
    </div>
  )
}
```

- [ ] **Step 7: Create OvalTable component**

```tsx
// frontend/src/components/table/OvalTable.tsx
import { PlayerState } from '../../hooks/useGameState'
import CardView from './CardView'

interface OvalTableProps {
  players: PlayerState[]
  communityCards: string[]
  pot: number
  currentPlayerIdx: number
  mySeat: number
}

export default function OvalTable({ players, communityCards, pot, currentPlayerIdx, mySeat }: OvalTableProps) {
  const n = players.length
  if (n === 0) return null

  // Arrange seats around the ellipse
  const arrangeSeat = (index: number, total: number) => {
    // My seat is always at the bottom center
    // Arrange others around the top half of the ellipse
    const myIdx = players.findIndex(p => p.seat_idx === mySeat)
    const relativePos = ((index - myIdx + total) % total)

    if (relativePos === 0) {
      // This is the user — always at bottom center
      return { top: '85%', left: '50%', transform: 'translate(-50%, -50%)' }
    }

    // Distribute others around top ellipse
    const others = total - 1
    const myPosition = index < myIdx ? index + total - myIdx - 1 : index - myIdx - 1
    const angle = Math.PI - (myPosition + 0.5) * (Math.PI / others)
    const rx = 42  // horizontal radius in %
    const ry = 35  // vertical radius in %
    const x = 50 + rx * Math.cos(angle)
    const y = 42 - ry * Math.sin(angle)

    return { top: `${y}%`, left: `${x}%`, transform: 'translate(-50%, -50%)' }
  }

  return (
    <div className="relative w-full" style={{ paddingBottom: '60%' }}>
      {/* Table body */}
      <div className="absolute inset-0 mx-4 mb-8"
        style={{
          borderRadius: '50% / 40%',
          background: 'linear-gradient(180deg, #5D3A1A 0%, #8B5E3C 30%, #6B3A2A 60%, #4A2511 100%)',
          boxShadow: '0 4px 30px rgba(0,0,0,0.6), 0 0 0 6px #3d1f0a, 0 0 0 9px #2a1508',
        }}>
        {/* Inner felt */}
        <div className="absolute inset-3 rounded-[50%/40%] border-2 border-yellow-700/50"
          style={{ background: 'radial-gradient(ellipse at center, #1a6e2e 0%, #0d4a1a 50%, #0a3312 100%)' }}>
        </div>
      </div>

      {/* Community cards */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex gap-2">
        {communityCards.map((card, i) => (
          <CardView key={i} card={card} size="md" />
        ))}
        {/* Empty community card slots */}
        {Array.from({ length: Math.max(0, 5 - communityCards.length) }).map((_, i) => (
          <CardView key={`empty-${i}`} size="md" />
        ))}
      </div>

      {/* Pot display */}
      {pot > 0 && (
        <div className="absolute top-[62%] left-1/2 -translate-x-1/2 text-yellow-400 text-sm font-bold">
          底池: ¥{pot}
        </div>
      )}

      {/* Player seats */}
      {players.map((player, i) => {
        const pos = arrangeSeat(i, n)
        const isMe = player.seat_idx === mySeat
        const isCurrent = player.seat_idx === currentPlayerIdx
        return (
          <div key={player.seat_idx} className="absolute" style={pos}>
            <div className={`flex flex-col items-center gap-1`}>
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold
                ${isMe
                  ? 'bg-gradient-to-br from-green-900 to-green-950 border-2 border-yellow-500 shadow-[0_0_12px_rgba(255,215,0,0.5)] text-yellow-300'
                  : 'bg-gradient-to-br from-green-800 to-green-900 border border-yellow-700/50 text-gray-200'} 
                ${isCurrent ? 'ring-2 ring-white animate-pulse' : ''}`}>
                {isMe ? '你' : player.name.slice(0, 2)}
              </div>
              <span className="text-xs text-gray-400">¥{player.stack}</span>
              {player.status === 'folded' && <span className="text-xs text-red-500">已弃牌</span>}
              {player.status === 'all_in' && <span className="text-xs text-yellow-500">All-in</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 8: Create GameTable page**

```tsx
// frontend/src/pages/GameTable.tsx
import { useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useWebSocket } from '../hooks/useWebSocket'
import { useGameState } from '../hooks/useGameState'
import OvalTable from '../components/table/OvalTable'
import ActionBar from '../components/table/ActionBar'
import CardView from '../components/table/CardView'

export default function GameTable() {
  const { tableId } = useParams<{ tableId: string }>()
  const { connected, send, on } = useWebSocket(tableId ?? null)
  const { state, updateState, setHoleCards, setActions, setMySeat } = useGameState()

  useEffect(() => {
    const unsubs = [
      on('welcome', (msg) => setMySeat(msg.seat_idx as number)),
      on('game_state_update', (msg) => updateState(msg as any)),
      on('hole_cards', (msg) => setHoleCards(msg.cards as string[])),
      on('your_turn', (msg) => setActions(msg.available_actions as any[])),
    ]
    return () => unsubs.forEach(fn => fn())
  }, [on, updateState, setHoleCards, setActions, setMySeat])

  const handleAction = useCallback((action: string, amount?: number) => {
    send({ type: 'player_action', action, amount })
    setActions([])  // Clear actions after sending
  }, [send, setActions])

  const handleStartHand = () => send({ type: 'start_hand' })

  const isMyTurn = state.available_actions.length > 0

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-black text-white flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-black/50 border-b border-gray-800">
        <h1 className="text-lg font-bold text-yellow-500">桌 {tableId}</h1>
        <div className="flex items-center gap-4 text-sm text-gray-400">
          <span>{connected ? '🟢 已连接' : '🔴 断开'}</span>
          <span>手牌 #{state.hand_number}</span>
        </div>
      </div>

      {/* Table area */}
      <div className="flex-1 flex flex-col items-center justify-center p-4">
        <OvalTable
          players={state.players}
          communityCards={state.community_cards}
          pot={state.pot}
          currentPlayerIdx={state.current_player_idx}
          mySeat={state.my_seat}
        />

        {/* Hole cards */}
        {state.hole_cards.length > 0 && (
          <div className="flex gap-2 mt-4">
            {state.hole_cards.map((card, i) => (
              <CardView key={i} card={card} highlighted size="lg" />
            ))}
          </div>
        )}
      </div>

      {/* Action bar */}
      <div className="p-2">
        {state.phase === 'waiting' ? (
          <div className="flex justify-center">
            <button onClick={handleStartHand}
              className="px-8 py-3 rounded-lg bg-yellow-600 hover:bg-yellow-500 text-white font-bold text-lg">
              开始新一手牌
            </button>
          </div>
        ) : (
          <ActionBar
            actions={state.available_actions}
            onAction={handleAction}
            disabled={!isMyTurn}
          />
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 9: Install frontend deps and verify build**

Run: `cd frontend && npm install && npm run build`
Expected: Build succeeds

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat: add React frontend — game table with oval layout, card/chip rendering, action bar"
```

---

## Phase 7: Full Game Loop Integration

### Task 9: Wire up AI auto-play in WebSocket

**Files:**
- Modify: `backend/sekhmet/api/ws.py`

- [ ] **Step 1: Add AI auto-step to WS handler**

In `backend/sekhmet/api/ws.py`, add this method to `_advance_if_needed` or as a separate post-action hook:

```python
async def _auto_play_ai(table_id: str):
    """If current player is AI, make their decision and broadcast."""
    state = table_manager.tables[table_id]
    conns = table_manager.connections[table_id]
    processor = ActionProcessor()

    while True:
        if state.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            break

        current_player = state.players[state.current_player_idx]
        if current_player.is_human or current_player.status not in (PlayerStatus.ACTIVE,):
            break

        # Import bot creation
        from ..ai_engine.bot_registry import BotRegistry, BotPersonality
        bot = BotRegistry.create("rule_medium")
        action = bot.decide(state, state.current_player_idx)
        state = processor.execute(state, action)

        # Broadcast bot's action
        for ws in conns.values():
            await ws.send_json({
                "type": "bot_action",
                "player_idx": action.player_idx,
                "action": action.type.value,
                "amount": action.amount,
            })

        table_manager.tables[table_id] = state
        await _broadcast_state(table_id)

        if state.phase == GamePhase.SHOWDOWN:
            await _handle_showdown(table_id)
            break


async def _handle_showdown(table_id: str):
    """Resolve showdown — evaluate hands, award pot, show results."""
    state = table_manager.tables[table_id]
    conns = table_manager.connections[table_id]

    from ..game_engine.hand_evaluator import evaluate_best_5_from_7
    from ..game_engine.pot_manager import create_side_pots, award_pot

    # Gather player bets and hand scores
    player_bets = {}
    hand_scores = {}
    active_players = set()
    for p in state.players:
        if p.status in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN):
            player_bets[p.seat_idx] = p.total_bet
            active_players.add(p.seat_idx)
            if p.hole_cards:
                all_cards = list(p.hole_cards) + list(state.community_cards)
                hand_scores[p.seat_idx] = evaluate_best_5_from_7(all_cards)

    remaining_after_folds = {p.seat_idx for p in state.players if p.status != PlayerStatus.FOLDED}

    side_pots = create_side_pots(player_bets, active_players)
    payouts = award_pot(side_pots, remaining_after_folds, hand_scores)

    # Broadcast results
    for ws in conns.values():
        await ws.send_json({
            "type": "hand_result",
            "hands": {
                str(pid): {
                    "cards": [str(c) for c in state.players[pid].hole_cards] if state.players[pid].status != PlayerStatus.FOLDED else None,
                    "score": str(hand_scores.get(pid, "Folded")),
                }
                for pid in hand_scores
            },
            "payouts": payouts,
            "side_pots": [{"amount": sp.amount, "eligible": list(sp.eligible_players)} for sp in side_pots],
        })

    # Reset for next hand — update stacks, rotate dealer, clear state
    new_players = []
    for p in state.players:
        won = payouts.get(p.seat_idx, 0)
        new_players.append(p._replace(
            stack=p.stack + won,
            hole_cards=(),
            status=PlayerStatus.SITTING_OUT,
            current_bet=0,
            total_bet=0,
        ))
    n = len(state.players)
    new_dealer = (state.dealer_idx + 1) % n
    new_state = GameState.create_new(
        dealer_idx=new_dealer,
        small_blind=state.blinds[0],
        big_blind=state.blinds[1],
    )
    new_state = new_state._replace(
        players=tuple(new_players),
        hand_number=state.hand_number + 1,
    )
    table_manager.tables[table_id] = new_state
```

- [ ] **Step 2: Run integration test — start a game and verify AI responds**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All existing tests continue to pass

- [ ] **Step 3: Commit**

```bash
git add backend/sekhmet/api/ws.py
git commit -m "feat: add AI auto-play and showdown resolution to game loop"
```

---

## What's Next (Future Phases)

After the core game loop works end-to-end (human plays vs AI at a visual table), continue with:

1. **Trainer module** — scenario library, runner, scorer, analyzer (per spec §5)
2. **GTO Bot** — precomputed range tables, postflop strategy based on board texture (per spec §4.4)
3. **History + Replay** — store hand records, replay viewer (per spec §6.1)
4. **Tournament mode** — MTT/SNG with blind level progression, ICM considerations
5. **Mobile polish** — responsive CSS for phone-sized screens (per spec §6.5)
6. **RL Bot** — deep reinforcement learning integration (per spec §4.1, Level 5)
