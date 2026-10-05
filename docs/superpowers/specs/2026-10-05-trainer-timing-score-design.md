# Sekhmet — 训练器计时计分 · 设计文档

> 2026-10-05 · 迭代 #3：scorer 的 timing 分量目前硬编码"30s 内满分、60s 衰减到 0"，与题目难度无关（河牌三条街的复杂决策和翻前机械题同一个时钟），玩家也看不到自己的用时与预算。本包把时间预算与难度挂钩，并把用时暴露给前端。

## 1. 背景

- `scorer.score_decision()` 的 timing 段：`elapsed <= 30_000` 满分，之后线性衰减，`90_000` 归零——魔数，不分难度
- 迭代 #1 已把 `time_taken_ms` 落库、`elapsed_ms` 进 API 响应；迭代 #2 之前 `timing_judgment` 权重 0.15 已生效
- 前端提交前后没有任何时间显示，玩家不知道"想太久"被扣了多少

## 2. 范围

**做**：
- `ScoringWeights` 增加时间预算参数：`time_budget_base_s = 20`、`time_budget_per_difficulty_s = 10` → `budget = (20 + difficulty × 10) s`（难度 1 = 30s … 难度 5 = 70s）
- scorer：预算内满分；超预算线性衰减，`2 × budget` 归零（泛化现有逻辑，去掉魔数）
- 秒答（< 1.5s）不扣分，但在 `detailed_feedback` 追加一句"秒答——确认你不是手滑"（防止为保 timing 乱点题）
- `GET /api/trainer/scenarios/{id}` 响应新增 `time_budget_ms`；`submit` 响应已有 `elapsed_ms`
- 前端 `ScenarioDetail`：决策区显示"建议用时 ≤ Ns"；结果页显示"你的用时 X.Xs / 预算 Ns（timing 满分/扣分）"
- 测试：scorer 单测（各难度预算边界、衰减线性、秒答提示）、API 字段、runner 集成

**不做**（明确排除）：
- 全局倒计时强制提交（训练不是真实牌桌，保持无压力作答）
- 历史用时图表（`training_attempts.time_taken_ms` 已落库，留待统计包）

## 3. 实现要点

- 预算公式进 `config.ScoringWeights`（`time_budget_base_s` / `time_budget_per_difficulty_s`），scorer 从 `app_config.scoring` 读取——沿用现有权重配置模式
- `score_decision` 已接收 `time_taken_ms`，只需加 `difficulty` 入参（scenario.difficulty 本来就在调用处）
- 秒答阈值常量 `QUICK_ANSWER_MS = 1500` 放 scorer 模块级
- 前端无新依赖：预算值来自场景详情响应，用时来自提交响应

## 4. 测试与 CI

- `test_trainer.py` scorer 段更新：难度 1 题 29.9s 满分 / 45s 衰减到约一半 / 秒答提示文案；难度 5 题 65s 仍满分（旧实现会扣）
- `test_trainer.py` API：`GET /scenarios/{id}` 带 `time_budget_ms`
- CI 无需改动
