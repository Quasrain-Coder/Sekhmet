# Sekhmet — MTT 锦标赛模式 · 设计文档

> 2026-10-05 · 迭代 #7：全仓库只有固定盲注现金桌；`blind_structure.get_mtt_blinds`/`STANDARD_MTT_STRUCTURE`（15 级，含 ante 字段）自 P1 起就写好但零引用。本包把锦标赛模式接上引擎生命周期：盲注按手数升级、破产淘汰、最后一人获胜。

## 1. 背景

- 现有桌生命周期是现金桌语义：0 筹码 → rebuy 补回，永不结束
- 锦标赛三要素：盲注升级（压力来源）、淘汰（不可回购）、终局（剩一人）
- `GameState` frozen dataclass——升盲注用 `dataclasses.replace` 在发牌前覆写，引擎无感知
- ante 结构表里有字段但引擎发牌不支持 ante——本包忽略 ante（超 15 级封顶在 ante 到来前基本终局），文档注明

## 2. 范围

**做**：
- `TableConfig`：`tournament: bool`、`blind_up_every_hands: int = 8`（按手数计时——无真实时钟依赖，测试友好；线上每手约 1-2 分钟，8 手 ≈ 一级）
- `TableSession`：`blind_level` / `hands_played` / `finished`，`create_table` 透传
- `start_hand`（锦标赛分支）：
  1. 发牌前把 stack≤0 的座位从桌中移除（复用 `_stand_up_locked`）——淘汰
  2. 存活 ≤1 → `finished=True`，广播 `tournament_result`（winner），不再发牌
  3. `hands_played += 1`；非首手且到期 → `blind_level += 1`（封顶 15），`replace` 覆写 state 盲注
- `rebuy`：锦标赛桌直接 `GameError`（不可回购是定义性的）
- `table_info`：`tournament` / `blind_level` / `hands_to_next_level` / `finished` 字段
- 前端：Lobby 建房表单加锦标赛开关（间距默认 8 手）；GameTable 头部显示 `Lv.N · SB/BB · X 手后升级`；`tournament_result` 全屏横幅；锦标赛桌 RebuyPanel 隐藏
- 测试：升级纯函数、淘汰+终局判定、rebuy 拒绝、config 往返、table_info 字段、端到端（小盲注 4 级快速升 + all-in 快进到终局）

**不做**（明确排除）：
- ante 收取（引擎不支持，见上）
- 名次奖励分配/奖品池（个人平台无支付语义；名次 = 淘汰顺序，`eliminated` 已隐含）
- 时间制盲注升级（按手数已闭环；时间制需要后台时钟，收益低）
- 多桌合并/Final Table 重排（单桌 SNG 形态，文档如实命名——"单桌锦标赛"）

## 3. 实现要点

- 升级判定独立纯函数 `_advance_blind_level(session)`：`hands_played > 1 and (hands_played - 1) % interval == 0` → 首手 level 1，第 `interval+1` 手升 level 2
- 盲注覆写：`dataclasses.replace(state, small_blind=…, big_blind=…)` 在 `deal_new_hand` 之前——发牌与盲注扣除读 state 字段，单点覆写全链生效
- 淘汰发生在 start_hand 内（WAITING 相位，无并发风险，但仍走 `session.lock` 与既有路径一致）
- `tournament_result` 消息复用 `_state_broadcast` + 附加 `tournament: {winner_seat, winner_name}`；广播后桌保持可看，sweeper 照常按闲置回收

## 4. 测试与 CI

- `tests/test_tables.py` 增补（锦标赛段）：`_advance_blind_level` 边界（首手/到期/封顶）；破产座位在下一手发牌前被移除；终局 finished+result；rebuy 抛 GameError；`TableConfig.from_dict` 往返新键
- 端到端：max_seats=2、buyin=最小、interval=2，all-in 快进两手看升级、快进到终局看 result
- CI 无需改动
