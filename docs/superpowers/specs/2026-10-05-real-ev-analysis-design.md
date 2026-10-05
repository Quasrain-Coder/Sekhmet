# Sekhmet — 训练器真实 EV 分析 · 设计文档

> 2026-10-05 · 迭代 #2：`trainer/analyzer.py` 的 EV 是"从分数比例反推"的假值（`player_ev = optimal_ev * score/100`，`analyze()` 甚至不接收玩家实际动作）。本包把 `gto_bot` 的蒙特卡洛 equity 机制抽成共享模块，训练反馈改为**现场计算真实 equity 与 EV**，与手写预置值并存（现场算不了才回退手写）。

## 1. 背景

- `analyzer.analyze(scenario, score_total)` 只拿分数：player_ev 是 best_ev × 分数比例的线性插值，没有任何扑克含义
- 场景 `analysis` 字段带作者手写的 `equity_vs_range` / `ev_*`（内置 16 题有，导入题没有）——静态且从未被校准
- `gto_bot._equity_vs_opponent` 已有完整 MC 采样 vs 加权范围，但绑定在 bot 上、且假设 board 完整（postflop 才用）
- 训练反馈要可信，EV 必须从"分数的影子"变成"牌力的函数"

## 2. 范围

**做**：
- 新共享模块 `ai_engine/equity.py`：
  - `equity_vs_combos(hole, board, combos, samples, rng)` — 完整 MC；board 不足 5 张时逐样本补全 runout（preflop 场景可用）；board 完整时我方牌力只评一次（gto_bot 快路径语义）
  - `range_combos()` / `weighted_sample()` / `infer_opponent_range()` / 位置桶逻辑 — 自 `gto_bot` 迁入，gto_bot 改为委托（行为不变，`test_gto_bot` 全绿为准）
- `analyzer.analyze()` 重写：签名加 `player_action`；优先现场 MC（GTOBot 范围推断），算不出时回退作者手写值；结果新增 `equity_source`（`"monte_carlo"` / `"authored"`）与 `assumptions`（模型假设说明）
- EV 模型（单街近似，诚实标注）：
  - `ev_fold = 0`；`ev_check = equity × pot`
  - `ev_call = equity × (pot + to_call) − to_call`
  - `ev_bet/raise(X) = equity × (pot + 2X) − (1 − equity) × X`（对手必跟的保守下界，X=金额，all-in 取 stack）
- `player_ev`：玩家实际动作映射到上述公式；`optimal_ev` = max(0, 各候选动作 EV)；`ev_loss = optimal_ev − player_ev`（可负——玩家打出比"最优"更高的真 EV 时如实展示）
- `scenario_runner.submit` 把玩家动作传入 analyze；API 响应 `analysis` 新增字段（additive，旧字段语义不变）
- 前端 `FeedbackPanel`：equity 行标注数据来源（蒙特卡洛/作者预置），EV 三行保留，`details` 逐行展示
- 测试：`equity.py` 单测（AA 翻前 vs 随机 ≈ 0.85；已知河牌局面与手算一致；快路径与补全路径一致性）、analyzer 单测（MC 路径公式一致性、fold player_ev=0、回退路径）、runner 集成、gto_bot 回归

**不做**（明确排除）：
- 对手范围随街收窄 / 多人池建模（gto_bot 既有简化，属 L4.5 迭代）
- 后续街下注的 EV 树（单街近似已在 `assumptions` 声明）
- 计时计分（迭代 #3）

## 3. 实现要点

- equity 采样数：postflop 沿用 gto_bot 的 200；preflop（需补全 5 张 runout）用 300——实测 600 次完整 runout 评估 0.11s，API 延迟无感
- trainer 拿范围：`infer_opponent_range(frozen_state, player_seat)`；返回 None（无活跃对手）时回退 authored
- 数字口径：EV 单位为"当前底池的筹码"（chips），`details` 文案里注明
- `analyze()` 保持向后兼容：`player_action=None` 时行为等同旧版（分数比例），仅供旧调用方过渡——runner 内部总是传动作

## 4. 测试与 CI

- `tests/test_equity.py`：AA vs 随机双手翻前 equity 落在 0.80–0.89；河牌一对 A vs 单张高牌组合 = 1.0/0.0 边界；board 完整时与逐样本补全路径结果一致（同 rng）；无有效组合返回 None
- `tests/test_trainer.py` 补 analyzer 相关断言迁移/更新；`tests/test_trainer_stats.py` 不受影响（score 形状不变）
- CI 无需改动
