# Sekhmet — 训练成绩落库 · 设计文档

> 2026-10-05 · 迭代 #1：训练器的分数目前只存浏览器 localStorage（`trainerScores`，上限 100 条纯数字），换设备/清缓存即丢，且无错题本、无分类弱点分析。本包把每次训练决策落库，并解锁三个读取视图：进步曲线（服务端）、分类统计、错题本。

## 1. 背景

- `/api/trainer/scenarios/{id}/submit` 纯无状态：算分即返回，不落任何数据
- 前端 `ScoreChart.tsx` 从 localStorage 读 `trainerScores`（`ScenarioDetail` 提交后 push），仅本机可见
- 与对局战绩（`UserStatsRecord` / `HandRecord`）不同，训练行为没有任何账号维度沉淀
- 访客（未登录）与登录用户的边界沿用现有约定：**访客行为不计入任何持久化统计**

## 2. 范围

**做**：
- 新表 `training_attempts`：一行 = 一次提交的评分决策（user_id / scenario_id / category / difficulty / action JSON / score 四维 / is_optimal / hints_used / time_taken_ms / created_at）
- `POST /api/trainer/scenarios/{id}/submit` 接受可选 `token` 与 `hints_used`：token 有效且账号存在才落库；无效 token 不报错、照常返回评分（访客可继续训练）
- 新端点（均需有效 token，否则 401）：
  - `GET /api/trainer/stats` — 总览（总题数 / 均分 / 最优率）+ 分类明细（每类题数 / 均分 / 最优率）+ 最近记录（进步曲线数据源，上限 50 条）
  - `GET /api/trainer/mistakes` — 错题本：按 scenario 取**最近一次**尝试，最近一次非最优的题才入选（做过后期改对了就出列），附题库内标题
- 前端：
  - `ScenarioDetail` 提交时带上 `token` 与 `hints_used`
  - `ScoreChart` 登录态改读服务端 `stats.recent`（无 token / 请求失败回退 localStorage，访客行为不变）
  - `Trainer` 页新增"训练统计"卡（总览 + 分类弱点条）与"错题本"区（点击直接跳转该题重训）
- 测试：`tests/test_trainer_stats.py`（落库条件 / 聚合 / 错题进出列 / 401）

**不做**（明确排除）：
- 计时计分启用（`timing_judgment` 权重仍挂空，落库先存 `time_taken_ms` 原始值，迭代 #3 再启用）
- 真实 EV 分析（迭代 #2）
- 跨设备实时同步、删除/重置成绩、全局排行榜

## 3. 实现要点

- 新 ORM 模型 `TrainingAttemptRecord` 放 `models/records.py`（与现有表同文件）；`create_all` 自动建表，老库无需迁移（纯新增表）
- 查询辅助函数放 `records.py`：`attempts_recent()` / `category_breakdown()` / `mistake_scenarios()`——SQLAlchemy select，聚合在 Python 侧完成（SQLite 单机、数据量小，不值得引入 SQL 聚合复杂度）
- 落库直接 `await` 在 submit 端点内（try/except 包裹，失败只记日志不影响返回）——训练提交低频，无需 `recorder.schedule_recording` 的 fire-and-forget
- 错题本"最近一次非最优"语义：按 scenario_id 分组取 max(id) 的那条，`is_optimal = False` 才保留；标题从进程内 `_library` 查，查不到回退 scenario_id
- 前端 localStorage 写入保留（访客曲线来源 + 服务端故障回退），登录用户以服务端为准

## 4. 测试与 CI

- `test_trainer_stats.py`：注册→提交→库里有行（字段正确）；无效 token 提交不落库；stats 聚合数字（均分/最优率/分类计数）；错题本先出后消失（改对即出列）；stats/mistakes 无效 token → 401
- CI 无需改动：coverage 目标是整个 `sekhmet` 包，新表/新端点自动纳入
