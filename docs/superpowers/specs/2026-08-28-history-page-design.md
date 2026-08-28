# Sekhmet — History 对局历史页 · 设计文档

> 2026-08-28 · P6 第一项：包 D（`2026-08-12-persistence-testing-design.md`）预留的前端页面立项——"前端页面不在本包范围（回放/历史页另行立项）；REST 先行解锁数据闭环"。本包只做**列表页**；逐手回放（HandReplay）下一包实现。

## 1. 背景

- 包 D 已落地：`HandRecord` 逐手落库 + `UserStatsRecord` 累计战绩 + REST（`GET /api/history/hands`、`GET /api/history/players`）
- 数据闭环只通了"写"，用户无法"读"——本包补上读取界面

## 2. 范围

**做**：
- 新路由 `/history` → `History` 页（`frontend/src/pages/History.tsx`）
- 页面两区：
  1. **玩家战绩榜**：`/api/history/players` 按 net_chips 降序（服务端已排序），列为 排名 / 玩家 / 手数 / 胜场 / 胜率 / 净盈亏
  2. **最近对局**：`/api/history/hands?limit=50`，每手一张卡片——`#id · table_id · 时间`，公共牌用现有 `CardView small` 渲染，各座位净盈亏（`stack_after - stack_before`，正金负红），赢家（awards 中出现的 seat_idx）加 🏆；点击卡片展开/收起动作序列（座位名 + 动作 + 金额）
- Lobby 入口：Trainer 面板加 "📜 对局历史" 按钮
- 测试：`__tests__/History.test.tsx`（vitest，stub fetch）

**不做**（明确排除）：
- 逐手可视化回放（下一包，路由 `/history/:hand_id`，见主设计文档 6.1）
- 分页/筛选 UI（REST 已支持 `table_id` 参数，界面暂不接）
- 后端改动（REST 契约不变）

## 3. 实现要点

- 纯前端：不改任何后端文件；REST 响应形状以 `api/history.py` 为准
- 视觉沿用青蓝霓虹主题变量（`--cyan` / `--gold` / `--rose`），新增类加 `history-` 前缀（`.hand-card` / `.net-pos` / `.net-neg` 等），避免与牌桌侧栏已有的 `.history` 类冲突
- 净盈亏着色约定与 Lobby 战绩条一致：正 = 金（`var(--gold-text)`），负 = 红（`var(--rose)`）
- 赢家判定：`awards[].seat_idx` 集合（分池时可能多人）
- 卡片展开动作流水是回放页的低成本过渡；回放页上线后卡片改为跳转转 `/history/:hand_id`

## 4. 测试与 CI

- `History.test.tsx`：玩家榜渲染与排序、手牌卡片（公共牌张数 / 净盈亏着色 / 赢家标记）、空数据态、点击展开动作列表
- CI 无需改动：frontend job 的 `npx vitest run` 自动收集新测试（遵守 CI 记忆纪律，已确认覆盖）
