---
name: sekhmet-dev
description: >
  当你对 /home/quasrain/repos/Sekhmet 目录下的任何文件进行修改、编辑、新增、删除、重构、修复 bug、添加功能、编写测试、调整配置、更新文档时，必须使用此 skill。
  只要工作目录或操作涉及 Sekhmet 仓库，无论任务大小（改一行代码、修一个 typo、调整样式、重构架构），都必须先加载此 skill 获取项目上下文和开发规范。
  本项目是一个德州扑克游戏与训练平台，后端 Python FastAPI + WebSocket + SQLite，前端 React (Vite + TypeScript)。支持单机 vs AI 对战和情景训练。
---

# Sekhmet 项目开发指南

## 核心理念

Sekhmet 是一个**个人德州扑克学习平台**，核心由三个子系统组成：游戏引擎、AI 引擎、情景训练器。理解这些是关键：

- **游戏引擎是不可变状态机**：每次动作产生新的 `GameState` 快照，便于回放、撤销和测试。状态流转严格单向。
- **AI 引擎通过插件化注册**：所有 Bot 继承 `BaseBot` 接口，通过 `BotRegistry` 工厂创建。新增 Bot 等级无需改动引擎代码。
- **训练器是引擎的只读消费者**：场景冻结游戏状态在某个决策点，玩家提交决策后由 `Scorer` 和 `Analyzer` 评估。
- **模块化单体架构**：单进程内按清晰边界拆分为 `game_engine/`、`ai_engine/`、`trainer/` 独立包，通过接口通信，将来可抽离为微服务。

## 分支策略

- **`main`** — 主要开发分支，日常开发在此分支上进行
- **`release`** — 发布分支，稳定版本从这里发布
- **新功能** — 必须从 `main` 拉出新分支开发，不允许直接在 `main` 或 `release` 上提交
- **合入规则** — 向 `main` 或 `release` 合入代码必须通过 Pull Request，**由用户确认后才能合入**，不允许直接 push 或 merge

### 开发流程

```
main ─── feature/xxx ─── PR ──→ main ─── PR ──→ release
  │                            │
  └── 日常开发基础               └── 需用户审批
```

1. 从 `main` 创建 feature 分支：`git checkout -b feature/xxx main`
2. 在 feature 分支上开发和提交
3. 开发完成后，向 `main` 发起 PR，等用户审批合入
4. 准备发布时，从 `main` 向 `release` 发起 PR，等用户审批合入

**重要**：除非用户明确指示，否则**不要自行合并任何 PR**。所有合入操作必须等待用户确认。

## 架构速览

```
浏览器                         服务端
┌──────────────┐  WebSocket    ┌──────────────────────────────┐
│ React App    │◄─────────────►│ FastAPI                       │
│ (Vite + TS)  │  JSON msgs    │  ├─ api/ws.py (消息路由)       │
│              │               │  ├─ game_engine/ (核心逻辑)    │
│              │  REST         │  ├─ ai_engine/ (Bot 工厂)      │
│              │◄─────────────►│  ├─ trainer/ (训练器)          │
│              │  (历史/场景)    │  ├─ models/ (ORM + 记录)       │
│              │               │  └─ config.py (全局配置)       │
└──────────────┘               └──────────────────────────────┘
```

### 数据流（以一手牌为例）

```
玩家点击 Raise → WebSocket send → ws.py 收到 player_action
  → action_processor.validate() 校验合法性
  → action_processor.execute() 产生新 GameState
  → 检查是否需要推进回合 (all acted & bets equalized)
  → 如果需要 AI 行动：调用 ai_engine → bot.decide(state, idx) → 自动执行
  → ws.py 广播 game_state_update 给所有在线玩家
  → 前端更新牌桌状态
```

关键原则：**永远在 game_engine 中修改状态，在 ws.py 中做消息路由，在 ai_engine 中做 bot 决策**。不要在 ws.py 里写游戏逻辑或 AI 决策。

## 项目结构

