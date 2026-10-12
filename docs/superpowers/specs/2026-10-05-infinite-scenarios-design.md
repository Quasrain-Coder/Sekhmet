# Sekhmet — 训练器无限出题 · 设计文档

> 2026-10-05 · 迭代 #5：题库是静态物化的 516 题（`bulk_generator` 预生成到磁盘）+ 16 内置，玩家刷两遍就背熟了答案。而 `bulk_generator` 内部本来就是"模板 + 随机发牌 + GTOBot 定参考动作 + 质量过滤"的完整生成机制——本包把它挂到运行时：每次请求现场出一道新题，永不重复。

## 1. 背景

- 设计文档 §5.5 的"给定约束随机生成"第三来源：CLI 批量生成已落地（#83），运行时生成缺失
- 生成机制现成：`_TEMPLATES`（15 个模板）→ `tpl.build(rng)` 出 spec → `_scenario_for()` 质量过滤（参考动作合法性 / 板面谓词 / 最优解满分 / 非平凡性）→ `Scenario`
- 迭代 #2 的真实 EV 分析对带 frozen_state 的场景自动走 MC——现场生成的题天然享受，无需预置 analysis

## 2. 范围

**做**：
- `bulk_generator.generate_one(rng, category, max_attempts=800)`：随机选模板（可按 category 过滤）循环 build+过滤直到出一道合格题；多次失败返回 None
- `GET /api/trainer/random?category=`：现场生成，id 改写为 `rand-<8hex>`（与磁盘 `gen-XXXX` 永不冲突），`_library.add()` 进进程内库，返回与 `GET /scenarios/{id}` 同形状（含 table 预览 + 计时起点）
- 未知 category → 400；生成失败（模板滤网极严时理论上可能）→ 503
- 前端 Trainer 页：分类过滤行加"🎲 随机一题"——按当前分类生成并跳转；ScenarioDetail 无感知（就是普通场景）
- 随机题与磁盘题同池参与错题本/统计（category/difficulty 照常落库）
- 测试：generate_one 合格性与 category 过滤、API 端到端（random → get → submit）、未知 category 400

**不做**（明确排除）：
- 现场生成的题持久化到磁盘（进程内存活即可——流式练习本就无需收藏；错题本里点击已重启丢失的 rand 题会 404，前端提示"该题已过期，重新随机一题"即可，属可接受折衷）
- 难度定向生成（模板自带难度，随机已覆盖 1–4）
- 限制重复牌型（概率极低且无伤大雅）

## 3. 实现要点

- `_scenario_for(spec, tpl, idx)` 原样复用；idx 仅影响 id，API 层统一改写
- 计时起点：random 端点返回前调用 `_runner.start(id)`，与 get_scenario 语义一致
- 生成在请求线程同步执行——单题 build+过滤通常 <10ms，极端模板重试几百次也在 1s 内；不加后台任务
- 前端按钮失败态：503 时 toast"生成失败，再试一次"

## 4. 测试与 CI

- 后端 `tests/test_trainer.py` 增补：`generate_one()` 三例（默认/过滤/耗尽）；`test_trainer_random_endpoint` 端到端
- 前端并入 TrainerStats.test（点按钮 → fetch random → 跳转）
- CI 无需改动
