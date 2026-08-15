# Sekhmet — 德州扑克游戏与训练平台 · 设计文档

> 2026-06-13 · 个人学习工具，帮助从入门进阶

## 1. 项目定位

Sekhmet 是一个**个人德州扑克学习平台**——单机对战 AI + 情景训练，帮你从入门玩家进阶。同时支持朋友间本地对战。

| 维度 | 决策 |
|------|------|
| 用户规模 | 个人/小圈子，自托管 |
| 对战模式 | 纯单机 vs AI，支持任意人数同桌 |
| 游戏模式 | 现金桌 (Cash Game) + 锦标赛 (MTT/SNG) |
| 规则 | No-Limit Hold'em，标准规则 |
| 训练器 | 情景训练，分层反馈（简洁 → 深度分析） |
| 部署 | 本地优先，支持家庭服务器/云，需移动端适配 |
| 技术栈 | Python (FastAPI) 后端 + React (Vite + TS) 前端 |

## 2. 系统架构

**模块化单体** —— 单个 Python 进程，内部按清晰边界拆成独立包，通过接口通信。前端 React SPA，WebSocket 实时通信。将来可抽离微服务。

```
Sekhmet/
├── backend/                     # Python 包
│   ├── game_engine/             # 德州扑克核心引擎
│   │   ├── deck.py              # 牌组管理
│   │   ├── hand_evaluator.py    # 手牌强度评估（7选5最佳牌型）
│   │   ├── game_state.py        # 游戏状态机
│   │   ├── action_processor.py  # 动作合法性校验与执行
│   │   ├── pot_manager.py       # 底池管理（分池算法）
│   │   └── rules/               # 规则配置（盲注结构等）
│   │
│   ├── ai_engine/               # AI 引擎
│   │   ├── base_bot.py          # AI 基类接口
│   │   ├── rule_bot.py          # 规则型 bot（Level 1-3）
│   │   ├── gto_bot.py           # GTO 查表 bot（Level 4）
│   │   ├── rl_bot.py            # RL 模型接口（Level 5，预留）
│   │   └── bot_registry.py      # bot 工厂/注册
│   │
│   ├── trainer/                 # 情景训练器
│   │   ├── scenario_library.py  # 场景库管理
│   │   ├── scenario_runner.py   # 场景执行引擎
│   │   ├── scorer.py            # 决策评分
│   │   ├── analyzer.py          # 深度分析（equity、范围、GTO偏差）
│   │   └── scenario_generator.py# 自动生成训练场景
│   │
│   ├── api/                     # FastAPI 路由
│   │   ├── game.py              # 游戏相关端点
│   │   ├── trainer.py           # 训练相关端点
│   │   ├── history.py           # 对局历史
│   │   └── ws.py                # WebSocket 处理器
│   │
│   ├── models/                  # ORM 模型
│   │   ├── game_record.py
│   │   ├── hand_history.py
│   │   └── training_progress.py
│   │
│   └── config.py                # 全局配置
│
├── frontend/                    # React (Vite + TS)
│   └── src/
│       ├── pages/               # Lobby, GameTable, Trainer, History
│       ├── components/          # table/, trainer/, shared/
│       └── hooks/               # useWebSocket, useGameState
│
├── docker-compose.yml
└── README.md
```

**通信方式**：前端 ↔ 后端主要走 WebSocket（游戏实时状态推送 + 动作提交），REST 用于历史记录、场景管理等非实时操作。

**存储**：SQLite 本地默认，可切换到 PostgreSQL。

## 3. 游戏引擎

### 3.1 状态机

```
WAITING → DEALING → PREFLOP → FLOP → TURN → RIVER → SHOWDOWN → WAITING
```

中途除一人外全部弃牌 → 直接跳 SHOWDOWN，最后未弃牌者全收底池。

### 3.2 核心数据结构

**GameState**（不可变快照，每次动作产生新实例，便于回放和撤销）：

```python
@dataclass
class GameState:
    phase: GamePhase                    # 当前阶段
    players: list[Player]               # 玩家列表（座位、筹码、手牌、状态）
    community_cards: list[Card]         # 公共牌 (0/3/4/5)
    pot: PotState                       # 主池 + 边池
    current_player_idx: int             # 当前行动玩家索引
    dealer_idx: int                     # 按钮位
    last_aggressor_idx: int | None      # 最后主动加注者
    current_bet: int                    # 当前轮次最大下注额
    round_history: list[Action]         # 本局所有动作
    acted_seats: tuple[int, ...]        # 本轮已行动座位（回合结束判定依据，每街重置）
    blinds: tuple[int, int]             # (小盲, 大盲)
```

**PotState**（支持分池——all-in 场景）：

```python
@dataclass
class PotState:
    main_pot: int                       # 主池
    side_pots: list[SidePot]            # 边池列表，按 all-in 金额递增
    # SidePot: {amount: int, eligible_players: set[int]}
```

**Action**：

```python
class Action:
    type: FOLD | CHECK | CALL | BET | RAISE | ALL_IN
    amount: int
    player_idx: int
    phase: GamePhase
```

