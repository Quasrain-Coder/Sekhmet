"""Scenario library — load, list, and filter training scenarios."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class ScenarioCategory(Enum):
    PREFLOP_RANGE = "preflop_range"
    POSTFLOP_VALUE = "postflop_value"
    BLUFFING = "bluffing"
    RIVER_DECISION = "river_decision"
    POT_ODDS = "pot_odds"
    POSITION = "position"


@dataclass
class Scenario:
    """A single training scenario."""

    id: str
    title: str
    description: str
    category: ScenarioCategory
    difficulty: int  # 1–5
    optimal_action: dict[str, Any]  # {"type": "FOLD", "amount": 0}
    acceptable_range: dict[str, list[float]] = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)
    analysis: dict[str, Any] = field(default_factory=dict)
    # Frozen game state (set by runner after loading)
    frozen_state: Any = None

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> "Scenario":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            category=ScenarioCategory(data["category"]),
            difficulty=data.get("difficulty", 1),
            optimal_action=data["optimal_action"],
            acceptable_range=data.get("acceptable_range", {}),
            hints=data.get("hints", []),
            analysis=data.get("analysis", {}),
        )


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


class ScenarioLibrary:
    """In-memory collection of scenarios loaded from YAML files."""

    def __init__(self, data_dir: str | Path = "data/scenarios"):
        self.data_dir = Path(data_dir)
        self._scenarios: dict[str, Scenario] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def load_all(self) -> int:
        """Scan data_dir for .yaml files and load them.  Returns count."""
        self._scenarios.clear()
        if not self.data_dir.exists():
            return 0
        for path in self.data_dir.glob("*.yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    s = Scenario.from_yaml(data)
                    self._scenarios[s.id] = s
                elif isinstance(data, list):
                    for item in data:
                        s = Scenario.from_yaml(item)
                        self._scenarios[s.id] = s
            except Exception:
                logger.exception("Failed to load scenario %s", path)
        return len(self._scenarios)

    def get(self, scenario_id: str) -> Scenario | None:
        return self._scenarios.get(scenario_id)

    def list_all(self) -> list[Scenario]:
        return sorted(self._scenarios.values(), key=lambda s: (s.category.value, s.difficulty))

    def list_by_category(self, category: ScenarioCategory) -> list[Scenario]:
        return [s for s in self._scenarios.values() if s.category == category]

    def list_by_difficulty(self, max_diff: int) -> list[Scenario]:
        return [s for s in self._scenarios.values() if s.difficulty <= max_diff]

    def add(self, scenario: Scenario) -> None:
        self._scenarios[scenario.id] = scenario

    def __len__(self) -> int:
        return len(self._scenarios)


# ---------------------------------------------------------------------------
# Built-in scenarios (fallback when no YAML files exist)
# ---------------------------------------------------------------------------

BUILTIN_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "preflop-utg-marginal",
        "title": "翻前 UTG 边缘手牌",
        "description": "你在 UTG 位置拿到 KJo，前序无人行动，你该怎么办？",
        "category": "preflop_range",
        "difficulty": 2,
        "optimal_action": {"type": "FOLD", "amount": 0},
        "acceptable_range": {"FOLD": [0.70, 1.0], "RAISE": [0.0, 0.30]},
        "hints": [
            "UTG 位置最差，范围应该最紧",
            "KJo 在 9 人桌 UTG 是负 EV 手牌",
            "从早期位置打边缘手牌会让你在翻后处于不利位置",
        ],
        "analysis": {
            "equity_vs_range": 0.42,
            "ev_fold": 0.0,
            "ev_raise": -0.8,
        },
    },
    {
        "id": "preflop-btn-premium",
        "title": "翻前 BTN 强牌",
        "description": "你在 BTN 拿到 AKs，前序全部弃牌到你",
        "category": "preflop_range",
        "difficulty": 1,
        "optimal_action": {"type": "RAISE", "amount": 30},
        "acceptable_range": {"RAISE": [0.90, 1.0]},
        "hints": [
            "AKs 是顶级手牌，在 BTN 应该加注",
            "加注可以建立底池并隔离较弱的对手",
        ],
        "analysis": {
            "equity_vs_range": 0.67,
            "ev_raise": 2.5,
        },
    },
    {
        "id": "flop-top-pair-faces-bet",
        "title": "翻后顶对面对下注",
        "description": "你在翻牌圈中了顶对顶踢，对手下注 2/3 底池",
        "category": "postflop_value",
        "difficulty": 3,
        "optimal_action": {"type": "CALL", "amount": 0},
        "acceptable_range": {"CALL": [0.60, 1.0], "RAISE": [0.0, 0.40]},
        "hints": [
            "顶对顶踢在干燥牌面上有很好的摊牌价值",
            "跟注可以控制底池，避免在翻牌圈过度膨胀",
            "如果你认为对手在诈唬，也可以考虑加注",
        ],
        "analysis": {
            "equity_vs_range": 0.72,
            "ev_call": 1.8,
            "ev_raise": 0.5,
        },
    },
    {
        "id": "river-bluff-spot",
        "title": "河牌诈唬机会",
        "description": "河牌完成可能的同花，你手里没有同花但有位置优势",
        "category": "bluffing",
        "difficulty": 4,
        "optimal_action": {"type": "BET", "amount": 75},
        "acceptable_range": {"BET": [0.50, 1.0], "CHECK": [0.0, 0.50]},
        "hints": [
            "河牌完成同花听牌，这是诈唬的好时机",
            "你没有摊牌价值，只有下注才能赢",
            "下注 2/3 底池左右比较可信",
        ],
        "analysis": {
            "equity_vs_range": 0.15,
            "ev_bluff": 2.3,
            "ev_check": -1.0,
        },
    },
    {
        "id": "pot-odds-draw",
        "title": "底池赔率与听牌",
        "description": "你在转牌有同花听牌，对手全下 50 到 100 的底池",
        "category": "pot_odds",
        "difficulty": 3,
        "optimal_action": {"type": "CALL", "amount": 0},
        "acceptable_range": {"CALL": [0.80, 1.0]},
        "hints": [
            "同花听牌有约 18-20% 的胜率",
            "你跟注 50 赢 150，赔率是 3:1，需要 25% 胜率",
            "实际上你的期望值为正，应该跟注",
        ],
        "analysis": {
            "equity_vs_range": 0.20,
            "pot_odds_required": 0.25,
            "ev_call": 0.8,
        },
    },
]
