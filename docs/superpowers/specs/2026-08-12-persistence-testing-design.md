# Sekhmet — 包 D：持久化地基与前端测试/CI · 设计文档

> 2026-08-12 · models/ SQLite 持久化（对局记录 + 玩家战绩）+ vitest 前端测试设施 + 前端 CI job

## 1. 背景

- 无任何持久化：房间销毁即数据全灭（排行榜内存版、对局无记录）。`sqlalchemy>=2.0` 和 `aiosqlite` 早已在依赖里但从未使用；`config.database_url` 也已就位
- 前端零测试设施（无 vitest），CI 只跑后端——三次重设计全靠肉眼验收

## 2. 持久化（models/ 层）

### 2.1 表结构

```python
class HandRecord(Base):
    id: int (PK, autoincrement)
    table_id: str (index)
    players: str    # JSON: [{seat_idx, name, is_human, stack_before, stack_after}]
    board: str      # JSON: ["A♠", ...]（最终牌面，fold-out 可能不足 5 张）
    actions: str    # JSON: round_history [{seat, action, amount}]
    awards: str     # JSON: [{seat_idx, amount, hand}]
    created_at: datetime (UTC)

class PlayerStatsRecord(Base):
    name: str (PK)          # 仅人类玩家（bot 名字不入库）
    hands: int
    wins: int
    net_chips: int
    updated_at: datetime (UTC)
```

### 2.2 写入时机与可靠性

- `_resolve_showdown` 结算完成后**异步落库**（fire-and-forget task；异常仅 logger.exception，绝不影响牌局）
- 每手一条 HandRecord；每名人类玩家 upsert 累计 PlayerStatsRecord（hands/wins/net_chips 累加）
- 建表：lifespan startup 执行 `create_all`（与现有 sweeper 合并在一个 lifespan 里）；不用 Alembic（两张表，YAGNI）

### 2.3 查询 REST

- `GET /api/history/hands?limit=20&table_id=<可选>`——按时间倒序
- `GET /api/history/players`——按 net_chips 降序的全局战绩
- 前端页面不在本包范围（回放/历史页另行立项）；REST 先行解锁数据闭环

## 3. 前端测试设施 + CI

- 依赖（devDependencies）：`vitest`、`jsdom`、`@testing-library/react`、`@testing-library/jest-dom`（本地 npm install 加 `--registry=https://registry.npmmirror.com`；CI 用默认源）
- `vite.config.ts` 加 `test: { environment: 'jsdom', globals: true }`
- 首批组件测试（`frontend/src/__tests__/`）：
  - `Toast.test.tsx`：渲染 error/info、3.5s 自动消失（fake timers）、点击关闭
  - `Leaderboard.test.tsx`：按 net_chips 降序、折叠/展开
  - `CardView.test.tsx`：角标渲染 rank+suit、红花色 card-red / 黑花色 card-black、牌背
- CI 新增 `frontend` job（与 backend test 并列）：checkout → setup-node 22（cache npm）→ `npm ci` → `npx oxlint src` → `npm run build` → `npx vitest run`

## 4. 实现要点

- 新增 `backend/sekhmet/models/`：`db.py`（engine/session 工厂、init_db）、`records.py`（两张表 ORM）、`recorder.py`（record_hand + upsert_stats 的 fire-and-forget 封装）
- `table_manager._resolve_showdown` 末尾调 recorder（传入结算前后的数据快照）
- `api/history.py` 新路由；`main.py` 挂载 + lifespan 合并 init_db
- **CI 记忆纪律**：新增模块必须同步 CI——本包同时改后端 pytest（tests/ 自动收集，无需改）和新增 frontend job
- 测试用内存 SQLite（`sqlite+aiosqlite:///:memory:`）隔离

## 5. 测试

- recorder：一手牌结束后 HandRecord 落库（players/board/actions/awards 字段完整）、PlayerStatsRecord 累计正确、bot 不入库、落库异常不影响结算
- REST：hands 列表倒序/limit/table_id 过滤；players 降序
- 前端：3 个组件测试文件全绿
- 既有 224 后端测试保持绿