```
Sekhmet/
├── backend/                         # Python 包
│   ├── game_engine/                 # 德州扑克核心引擎
│   │   ├── deck.py                  # 牌组管理 (52张标准牌，Fisher-Yates 洗牌)
│   │   ├── hand_evaluator.py        # 手牌强度评估 (7选5最佳牌型，Trevor 查表法)
│   │   ├── game_state.py            # 游戏状态机 (GameState 不可变快照)
│   │   ├── action_processor.py      # 动作合法性校验与执行
│   │   ├── pot_manager.py           # 底池管理 (分池算法)
│   │   └── rules/                   # 规则配置
│   │       └── blind_structure.py   # 盲注结构 (现金桌固定 / MTT 递增)
│   │
│   ├── ai_engine/                   # AI 引擎
│   │   ├── base_bot.py              # AI 基类接口 (abstract decide())
│   │   ├── rule_bot.py              # 规则型 bot (Level 1-3)
│   │   ├── gto_bot.py               # GTO 查表 bot (Level 4)
│   │   ├── rl_bot.py                # RL 模型接口 (Level 5，预留)
│   │   └── bot_registry.py          # bot 工厂/注册
│   │
│   ├── trainer/                     # 情景训练器
│   │   ├── scenario_library.py      # 场景库管理 (CRUD + 分类)
│   │   ├── scenario_runner.py       # 场景执行引擎 (冻结状态 → 等待决策)
│   │   ├── scorer.py                # 决策评分 (动作匹配 60% + Sizing 25% + 时机 15%)
│   │   ├── analyzer.py              # 深度分析 (equity、范围、GTO 偏差)
│   │   └── scenario_generator.py    # 自动生成训练场景 (基于历史弱点)
│   │
│   ├── api/                         # FastAPI 路由
│   │   ├── game.py                  # 游戏 REST 端点: 创建牌桌 / 加入 / 状态查询
│   │   ├── trainer.py               # 训练 REST 端点: 场景列表 / 进度查询
│   │   ├── history.py               # 对局历史 REST 端点
│   │   └── ws.py                    # WebSocket 处理器: 游戏动作 + 训练交互
│   │
│   ├── models/                      # ORM 模型 + 数据类
│   │   ├── game_record.py           # 对局记录
│   │   ├── hand_history.py          # 单手牌历史 (含完整 GameState 序列)
│   │   └── training_progress.py     # 训练进度 (场景ID + 得分 + 时间戳)
│   │
│   ├── data/                        # 静态数据
│   │   ├── scenarios/               # 预设计场景库 (YAML)
│   │   └── gto_tables/              # GTO 范围表 (CSV / binary)
│   │
│   ├── config.py                    # 全局配置 (牌桌参数、AI 等级、评分权重)
│   └── requirements.txt
│
├── frontend/                        # React (Vite + TS)
│   └── src/
│       ├── pages/                   # 页面级组件
│       │   ├── Lobby.tsx            # 大厅: 创建/加入牌桌
│       │   ├── GameTable.tsx        # 牌桌: 游戏主界面 (状态驱动渲染)
│       │   ├── Trainer.tsx          # 训练器: 场景分类 + 进度
│       │   ├── ScenarioDetail.tsx   # 训练决策页
│       │   └── History.tsx          # 对局历史列表
│       ├── components/
│       │   ├── table/               # 牌桌相关组件
│       │   │   ├── OvalTable.tsx    # 椭圆桌渲染 (玩家环绕排列)
│       │   │   ├── CardView.tsx     # 单张牌渲染 (暗夜霓虹风格)
│       │   │   ├── ChipStack.tsx    # 筹码堆叠 + 下注动画
│       │   │   ├── PotDisplay.tsx   # 底池金额显示
│       │   │   ├── CommunityCards.tsx  # 公共牌区
│       │   │   ├── PlayerSeat.tsx   # 玩家座位 (你: 金色，对手: 绿色)
│       │   │   └── ActionBar.tsx    # 动作栏: 弃牌|过牌|跟注|加注|全下 + 计时器
│       │   ├── trainer/             # 训练器组件
│       │   │   ├── CategoryCard.tsx # 场景分类卡片 + 进度条
│       │   │   ├── FeedbackPanel.tsx# 分层反馈面板 (简洁 → 详细 → 范围可视化)
│       │   │   └── HintButton.tsx   # 可选提示按钮
│       │   └── shared/              # 通用组件
│       │       ├── HandReplay.tsx   # 对局回放播放器
│       │       └── ScoreChart.tsx   # 训练得分趋势图
│       └── hooks/                   # 自定义 Hooks
│           ├── useWebSocket.ts      # WebSocket 连接管理 (自动重连)
│           ├── useGameState.ts      # 游戏状态管理 (useReducer 驱动)
│           └── useTrainer.ts        # 训练交互逻辑
│
├── docker-compose.yml               # 一键部署
├── README.md
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-06-13-sekhmet-poker-platform-design.md  # 完整设计文档
```

## 游戏状态机 (GamePhase)

