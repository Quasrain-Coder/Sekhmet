# Sekhmet — 排行榜 / 自定义选座 / 下一局开关 + 头像挡牌修复 · 设计文档

> 2026-08-09 · 三个小功能 + 一个视觉回归修复

## 1. 背景

- **Bug（视觉回归）**：霓虹重设计后，底部"我"的座位（金色头像 + 名字 + 筹码 + 放大的手牌）总高约 150px，锚定在 `bottom: 5%` 使内容向上生长，头像正好压到 52% 处的公共牌区——头像挡牌。
- 三个功能需求：房间内排行榜、入座时自定义选座、摊牌后显式"下一局"开关。

## 2. Bug 修复：头像挡牌

- 根因：`.seat-0` 用 `bottom: 5%` 锚定，flex 列内容向上撑高，侵入公共牌区。
- 修法：我的手牌（`.player-seat.me .cards`）改为绝对定位挂在座位盒**下沿之外**（`position: absolute; top: 100%; left: 50%; transform: translateX(-50%)`），不再撑高座位盒；头像留在桌沿，手牌压桌沿的视觉效果保留。
- 约束：不破坏 seat-wrap 锚定机制（PR #10、#12 两轮修复的不变量：wrap 持 seat-N 绝对定位，内层 player-seat 非 absolute）。

## 3. LeaderBoard（内存版）

### 3.1 数据

`TableSession` 新增：

```python
stats: dict[int, PlayerStats]  # seat_idx → stats
total_buyin: dict[int, int]    # seat_idx → 累计买入（算净盈亏用）

@dataclass
class PlayerStats:
    hands: int = 0
    wins: int = 0
```

- `start_hand`：所有在座玩家 `hands += 1`
- `_resolve_showdown`：每个 PotAward 的赢家 `wins += 1`（分池多人各记一胜）
- 净盈亏 = 当前 stack − total_buyin（前端计算或后端算好随广播发出——定为后端算好）
- `stand_up`：清理 stats/total_buyin 条目

### 3.2 协议

`table_state` 与 `table_info` 的 `seats` 明细增加三个字段：`hands`、`wins`、`net_chips`。无新消息类型。

### 3.3 展示

牌桌页加可折叠排行榜面板（默认折叠）：标题栏 "🏆 Leaderboard" 点击展开，按净盈亏降序，列：名次、名字（bot 带等级）、手数、胜场、胜率、净盈亏（正金负灰）。样式随霓虹主题。

### 3.4 持久化预留

统计以玩家名字语义呈现，将来落 SQLite（models/ 层，P6）时前端无感。本迭代不动数据库。

## 4. 自定义选座

- 入座确认页加入**选座示意图**：座位点按弧形排列（CSS transform rotate/translate 围半圆，或简化为 flex 弧行），编号 0..max_seats-1：
  - 已占：显示名字缩写，不可点
  - 空位：可点，hover 霓虹提亮，选中金色高亮
- 未选座位时"入座"按钮禁用（或默认选中第一个空位——定为**默认选中第一个空位**，用户可改点别的）
- 后端零改动（sit_down 已支持任意 seat_idx）

## 5. 摊牌后"下一局"开关

- 摊牌结果面板（`.hand-result`）底部加金色大按钮 **"Next Hand"**，仅 `phase === 'SHOWDOWN'` 时渲染，点击发送 `start_hand`
- 页头 Deal 按钮保留（开第一手用）；SHOWDOWN 后面板按钮是主路径

## 6. 实现要点

- 后端仅 `table_manager.py`（stats 追踪 + table_info 字段）+ 测试；无协议破坏性变更（seats 明细加字段是兼容的）
- 前端：GameTable.tsx（排行榜面板 + Next Hand 按钮 + 确认页选座图）、PlayerSeat/CSS（bug 修复）
- 无新依赖、无路由变更

## 7. 测试与验收

- 后端新测试：stats 随手牌累计（hands/wins/net_chips 经 table_info 正确暴露）；stand_up 清理；分池多赢家各记胜场
- 既有 184 测试保持绿（seats 加字段不破坏旧断言——e2e 旅程测试里有 seats 全等断言，需同步更新）
- 前端 build + oxlint 绿
- 人工验收：头像不再挡公共牌、我的手牌压桌沿、排行榜展开/折叠、确认页点选座位、摊牌后 Next Hand
- CI 无需改动（tests/ 自动收集）
