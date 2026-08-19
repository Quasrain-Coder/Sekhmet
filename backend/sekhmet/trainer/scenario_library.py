"""Scenario library — load, list, and filter training scenarios."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from ..game_engine import GamePhase, GameState, Player
from ..game_engine.deck import Card, Rank, Suit
from ..game_engine.game_state import PotState

_PHASE = {p.name: p for p in GamePhase}
_RANK = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
         "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
_SUIT = {"♠": Suit.SPADES, "♥": Suit.HEARTS, "♦": Suit.DIAMONDS, "♣": Suit.CLUBS}


def _card(text: str) -> Card:
    return Card(Rank(_RANK[text[:-1]]), _SUIT[text[-1]])


def _state(phase, player_seat, hole, board, pot, dealer, sb, bb,
           current_bet, stack, *, hero_current_bet: int | None = None) -> GameState:
    """Build a frozen 2-handed state for a builtin scenario.

    The player's seat is *player_seat* (0 or 1); the other seat holds
    generic cards (never shown).  *pot* is the pot so far, *current_bet*
    is the bet the hero faces: the villain (the other seat) holds it as
    its ``current_bet``, and unless *hero_current_bet* is given the hero
    has not yet matched it (``to_call = current_bet``).  A hero who is
    the big blind may set *hero_current_bet* to the blind to model "big
    blind checks" — then ``to_call = current_bet - bb``.
    """
    cards = [_card(c) for c in hole]
    if hero_current_bet is None:
        hero_current_bet = current_bet if player_seat == bb else 0
    villain = Player(
        name="Villain", seat_idx=1 - player_seat, stack=stack,
        hole_cards=(_card("2♠"), _card("3♣")),
        current_bet=current_bet if 1 - player_seat != bb else 0,
    )
    you = Player(
        name="You", seat_idx=player_seat, stack=stack,
        hole_cards=tuple(cards), is_human=True,
        current_bet=hero_current_bet,
    )
    return GameState(
        phase=_PHASE[phase],
        players=(you, villain),
        community_cards=tuple(_card(c) for c in board),
        pot=PotState(main_pot=pot),
        dealer_idx=dealer,
        current_player_idx=player_seat,
        current_bet=current_bet,
        min_raise=10,
        small_blind=5,
        big_blind=10,
        sb_seat=sb,
        bb_seat=bb,
    )

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
    # Which seat the player holds in ``frozen_state`` (rendering only).
    player_seat: int | None = None

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
            frozen_state=data.get("frozen_state"),
            player_seat=data.get("player_seat"),
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
        # Concrete 9-handed table: you are UTG (seat 3) with K♠J♥.
        "player_seat": 3,
        "frozen_state": _state(
            phase="PREFLOP", player_seat=3,
            hole=("K♠", "J♥"), board=(), pot=15,
            dealer=8, sb=0, bb=1, current_bet=10, stack=200,
        ),
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
        "player_seat": 5,
        "frozen_state": _state(
            phase="PREFLOP", player_seat=5,
            hole=("A♠", "K♠"), board=(), pot=15,
            dealer=5, sb=0, bb=1, current_bet=10, stack=200,
        ),
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
        "player_seat": 1,
        "frozen_state": _state(
            phase="FLOP", player_seat=1,
            hole=("A♣", "Q♣"), board=("A♦", "9♠", "2♥"), pot=60,
            # Villain (BB, seat 0) bet 40 into 60 — hero faces 40.
            dealer=0, sb=1, bb=0, current_bet=40, stack=180,
        ),
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
        "player_seat": 0,
        "frozen_state": _state(
            phase="RIVER", player_seat=0,
            hole=("8♣", "7♣"), board=("10♠", "9♠", "2♥", "4♦", "5♠"), pot=110,
            dealer=0, sb=0, bb=1, current_bet=0, stack=190,
        ),
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
        "player_seat": 0,
        "frozen_state": _state(
            phase="TURN", player_seat=0,
            hole=("A♥", "K♥"), board=("3♥", "7♥", "10♣", "Q♦"), pot=150,
            dealer=0, sb=0, bb=1, current_bet=50, stack=150,
        ),
    },
    {
        "id": "river-oppo-sets",
        "title": "河牌对手暗三条",
        "description": "你在河牌是两对，对手在转牌加注后河牌又重锤全下",
        "category": "river_decision",
        "difficulty": 4,
        "optimal_action": {"type": "FOLD", "amount": 0},
        "acceptable_range": {"FOLD": [0.65, 1.0], "CALL": [0.0, 0.35]},
        "hints": [
            "河牌面对这种重注，你需要击败对方的价值范围",
            "两对在这里只赢诈唬，很难有足够的胜率",
            "对手在转牌加注并河牌全下，几乎从不诈唬",
        ],
        "analysis": {
            "equity_vs_range": 0.22,
            "ev_fold": 0.0,
            "ev_call": -1.4,
        },
        "player_seat": 0,
        "frozen_state": _state(
            phase="RIVER", player_seat=0,
            hole=("K♣", "Q♣"), board=("K♦", "Q♥", "3♠", "7♦", "9♠"), pot=200,
            dealer=0, sb=0, bb=1, current_bet=150, stack=120,
        ),
    },
    {
        "id": "river-blocker-bluff",
        "title": "河牌拿阻断张诈唬",
        "description": "你在河牌只有高牌 A，但手里有 A♠ 阻断坚果同花，对手过牌",
        "category": "river_decision",
        "difficulty": 5,
        "optimal_action": {"type": "BET", "amount": 80},
        "acceptable_range": {"BET": [0.55, 1.0], "CHECK": [0.0, 0.45]},
        "hints": [
            "没有摊牌价值，只能通过下注取胜",
            "A♠ 阻断坚果同花，是少数几个值得诈唬的阻断张",
            "下注一个接近底池的尺度最能施压",
        ],
        "analysis": {
            "equity_vs_range": 0.12,
            "ev_bluff": 1.9,
            "ev_check": -1.2,
        },
        "player_seat": 0,
        "frozen_state": _state(
            phase="RIVER", player_seat=0,
            hole=("A♠", "3♦"), board=("J♠", "10♠", "4♠", "8♦", "2♣"), pot=80,
            dealer=0, sb=0, bb=1, current_bet=0, stack=200,
        ),
    },
    {
        "id": "river-third-bullet",
        "title": "河牌第三条街开火",
        "description": "你翻前加注、转牌持续下注，河牌发出空白牌，对手再次过牌",
        "category": "river_decision",
        "difficulty": 3,
        "optimal_action": {"type": "BET", "amount": 60},
        "acceptable_range": {"BET": [0.60, 1.0], "CHECK": [0.0, 0.40]},
        "hints": [
            "对手连过三条街，几乎从不埋伏，你大概率领先",
            "空白河牌没有改变牌面，你的范围优势仍在",
            "三条街下注（triple barrel）在低级别极难被跟注",
        ],
        "analysis": {
            "equity_vs_range": 0.65,
            "ev_bet": 1.6,
            "ev_check": 0.4,
        },
        "player_seat": 0,
        "frozen_state": _state(
            phase="RIVER", player_seat=0,
            hole=("A♦", "Q♣"), board=("7♠", "3♣", "2♥", "10♠", "5♦"), pot=100,
            dealer=0, sb=0, bb=1, current_bet=0, stack=180,
        ),
    },
    {
        "id": "position-bb-ace-high",
        "title": "大盲位 A 高牌翻后",
        "description": "你在 BB 用 A5o 补盲进池，翻牌 A72 彩虹，对手下注 1/3 底池",
        "category": "position",
        "difficulty": 3,
        "optimal_action": {"type": "CALL", "amount": 0},
        "acceptable_range": {"CALL": [0.55, 1.0], "RAISE": [0.0, 0.45]},
        "hints": [
            "翻牌顶对虽然只能赢价值，但你的范围里包含更多 Ax",
            "跟注看一张转牌，保留对手诈唬的空间",
            "加注只会打走你赢的那些范围",
        ],
        "analysis": {
            "equity_vs_range": 0.58,
            "ev_call": 1.2,
            "ev_raise": 0.3,
        },
        "player_seat": 1,
        "frozen_state": _state(
            phase="FLOP", player_seat=1,
            hole=("A♠", "5♥"), board=("A♦", "7♣", "2♠"), pot=40,
            # Villain (SB, seat 0) bet 15 into 40 — hero (BB, seat 1)
            # checks, so faces the full 15 (to_call = 15 - 0).
            dealer=0, sb=0, bb=1, current_bet=15, stack=180,
            hero_current_bet=0,
        ),
    },
    {
        "id": "position-btn-steal",
        "title": "BTN 偷盲",
        "description": "你在 BTN，前面弃牌到你，SB 是一个较紧的玩家",
        "category": "position",
        "difficulty": 1,
        "optimal_action": {"type": "RAISE", "amount": 25},
        "acceptable_range": {"RAISE": [0.80, 1.0], "FOLD": [0.0, 0.20]},
        "hints": [
            "BTN 是全场最好的位置，可以施加最大压力",
            "偷盲加注通常使用 2.5BB 的标准尺度",
            "紧的 SB 弃牌率很高，你的偷盲会更有利可图",
        ],
        "analysis": {
            "equity_vs_range": 0.52,
            "ev_raise": 1.4,
            "ev_fold": -0.5,
        },
        "player_seat": 5,
        "frozen_state": _state(
            phase="PREFLOP", player_seat=5,
            hole=("A♠", "2♣"), board=(), pot=15,
            dealer=5, sb=0, bb=1, current_bet=10, stack=200,
        ),
    },
    {
        "id": "pot-odds-flush-rebuy",
        "title": "翻牌圈同花听牌跟注",
        "description": "你在翻牌拿到同花听牌，对手下注 3/4 底池",
        "category": "pot_odds",
        "difficulty": 2,
        "optimal_action": {"type": "CALL", "amount": 0},
        "acceptable_range": {"CALL": [0.85, 1.0], "RAISE": [0.0, 0.15]},
        "hints": [
            "九张同花听牌在翻牌圈约有 36% 的胜率",
            "对手下注 3/4 底池，你的跟注赔率约 1.8:1，足以支持听牌",
            "没有位置，不要用加注把底池做大",
        ],
        "analysis": {
            "equity_vs_range": 0.36,
            "pot_odds_required": 0.30,
            "ev_call": 0.9,
        },
        "player_seat": 1,
        "frozen_state": _state(
            phase="FLOP", player_seat=1,
            hole=("J♥", "8♥"), board=("K♥", "5♦", "2♣"), pot=80,
            # Villain (BB, seat 0) bet 60 into 80 — hero (seat 1) calls 60.
            dealer=0, sb=1, bb=0, current_bet=60, stack=200,
        ),
    },
    {
        "id": "bluffing-flop-raise-semi",
        "title": "翻牌圈半诈唬加注",
        "description": "你在小盲位补盲进池，翻牌击中两头顺听牌",
        "category": "bluffing",
        "difficulty": 3,
        "optimal_action": {"type": "RAISE", "amount": 55},
        "acceptable_range": {"RAISE": [0.5, 1.0], "CALL": [0.0, 0.50]},
        "hints": [
            "两头顺听牌是标准的半诈唬：落后对手但赢率充足",
            "加注同时有弃牌收益和实现权益，比单纯跟注更均衡",
            "不要用加注赶走对手的范围里你赢不了的部分",
        ],
        "analysis": {
            "equity_vs_range": 0.40,
            "ev_raise": 1.5,
            "ev_call": 0.4,
        },
        "player_seat": 1,
        "frozen_state": _state(
            phase="FLOP", player_seat=1,
            hole=("8♣", "7♣"), board=("6♠", "5♥", "K♦"), pot=60,
            dealer=0, sb=1, bb=0, current_bet=20, stack=180,
        ),
    },
    {
        "id": "value-flop-two-pair-raise",
        "title": "翻牌两对加注打价值",
        "description": "你在小盲位拿到 Q9o，翻牌击中两对，底池已被加注",
        "category": "postflop_value",
        "difficulty": 2,
        "optimal_action": {"type": "RAISE", "amount": 70},
        "acceptable_range": {"RAISE": [0.6, 1.0], "CALL": [0.0, 0.40]},
        "hints": [
            "两对在翻牌圈是强牌，需要尽快建立底池",
            "Q9 这类两对容易被对手反超，加注保护权益",
            "在你的弃牌范围里加入一些价值加注，平衡打法",
        ],
        "analysis": {
            "equity_vs_range": 0.80,
            "ev_raise": 2.1,
            "ev_call": 1.0,
        },
        "player_seat": 1,
        "frozen_state": _state(
            phase="FLOP", player_seat=1,
            hole=("Q♠", "9♠"), board=("Q♦", "9♥", "3♣"), pot=120,
            # Villain (BTN, seat 0) bet 40 into 120 — hero (SB, seat 1) raises.
            dealer=0, sb=1, bb=0, current_bet=40, stack=180,
        ),
    },
    {
        "id": "preflop-sb-strong-call",
        "title": "翻前小盲对抗强范围",
        "description": "你在 SB 拿到 QQ，BTN 加注到 3BB，你需要补全盲注",
        "category": "preflop_range",
        "difficulty": 2,
        "optimal_action": {"type": "CALL", "amount": 0},
        "acceptable_range": {"CALL": [0.5, 1.0], "RAISE": [0.0, 0.50]},
        "hints": [
            "QQ 对抗 BTN 的宽范围有明显优势",
            "没有位置，跟注可以控制底池并保持灵活",
            "如果 4bet，你会让对手轻松弃掉大部分被你统治的范围",
        ],
        "analysis": {
            "equity_vs_range": 0.68,
            "ev_call": 1.1,
            "ev_raise": 0.6,
        },
        "player_seat": 1,
        "frozen_state": _state(
            phase="PREFLOP", player_seat=1,
            hole=("Q♠", "Q♣"), board=(), pot=45,
            # Villain (BTN, seat 0) raised to 30 — pot = SB 5 + BB 10 +
            # BTN 30; hero (SB, seat 1) already has 5 in, calls 25.
            dealer=0, sb=1, bb=0, current_bet=30, stack=190,
            hero_current_bet=5,
        ),
    },
    {
        "id": "value-overpair-check-raise",
        "title": "翻牌超对价值下注",
        "description": "你翻前加注进池，翻牌你拿着超对 J",
        "category": "postflop_value",
        "difficulty": 1,
        "optimal_action": {"type": "BET", "amount": 45},
        "acceptable_range": {"BET": [0.75, 1.0], "CHECK": [0.0, 0.25]},
        "hints": [
            "超对在翻牌圈是价值牌，必须主动下注",
            "持续下注约 1/2 底池即可，不用过大",
            "在干燥牌面上可以打得更小，保留对手更宽的范围",
        ],
        "analysis": {
            "equity_vs_range": 0.72,
            "ev_bet": 1.4,
            "ev_check": 0.6,
        },
        "player_seat": 0,
        "frozen_state": _state(
            phase="FLOP", player_seat=0,
            hole=("J♠", "J♣"), board=("7♦", "3♠", "2♥"), pot=90,
            dealer=0, sb=0, bb=1, current_bet=0, stack=200,
        ),
    },
    {
        "id": "bluffing-float-dry-board",
        "title": "干燥翻牌漂浮跟注",
        "description": "对手在干燥翻牌下注，你手里是带后门花的中等对子",
        "category": "bluffing",
        "difficulty": 2,
        "optimal_action": {"type": "CALL", "amount": 0},
        "acceptable_range": {"CALL": [0.55, 1.0], "FOLD": [0.0, 0.45]},
        "hints": [
            "干燥牌面上对手的下注范围很宽，你可以用中对子跟注",
            "你的后门同花和后门顺子能增加实现权益",
            "别急着加注，留一个下注回合给转牌诈唬",
        ],
        "analysis": {
            "equity_vs_range": 0.48,
            "ev_call": 0.8,
            "ev_fold": -0.5,
        },
        "player_seat": 1,
        "frozen_state": _state(
            phase="FLOP", player_seat=1,
            hole=("8♥", "8♦"), board=("A♦", "4♣", "2♠"), pot=70,
            dealer=0, sb=1, bb=0, current_bet=25, stack=170,
        ),
    },
]