```
WAITING → DEALING → PREFLOP → FLOP → TURN → RIVER → SHOWDOWN → WAITING
```

- **WAITING**：等待玩家就绪，开始新一手牌
- **DEALING**：发底牌（每人 2 张），收集 ante/blinds
- **PREFLOP**：翻前下注轮（从小盲后开始）
- **FLOP**：发 3 张公共牌 → 下注轮
- **TURN**：发第 4 张公共牌 → 下注轮
- **RIVER**：发第 5 张公共牌 → 下注轮
- **SHOWDOWN**：摊牌比大小 + 分池 → 结算 → 回到 WAITING

**提前终止**：除一人外全部弃牌 → 直接跳 SHOWDOWN，最后未弃牌者全收底池。

阶段转换**只在 `game_engine/action_processor.py` 中发生**：
- 每次动作执行后检查：所有人行动完毕且下注额一致？→ 推进到下一阶段
- 只剩一人未弃牌？→ 跳 SHOWDOWN
- ws.py 调用 `action_processor.execute()` 后广播新状态

## 开发模式

### 添加新的 Bot 等级

需要改 3 个地方：

1. **新建 bot 文件** (如 `ai_engine/new_bot.py`) — 继承 `BaseBot`，实现 `decide(state, player_idx) → Action`
2. **bot_registry.py** — 注册新 bot：`BotRegistry.register("new_bot", NewBot)`
3. **前端 Lobby** — 在 Bot 选择列表中添加新选项

### 添加新的训练场景

需要改 2 个地方：

1. **`data/scenarios/`** 目录下添加 YAML 文件，包含：
   - 场景元信息（id、标题、分类、难度）
   - 冻结的 `GameState`（用 pickle 序列化）
   - 最优动作和可接受范围
   - 分级提示文本
2. **scenario_library.py** — 确保 `load_scenarios()` 能扫描到新文件

### 修改底池分池逻辑

分池逻辑在 `game_engine/pot_manager.py` 中：
- `create_side_pots()` — 根据 all-in 金额生成边池
- `award_pot()` — 按牌力排序分配底池

修改时注意：
- `SidePot` 结构包含 `amount` 和 `eligible_players` (set[int])
- 主池所有人都有资格，边池只有投入足够金额的玩家有资格
- 每个边池独立按牌力排名分配

### 修改评分权重

评分逻辑在 `trainer/scorer.py` 中：
- `score_action_match()` — 动作匹配度 (默认权重 60%)
- `score_sizing()` — Sizing 精度 (默认权重 25%)
- `score_timing()` — 时机判断 (默认权重 15%)

权重通过 `config.py` 中的 `SCORING_WEIGHTS` 字典集中管理，修改只需改配置。

### 修改手牌评估（牌型排名）

牌型排名逻辑在 `game_engine/hand_evaluator.py` 中（Trevor 查表法）：
- `evaluate_7_cards()` — 从 7 张牌选最佳 5 张并返回 `HandScore`
- `HandScore` 是可比较对象，含牌型 rank 和 kicker 列表
- 同牌型时逐个比较 kicker

## WebSocket 消息协议

### 客户端 → 服务端

| type | 字段 | 说明 |
|------|------|------|
| `player_action` | `action: FOLD\|CHECK\|CALL\|BET\|RAISE\|ALL_IN`, `amount?` | 玩家动作 |
| `sit_down` | `seat_idx`, `buyin` | 入座 |
| `stand_up` | — | 离座 |
| `start_hand` | — | 房主开始新一手牌 |
| `trainer_submit` | `scenario_id`, `action`, `amount?` | 训练决策提交 |
| `request_hint` | `scenario_id` | 请求训练提示 |

### 服务端 → 客户端

| type | 触发时机 | 接收者 |
|------|----------|--------|
| `game_state_update` | 状态变更（发牌/动作/回合推进） | 全员 |
| `hand_result` | 摊牌结束（牌型展示 + 分池结果） | 全员 |
| `player_joined` | 新玩家加入 | 牌桌全员 |
| `player_left` | 玩家离开 | 牌桌全员 |
| `your_turn` | 轮到你行动 | 仅当前玩家 |
| `available_actions` | 列出当前可选动作 | 仅当前玩家 |
| `bot_action` | AI 做出动作 | 全员 |
| `trainer_feedback` | 训练决策评分结果 | 仅训练者 |
| `error` | 操作失败 | 仅操作者 |
| `hand_start` | 新一手牌开始 | 全员 |

### 消息设计原则