### 3.3 Hand Evaluator

用查表法（Trevor 算法）：从 7 张牌中找出最佳 5 张组合，返回可直接比较的 `HandScore`。

需处理：
- 牌型排名：皇家同花顺 > 同花顺 > 四条 > 葫芦 > 同花 > 顺子 > 三条 > 两对 > 一对 > 高牌
- 同牌型 kicker 比较
- 分池时按牌力排序，确定边池归属

### 3.4 Action Processor

1. 合法性校验（轮次、金额合法性、最小加注）
2. 执行动作（更新筹码、底池、推进回合）
3. 回合推进判定：所有可行动玩家（未弃牌且未 all-in）**均已行动**（在 `acted_seats` 中）且下注额一致 —— "已行动"追踪是大盲 option 的保障：翻前溜入底池时大盲必须获得一次行动机会
4. 提前结束判定（只剩一人未弃牌 → 直接 SHOWDOWN，不发完牌面，胜者无需亮牌）
5. 阶段推进时发放公共牌（flop 3 张 / turn 1 张 / river 1 张，无烧牌——数字牌堆烧牌无意义）
6. 无人可再行动（其余玩家全部 all-in）→ 自动发完剩余公共牌直进 SHOWDOWN（runout），牌局不得停滞

## 4. AI 引擎

### 4.1 Bot 等级体系

```
Level 1  ── RuleBot(easy)    被动跟注型，偶尔诈唬
Level 2  ── RuleBot(medium)  基本位置意识，会加注
Level 3  ── RuleBot(hard)    攻击型 TAG 风格，懂得 sizing
Level 4  ── GTOBot           基于 GTO 范围表的近似策略
Level 5  ── RLBot(预留)      神经网络模型，自博弈训练
```

### 4.2 Base Bot 接口

```python
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

### 4.3 RuleBot

决策树：手牌分类 → 位置调整 → 场景匹配 → 动作生成。

实现要点（与代码同步）：

- **翻前**：`_preflop_strength` 启发式牌力分（高张/低张/对子/同花/
  连张），按难度与位置调整跟注/加注门槛；位置按真实行动顺序计算
  （翻后以按钮为锚、翻前以大盲为锚，只统计未弃牌座位）。
- **翻后**：成牌按类别映射到保守近似 equity（`_RANK_EQUITY`，不是
  类别序号——顶对/两对/三条不再被当弱牌），听牌数 outs（含卡顺与
  wheel，已成型类别不产生 outs）+ 2/4 法则折算 equity，面对下注按
  equity vs 所需胜率决定跟/弃。
- **诈唬**：半诈唬概率按街道（翻 > 转 > 河）与底池大小缩放；抓诈唬
  概率按 pot odds 调价（小注多抓、超额下注少抓），L2+ 生效。
- **对手模型**：`ai_engine/stats_tracker.py` 跨手牌追踪每座 VPIP /
  PFR / 翻后弃牌率 / 激进度（Laplace 平滑），挂在牌桌 session 上、
  每次动作执行后由 table_manager 记录；L2+ 读取对手模型调整诈唬
  频率（对高弃牌率对手多诈、对激进对手多抓）。

按难度注入"合理错误"：
- **easy**：过度跟注、追听牌赔率不够也追、极少加注
- **medium**：基本 GTO 近似，偶尔 sizing 不佳
- **hard**：接近 GTO，精准 sizing，会混合策略

### 4.4 GTOBot（L4，已实现）

GTO 风格近似（非实时求解、非精确 GTO），由 `ai_engine/gto_bot.py` +
`ai_engine/gto_ranges.py` 实现：

- **翻前**：位置化范围表（`gto_ranges.py`）——RFI（各位置开池范围）、
  3-bet、平跟、BB 防守、4-bet、call-vs-3bet，含混合频率（如 A5s 50%
  3-bet）；范围字符串语法 `77+` / `A9s+` / `97s+` / `TT-88`。混合
  频率用由手牌+街道种子派生的确定性 RNG 掷骰，同一手牌在一手牌内
  行为稳定。
- **翻后**：以精确手牌对对手估计范围（last aggressor，范围按翻前
  故事——加注/溜入——与位置推断）做蒙特卡洛 equity（200 样本，
  确定性种子，每次决策约 20–40ms）；equity ≥ 0.62 价值下注（湿牌面
  3/4 池、干牌面 1/2 池）、听牌按 45% 半诈唬、面对下注按
  equity vs 所需胜率跟注、顶范围一半概率加注。
- **已知简化**（诚实声明）：对手翻后动作不进一步收窄其范围；
  多人池只对 last aggressor 建模。

范围表数据来自公开 GTO 解算器图表的简化近似，后续可替换为自训练
数据。设计文档 §4.1 的 Level 4 即此实现（Level 5 RLBot 仍预留）。

### 4.5 AI 性格参数

```python
@dataclass
class BotPersonality:
    aggression: float        # 攻击性 (0 = passive, 1 = maniac)
    tightness: float         # 松紧度 (0 = 玩任意两张, 1 = 只玩强牌)
    bluff_frequency: float   # 抓诈唬基础频率 (0 = 从不, 1 = 太多)
    use_position: bool       # 是否按位置调整翻前门槛
    use_pot_odds: bool       # 是否按 equity/赔率决策
