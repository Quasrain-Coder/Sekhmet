# Sekhmet — 玩家 HUD 对手数据上屏 · 设计文档

> 2026-10-05 · 迭代 #4：`OpponentStatsTracker`（VPIP/PFR/fold-to-bet，Laplace 平滑）早已在桌会话上跨手累积，且人类与 bot 的动作都被记录——但只有 bot 读它。真人玩家看不到任何对手倾向数据。本包把每座位的统计随 `game_state_update` 广播，牌桌座位卡上显示 HUD。

## 1. 背景

- `session.tracker: OpponentStatsTracker`：`observe()` 在人类动作（table_manager:887）与 bot 动作（:800）后都被调用；`new_hand()` 按发牌座位计手数
- 数据是**公开行为统计**（任何人盯着桌面都能手工记出来）——放进公共广播无信息泄露
- 前端 `PlayerSeat` 已有 name/stack/bet 行，HUD 是纯追加展示

## 2. 范围

**做**：
- `_state_broadcast()` 的每个 player 条目新增 `hud` 字段：`{hands, vpip_pct, pfr_pct, fold_to_bet_pct} | null`（座位从未上过牌桌统计 → `null`）
- 数值口径：`rate() × 100` 取整（Laplace 平滑后的值）；前端在 `hands < 5` 时淡显并标注样本少（平滑值在小样本下有意义的粗估）
- 前端：`PlayerInfo` 加 `hud` 可选字段；`PlayerSeat` 在 stack 下方渲染 `VPIP 45 · PFR 20`（自己的座位不显示）；样式 `.hud-line` 小字淡色
- 测试：广播含 hud（有数据/无数据字段为 null/离座清空后为 null）；前端 PlayerSeat 三态渲染 + isMe 隐藏

**不做**（明确排除）：
- HUD 历史趋势、按位置拆分（样本量不足，误导）
- fold-to-bet 上屏（`faced_bets` 样本通常 <10，展示噪声大于信息——字段照发，界面暂不渲染）
- 离线账户级 HUD（`user_stats` 的 VPIP 是跨桌生涯值，语义不同）

## 3. 实现要点

- 广播是全量玩家列表重建，hud 直接内联进 player dict——消息体积 +约 40B/座位，无新消息类型，前端零协议改动（可选字段）
- 离座清理（`tracker.stats.pop`）已有，广播自然回落为 `null`
- `hand_start` 不带 hud：开局瞬间上一手的 scratch 尚未 fold-in，数字会闪旧值；`game_state_update` 在动作后必达，HUD 每步都是新的

## 4. 测试与 CI

- 后端 `test_tables.py`：构造有动作历史的会话 → `_state_broadcast` 里对手座位 hud.vpip_pct 合理；无数据座位 hud 为 null
- 前端 `PlayerSeat.test`（并入现有 TableAnimations 或新建）：有数据显示行、hands<5 淡显、null 不渲染、isMe 不渲染
- CI 无需改动
