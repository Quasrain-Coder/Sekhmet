# Sekhmet — 包 A：规则与牌局完整性 · 设计文档

> 2026-08-10 · 死盲注修正 / all-in runout 分街可视 / 位置标记（D·SB·BB）

## 1. 背景

- **死盲注**：上一轮"爆掉坐观"功能让 0 筹码玩家跳过发牌，但盲注座位仍按座位号分配——爆掉玩家持盲注位时盲注收不到，而 `current_bet` 仍是大盲，其他人要跟一个没人缴纳的"幽灵盲注"。
- **runout 一闪而过**（用户报告）：两家 all-in 后引擎原子地把剩余公共牌发完并直进 SHOWDOWN，玩家看到的是"直接出结果"，看不到翻/转/河一张张发出。
- **位置不可见**（用户报告）：座位上不显示 Dealer/SB/BB 标记。

## 2. 死盲注修正

- 盲注分配给**按钮位之后有筹码的玩家**（按座位顺时针）：SB = 按钮后第一个 `stack>0` 的座位，BB = SB 之后第一个 `stack>0` 的座位；两人时按 HU 规则（按钮=SB；按钮爆掉则按钮后第一个有筹码者为 SB）
- 按钮旋转逻辑不变（仍按全部入座座位轮转，允许"死按钮"）
- 效果：盲注永远真实缴纳，底池=SB+BB；`deal_new_hand` 的坐观跳过逻辑（0 筹码不发牌）保持不变
- 既有测试 `test_deal_skips_zero_stack_player` 的断言需从"死盲注 pot=10"更新为"SB 顺延 pot=15"

## 3. All-in runout 分街发出

### 3.1 引擎改为逐街推进

- `_advance`：回合关闭且可行动玩家 ≤1 时，从"原子 runout 到底"改为**只推进一条街**（复用 `_advance_phase`）
- `_advance_phase`：若新街可行动玩家 ≤1（无人能再下注），`current_player_idx=None`——表示"等待 runout 继续"
- 新增公开 `runout_step(state) -> GameState`（推进一步），供桌层循环调用；原子 `_runout` 删除
- 语义保持不变：无人能响应时不再给任何"假回合"（单人剩筹也不再被询问）

### 3.2 桌层逐街广播

- `auto_bot_actions` 循环内：`current_player_idx is None` 且仍在下注阶段 → 调 `runout_step` 推进一条街、广播、**停顿 `runout_delay_seconds`（默认 0.8s，GameConfig 新增，测试置 0）**，继续直到 SHOWDOWN 后按现有路径结算
- 所有触发路径（人类动作、bot 动作、超时、宽限强制弃牌）已统一走 `after_action → auto_bot_actions`，单点生效
- 观众看到：翻牌 →（0.8s）→ 转牌 →（0.8s）→ 河牌 →（0.8s）→ 摊牌结果

### 3.3 既有测试适配

- `test_full_hand.py` 三个 runout 测试：从"call 完直接 SHOWDOWN"改为"逐步 runout_step 到 SHOWDOWN，每街牌数 3/4/5"
- `test_action_processor.py::test_players_all_in_goes_to_showdown`：断言改为"推进一条街且无人可行动"
- 桌层 runout 延迟测试：monkeypatch `runout_delay_seconds=0`

## 4. 位置标记（D / SB / BB）

- 后端：`_state_broadcast` 与 `_hand_start_broadcast` 增加 `sb_seat`、`bb_seat`（`dealer_idx` 已有）
- 前端：座位头像旁显示位置徽章——`D`（金色）、`SB`/`BB`（青色小胶囊）；数据直接读广播字段，不做前端推算
- WAITING/SHOWDOWN 阶段无盲注位，徽章仅在下注阶段显示

## 5. 实现要点

- 引擎：`action_processor.py`（盲注分配、逐街 runout、公开 runout_step）
- 桌层：`table_manager.py`（auto_bot_actions runout 分支、广播字段）、`config.py`（runout_delay_seconds）
- 前端：`OvalTable.tsx`/`PlayerSeat.tsx`（位置徽章）、reducer 存 sb/bb_seat
- 无协议破坏性变更（加字段）

## 6. 测试

- 引擎：盲注顺延（SB/BB 落到有筹码者、pot 正确、first_to_act 正确）；逐街 runout（每街牌数、最终 SHOWDOWN、筹码守恒）
- 桌层：all-in 后逐街广播（延迟置 0）；广播消息含 sb_seat/bb_seat
- 既有 204 测试适配后保持绿
- 前端 build + oxlint