```

## 5. 情景训练器

### 5.1 训练流程

```
选择场景 → 加载场景 → 呈现决策点 → 你做决策 → 提交 → 评分+反馈 → 下一个决策点
一次训练会话 = N 个决策点，打完看总评
```

### 5.2 场景定义

```python
@dataclass
class Scenario:
    id: str
    title: str
    description: str
    category: ScenarioCategory
    difficulty: int             # 1-5
    game_state: GameState       # 冻结的决策点状态
    player_idx: int             # 你是哪个位置
    optimal_action: Action      # GTO 最优动作
    acceptable_range: dict      # {ActionType: [min_freq, max_freq]}
    analysis: ScenarioAnalysis  # 深度分析数据（预计算）
    hints: list[str]            # 分级提示
```

**场景类别**：翻前范围、翻后 c-bet、价值下注、诈唬、跟注判断、锦标赛特化。

### 5.3 评分系统

总分 = 动作匹配度 (60%) + Sizing 精度 (25%) + 时机判断 (15%)

### 5.4 分层反馈

- **第一层**（即时）：✅/⚠️/❌ + 一句话解释
- **第二层**（展开）：Equity 计算、范围分析、EV 损失等详细面板
- **第三层**（深入）：范围矩阵可视化（前端渲染）

### 5.5 场景生成

- 手动设计场景
- 基于历史弱点自动生成（分析对局记录 → 找 EV 损失最大的场景类型）
- 给定约束随机生成

## 6. 前端设计

### 6.1 路由

```
/                  → Lobby（大厅）
/game/:table_id    → GameTable（牌桌）
/trainer           → Trainer（训练器）
/trainer/:scenario → ScenarioDetail（场景详情）
/history           → History（对局历史）
/history/:hand_id  → HandReplay（对局回放）
```

### 6.2 视觉风格

**青蓝霓虹夜场**（2026-08-09 重设计定稿，详见 `2026-08-09-neon-redesign-design.md`）：

- **牌桌**：胶囊跑道形（长直边 + 半圆端头）——深色宽包边模拟扶手垫 + 内嵌台呢（织物噪点 + 顶部射灯）+ 青色虚线投注环
- **配色**：深底 #05080f + 青色霓虹 #22d3ee 主调；金色 #fbbf24 标记"你"和下注；红桃花色用 #fb7185
- **牌面**：角标式（左上点数+花色，中央大花色），黑花色青辉光、红花色玫红辉光，牌背斜纹
- **座位**：圆形头像（bot 直接显示等级 L1-3），你的位置金色放大，轮到行动有呼吸光环
- **加注**：滑杆（总额语义）+ 动态按钮文案
- **大厅**：发光 ♠ SEKHMET logo、座位占用圆点（青=人、紫=bot）、阶段胶囊

### 6.3 GameTable（牌桌界面）

- 椭圆桌居中，对手环绕，你在底部中央金色高亮
- 公共牌区在桌面中央
- 你的手牌在桌子下方，金色边框突出
- 底部横排动作栏：弃牌 | 过牌 | 跟注 | 加注(含输入框) | 全下 — 带计时器（可关闭）
- 筹码移动动画（下注时筹码飞到池中）

### 6.4 Trainer（训练器界面）

- 分类卡片 + 进度条（各类别完成度 + 平均得分）
- 推荐训练区：基于历史弱点排序
- 最近训练记录

训练决策页面：
- 标准牌桌视图（冻结状态）
- 场景描述 + 局面说明
- 动作选项 + 金额输入
- 可选提示按钮
- 提交后弹出分层反馈面板

### 6.5 移动端适配

椭圆桌缩小为简化版，对手水平排列在顶部。动作按钮垂直堆叠（拇指友好），加注金额用底部抽屉输入。手牌和公共牌大字显示。

## 7. 数据存储

| 数据 | 存储方式 | 说明 |
|------|---------|------|
| 手牌历史 | SQLite → JSON 字段 | 每局完整状态序列（可回溯） |
| 训练进度 | SQLite | 场景ID + 得分 + 时间戳 |
| 用户设置 | SQLite / JSON | 偏好配置 |
| Bot 配置 | Python 代码 / YAML | 范围表、性格参数 |
| 场景库 | YAML + GameState pickle | 预设计 + 自动生成 |
| GTO 范围表 | CSV / binary | 查表用，预计算 |

SQLite 单文件，换 PostgreSQL 只需改连接字符串。

## 8. 非功能需求

- **性能**：AI 决策 < 500ms（规则 bot），< 2s（GTO bot）
- **可扩展**：RL 模型接口预留，Bot 注册机制支持插件式新增
- **部署**：docker-compose up 一键启动
- **安全**：本地使用，无认证系统（后续可加）
