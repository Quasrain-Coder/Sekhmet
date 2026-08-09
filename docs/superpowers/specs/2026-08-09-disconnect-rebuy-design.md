# Sekhmet — 断线宽限重连 / 行动超时 / 爆掉重买 · 设计文档

> 2026-08-09 · 自动退出机制（含短断线容忍）+ 局内 buyin（仅爆掉可重买）

## 1. 背景与目标

现状：

- ws 断连立即 `stand_up`——短暂闪断就掉局；手牌中断连还会把玩家从 `game_state.players` 里抽走，可能卡死手牌（此前记录为已知限制）
- 无行动超时——玩家不动则手牌永远停住
- 无局内 buyin——爆掉（0 筹码）的玩家只能离座重进，丢失房间内 stats

目标：断线宽限 + 按名重连认领、行动超时自动 check/fold、宽限期满安全移除、爆掉重买。

非目标：连着但不动的玩家不踢（仅自动 check/fold）；无认证体系（按名字认领即可，本地/朋友圈场景）；不改引擎协议语义外的部分。

## 2. 断线宽限与重连认领

### 2.1 状态与配置

- `GameConfig` 新增 `disconnect_grace_seconds: int = 60`
- `TableSession` 新增 `disconnected: set[int]`（掉线座位集合）

### 2.2 断连流程

ws 断连时**不再立即 stand_up**：

1. 座位加入 `disconnected`，广播 table_state（seats 明细新增 `connected: bool`，全桌可见"X 掉线"）
2. 启动 60s 宽限计时（asyncio task 存 session）
3. 宽限期满 → 移除（§4）；期间重连认领 → 取消计时

### 2.3 重连认领

`sit_down` 时若 `name` 匹配某个 `disconnected` 座位：

- 认领该座位（忽略请求里的 seat_idx）：`clients[seat] = 新连接`、`my_seat = seat`、清 `disconnected` 标记、取消宽限计时
- 若在手牌中且该座位有底牌：补发私有 `hole_cards` 消息 + 当前 `game_state_update`
- 广播 table_state

名字不匹配任何掉线座位 → 走正常入座（含 mid-hand 拒绝等现有规则）。

## 3. 行动超时

- `config.action_timeout_seconds`（现有字段，默认 30）首次启用
- 轮到**人类**玩家行动时启动计时（bot 即时行动不需要）；到期自动执行：无注 CHECK、有注 FOLD，走正常 `execute` + 广播 + bot 驱动链路
- 任何动作执行后取消旧计时、按新 current_player 重新评估是否启动
- 手牌结束（SHOWDOWN）/ 离座 / 房间销毁时取消计时
- 掉线玩家的回合同样受此约束——手牌不会因掉线卡死

实现：`TableSession` 持 `action_timer: asyncio.Task | None`；table_manager 加 `_schedule_action_timeout(session)`，在 `handle_player_action` / `auto_bot_actions` / `start_hand` 的状态推进点后调用。

## 4. 宽限期满的移除

- **手牌间隙**（WAITING/SHOWDOWN）：直接 `stand_up`
- **手牌中**：
  - 轮到该玩家 → `execute(FOLD)`
  - 不轮到他 → 标记 `is_active=False`（引擎的回合推进天然跳过非活跃玩家；其已投入筹码留在池中，符合扑克规则）
  - 立即从 `player_names`/`stats`/`total_buyin`/`bot_levels` 移除；弃牌的"壳"留在 players 元组里直到手牌结束（folded 玩家是惰性的）
- `start_hand` 发牌前 purge：`players = [p for p in players if p.seat_idx in player_names]`，防止壳被重新发牌

## 5. 爆掉重买（仅 0 筹码）

### 5.1 协议

新 ws 消息：`{"type": "rebuy", "amount": int}`

校验（失败回 error）：

- 已入座（my_seat）
- 手牌间隙（WAITING/SHOWDOWN）
- 当前 `stack == 0`（仅爆掉可重买）
- `20 × big_blind <= amount <= 200 × big_blind`

### 5.2 效果

- `stack += amount`（with_players 生成新 Player）
- `total_buyin[seat] += amount`——排行榜净盈亏自动保持正确
- 广播 table_state

### 5.3 配套：0 筹码玩家不再被发牌

`deal_new_hand` 对 `stack == 0` 的玩家跳过发牌（不底牌、不盲注、保持 `is_active=False`）；人数检查改为"stack>0 的玩家 ≥ 2"。重买后下一手自动回到牌局。

### 5.4 前端

- 我的 stack == 0 且手牌间隙 → 显示 Rebuy 面板（金额输入，默认 default_buyin，提交 `rebuy` 消息）
- 座位头像/排行榜可对 0 筹码玩家显示"OUT"角标（视觉小事，从简：排行榜 stack 列自然显示 0）

## 6. 实现要点

- 后端：`table_manager.py`（宽限/重连/超时/移除/rebuy/purge）+ `ws.py`（rebuy 消息、断连改宽限、sit_down 认领分支）+ `config.py`（grace 配置）+ `game_engine/action_processor.py`（deal_new_hand 跳过 0 筹码）
- 前端：`GameTable.tsx`（Rebuy 面板）+ `useGameState.ts`（SeatInfo + connected）+ 样式
- 计时器全部存 session，房间销毁时统一取消

## 7. 测试

后端（TDD，全程 pytest-asyncio）：

- 断连 → 座位保留且 connected=false；宽限期内同名 sit_down → 认领成功（恢复原座位，my_seat 正确）
- 宽限期满（测试用极短 grace）→ 局间直接移除
- 宽限期满且手牌中（轮到掉线者）→ 自动 FOLD，手牌继续
- 行动超时（极短 timeout）→ 自动 CHECK/FOLD 广播
- rebuy：stack>0 拒绝、局中拒绝、越限拒绝、爆掉后成功（stack/total_buyin 更新、广播）
- 0 筹码玩家不被发牌；重买后下一手回到牌局
- 既有 189 测试保持绿

前端：build + oxlint。CI 无需改动。