- **私密信息走单播**：你的底牌、训练反馈、可选动作列表
- **公共状态走广播**：公共牌、底池金额、各玩家动作和筹码变化
- **敏感字段服务端过滤**：对手底牌仅在 SHOWDOWN 时揭示，且只揭示摊牌者的牌
- 新增消息类型时，确保不会泄露不应公开的信息

## 前端约定

### 状态管理

使用 React `useReducer` 管理游戏状态（不使用全局 store，因为是单页单桌）：

```typescript
// hooks/useGameState.ts
type GameStateAction =
  | { type: 'UPDATE_STATE'; payload: GameState }
  | { type: 'SET_HAND'; payload: Card[] }
  | { type: 'SHOWDOWN'; payload: ShowdownResult }
  | { type: 'RESET' };
```

WebSocket 消息通过 `useWebSocket` hook 接收，自动 dispatch 到 `useGameState`。

### 组件渲染逻辑

`GameTable.tsx` 按 `gameState.phase` 结合 `isMyTurn` 条件渲染：

```tsx
{/* 公共牌区 — flop 及之后显示 */}
{phase !== 'PREFLOP' && phase !== 'WAITING' && phase !== 'DEALING' && (
  <CommunityCards cards={gameState.community_cards} />
)}

{/* 动作栏 — 仅轮到你时可用 */}
{isMyTurn ? (
  <ActionBar actions={gameState.available_actions} onAction={handleAction} />
) : (
  <WaitingIndicator currentPlayer={gameState.current_player_idx} />
)}
```

### 视觉规范

牌桌视觉风格已确定（详见设计文档 §6.2）：
- **牌桌**：经典赌场暗调椭圆桌——深色木框 + 墨绿台呢 + 金色装饰线
- **牌面**：暗夜霓虹风格——深色底 + 发光花色，♥♦ 红边框，♠♣ 灰边框
- **筹码**：经典条纹筹码——径向条纹 + 锯齿边缘，白/红/蓝/绿/黑 对应不同面值
- **你的位置**：金色光效突出，底部中央固定
- **对手**：绿色圆形标记，环绕椭圆桌排列

新增视觉元素时遵循此风格体系。

### 移动端适配

- 椭圆桌缩小为简化版，对手水平排列在顶部
- 动作按钮垂直堆叠（拇指友好），加注金额用底部抽屉输入
- 手牌和公共牌大字显示
- 使用 CSS 媒体查询 `@media (max-width: 768px)` 切换布局

## 后端约定

### 不可变 GameState

```python
# game_engine/game_state.py
@dataclass(frozen=True)
class GameState:
    phase: GamePhase
    players: tuple[Player, ...]     # 不可变序列
    community_cards: tuple[Card, ...]
    pot: PotState
    current_player_idx: int
    dealer_idx: int
    last_aggressor_idx: int | None
    current_bet: int
    round_history: tuple[Action, ...]
    blinds: tuple[int, int]
```

每次动作通过 `action_processor.execute(state, action)` 返回一个新 `GameState` 实例。这保证：
- 回放：保存的 `round_history` 可以完整重现整手牌
- 撤销：训练器可以回到任意决策点
- 测试：给定 state + action，预期 result 完全确定

### Bot 接口

```python
# ai_engine/base_bot.py
class BaseBot(ABC):
    @abstractmethod
    def decide(self, state: GameState, player_idx: int) -> Action: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def style_description(self) -> str: ...
```

所有 Bot 必须实现此接口。`bot_registry.py` 负责：
- 注册/查询可用 Bot
- 按配置创建 Bot 实例（含性格参数）

### 错误处理

所有游戏逻辑错误通过 `GameError` 及其子类抛出：

- `InvalidActionError` — 当前游戏状态不允许此动作
- `IllegalAmountError` — 下注金额不合法（小于最小加注 / 超过筹码）
- `NotYourTurnError` — 非该玩家行动轮次
- `PhaseError` — 当前阶段不允许此操作
- `TableFullError` — 牌桌已满
- `InsufficientFundsError` — 筹码不足
- `ScenarioNotFoundError` — 训练场景不存在

ws.py 统一捕获 `GameError` 并返回 `{"type": "error", "message": str(e)}` 给操作者。

### 训练场景文件格式

场景存储在 `data/scenarios/` 目录下，每个文件一个 YAML：

```yaml
id: "preflop-utg-marginal"
title: "翻前 UTG 边缘手牌"
description: "你在 UTG 位置拿到 KJo，前序无人行动"
category: "preflop_range"
difficulty: 2
optimal_action: { type: "FOLD", amount: 0 }
acceptable_range:
  FOLD: [0.7, 1.0]
  RAISE: [0.0, 0.3]
hints:
  - "UTG 位置最差，范围应该最紧"
  - "KJo 在 9 人桌 UTG 是负 EV 手牌"
analysis:
  equity_vs_range: 0.42
  ev_fold: 0
  ev_raise: -0.8
```

## 测试

### 运行测试

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -v
```

### 测试结构

```
backend/tests/
├── test_deck.py             # 牌组创建、洗牌、发牌
├── test_hand_evaluator.py   # 牌型评估 (最需要覆盖——各种牌型组合)
├── test_action_processor.py # 动作合法性校验 + 回合推进
├── test_pot_manager.py      # 分池算法 (all-in 多边池场景)
├── test_game_state.py       # GameState 不可变性 + 转换
├── test_rule_bot.py         # 规则型 Bot 决策
├── test_scorer.py           # 训练评分逻辑
├── test_scenario_runner.py  # 场景执行
└── test_ws.py               # WebSocket 集成测试
```

### 编写测试的模式

核心辅助方法（建议放入 `tests/conftest.py`）：

```python
def make_empty_table(n_seats=9):
    """创建空牌桌"""
    return GameState(phase=GamePhase.WAITING, players=(), ...)

def add_player(state, seat_idx, stack=1000, is_human=True):
    """添加玩家并返回新 state"""

def make_heads_up_state():
    """创建 HU 场景的标准 state"""

def make_showdown_state(hero_cards, villain_cards, community_cards):
    """创建摊牌场景用于测试牌型比较"""
```

**重要**：按照 [[feedback_ci]] 记忆，每次新增模块必须同步更新 CI test/coverage 步骤。

## 常见开发任务

### 修改盲注结构

1. `backend/game_engine/rules/blind_structure.py` 修改盲注配置
2. 如果是 MTT 盲注递增表，修改对应的 level 列表
3. 前端如有显示盲注信息，同步更新

### 给 RuleBot 增加新的决策规则

1. 在 `ai_engine/rule_bot.py` 的决策树中添加新分支
2. 确保新规则覆盖所有相关 GamePhase
3. 在 `test_rule_bot.py` 中为新规则添加测试用例

### 添加新的场景分类

1. 在 `trainer/scenario_library.py` 的 `ScenarioCategory` 枚举中添加新值
2. 在 `data/scenarios/` 下创建对应子目录
3. 更新前端 `Trainer.tsx` 的分类筛选逻辑

### 调整 AI 性格参数

1. `BotPersonality` dataclass 中添加新字段（如需要）
2. 在 `bot_registry.py` 的 Bot 工厂方法中传入新参数
3. `rule_bot.py` 的决策逻辑中读取新参数并影响决策
4. 前端 Bot 选择界面如有详细展示，同步更新

### 切换数据库（SQLite → PostgreSQL）

1. `backend/config.py` 修改 `DATABASE_URL`
2. 确保所有 ORM 模型不依赖 SQLite 特有语法
3. `docker-compose.yml` 添加 PostgreSQL 服务
4. 迁移脚本 (Alembic) 初始化表结构

## 部署

`docker-compose up` 一键启动：

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes: ["./backend/data:/app/data"]

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
```

生产环境可改为 FastAPI serve 前端 build 产物（类似 Dolos）。

## 文档

- `README.md` — 项目简介
- `docs/superpowers/specs/2026-06-13-sekhmet-poker-platform-design.md` — 完整设计文档（权威参考）
- `.claude/skills/sekhmet-dev/SKILL.md` — 本文件（开发指南）

设计文档是所有开发决策的权威来源。在开始任何模块实现前，先查阅设计文档中的对应章节。如果实现中需要偏离设计文档，先更新设计文档再编码。

## 当前状态

项目目前处于**设计完成、待实现**阶段。主要代码尚未开始编写。以下为建议的实现顺序：

1. **game_engine** — 先建德州扑克核心：deck → hand_evaluator → game_state → action_processor → pot_manager
2. **api + ws** — 基础 WebSocket 通道 + 简单终端可玩
3. **ai_engine (rule_bot)** — 最简可对战 AI
4. **frontend GameTable** — 可视化牌桌
5. **trainer** — 训练器（依赖 game_engine 稳定）
6. **ai_engine (GTO/RL)** — 高级 AI
7. **history + replay** — 对局记录和回放
