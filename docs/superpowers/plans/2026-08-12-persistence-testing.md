# 包 D：持久化地基与前端测试/CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** models/ SQLite 持久化（对局记录 + 玩家战绩 + 查询 REST）与前端测试设施（vitest + 组件测试 + CI 前端 job）。

**Architecture:** 新增 `backend/sekhmet/models/`（db/records/recorder 三模块），`_resolve_showdown` 结算后 fire-and-forget 落库；前端 vitest + testing-library，CI 加 frontend job。

**Tech Stack:** SQLAlchemy 2.0 async + aiosqlite（已在依赖）；vitest + jsdom + @testing-library/react。

**Spec:** `docs/superpowers/specs/2026-08-12-persistence-testing-design.md`

## Global Constraints

- 工作分支 `feat/persistence-testing`（spec 已提交）；禁止直接提交 main
- 后端测试：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`（当前 224 passed）
- 前端门禁：`cd frontend && npm run build && npx oxlint src` 绿
- 本地 npm install 必须加 `--registry=https://registry.npmmirror.com`；CI 用默认源
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- TDD：先写失败测试，看红，再实现
- **CI 纪律**（历史教训）：本包新增 models/ 模块 + 前端测试，CI 必须同步（后端 tests/ 自动收集无需改；前端新增 job）
- 落库失败绝不影响牌局（fire-and-forget + logger.exception）

---

### Task 1: 后端 — models/ 层（db / records / recorder）

**Files:**
- Create: `backend/sekhmet/models/__init__.py`、`db.py`、`records.py`、`recorder.py`
- Test: `backend/tests/test_models.py`（新建）

**Interfaces:**
- Produces:
  - `models.db`: `Base`、`engine`、`SessionLocal`（async_sessionmaker）、`configure(url: str)`（测试用，重建 engine/SessionLocal）、`init_db()`
  - `models.records`: `HandRecord`、`PlayerStatsRecord`
  - `models.recorder`: `async def record_hand(table_id, players_meta, board, actions, awards) -> None`、`async def upsert_player_stats(deltas: list[dict]) -> None`、`def schedule_recording(...) -> None`（fire-and-forget 包装，异常仅 logger.exception）

- [x] **Step 1: 写失败测试**（新建 backend/tests/test_models.py）

```python
"""Tests for the models/ persistence layer."""

import pytest
from sekhmet.models import db, records, recorder


@pytest.fixture
async def mem_db(tmp_path):
    """File-backed SQLite per test (in-memory aiosqlite is per-connection)."""
    db.configure(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await db.init_db()
    yield
    await db.engine.dispose()


async def test_record_hand_persists(mem_db):
    await recorder.record_hand(
        table_id="abc12345",
        players_meta=[
            {"seat_idx": 0, "name": "Hero", "is_human": True, "stack_before": 200, "stack_after": 215},
            {"seat_idx": 1, "name": "Bot L2", "is_human": False, "stack_before": 200, "stack_after": 185},
        ],
        board=["A♠", "K♥", "10♦", "2♣", "7♠"],
        actions=[{"seat": 0, "action": "CALL", "amount": 5}],
        awards=[{"seat_idx": 0, "amount": 15, "hand": "High Card, Ace"}],
    )
    async with db.SessionLocal() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(records.HandRecord))).scalars().all()
    assert len(rows) == 1
    r = rows[0]
    assert r.table_id == "abc12345"
    import json
    assert json.loads(r.board) == ["A♠", "K♥", "10♦", "2♣", "7♠"]
    assert json.loads(r.awards)[0]["seat_idx"] == 0


async def test_upsert_player_stats_accumulates_humans_only(mem_db):
    deltas = [
        {"name": "Hero", "is_human": True, "won": True, "delta": 15},
        {"name": "Bot L2", "is_human": False, "won": False, "delta": -15},
    ]
    await recorder.upsert_player_stats(deltas)
    await recorder.upsert_player_stats([{"name": "Hero", "is_human": True, "won": False, "delta": -10}])
    async with db.SessionLocal() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(records.PlayerStatsRecord))).scalars().all()
    assert len(rows) == 1  # bot 不入库
    hero = rows[0]
    assert hero.hands == 2 and hero.wins == 1 and hero.net_chips == 5


async def test_recording_failure_does_not_raise(mem_db):
    """落库异常只记日志，不向上抛。"""
    await db.engine.dispose()  # 弄坏 engine
    await recorder.record_hand("t", [], "[]", "[]", "[]")  # 不应抛出
```

（第三个测试要求 record_hand 内部容错——fire-and-forget 包装外的直接调用也不应抛出。实现时让 record_hand 自己 try/except，schedule_recording 只是 create_task 包装。）

- [x] **Step 2: 确认红**（ModuleNotFoundError: sekhmet.models）

- [x] **Step 3: 实现**

`models/__init__.py`：空文件。

`models/db.py`：

```python
"""Async database engine and session factory (SQLite via aiosqlite)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..config import app_config


class Base(DeclarativeBase):
    pass


engine = create_async_engine(app_config.database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def configure(url: str) -> None:
    """Rebuild engine/session factory — used by tests to point at a temp DB."""
    global engine, SessionLocal
    engine = create_async_engine(url)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from . import records  # noqa: F401 — register models on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

`models/records.py`：

```python
"""ORM models for hand history and persistent player stats."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HandRecord(Base):
    __tablename__ = "hand_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_id: Mapped[str] = mapped_column(String(16), index=True)
    players: Mapped[str] = mapped_column(Text)   # JSON array
    board: Mapped[str] = mapped_column(Text)     # JSON array of card strings
    actions: Mapped[str] = mapped_column(Text)   # JSON array
    awards: Mapped[str] = mapped_column(Text)    # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PlayerStatsRecord(Base):
    __tablename__ = "player_stats"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    hands: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    net_chips: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
```

`models/recorder.py`：

```python
"""Fire-and-forget persistence for completed hands."""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from .db import SessionLocal
from .records import HandRecord, PlayerStatsRecord

logger = logging.getLogger(__name__)


async def record_hand(table_id, players_meta, board, actions, awards) -> None:
    """Persist one completed hand. Never raises."""
    try:
        async with SessionLocal() as s:
            s.add(HandRecord(
                table_id=table_id,
                players=json.dumps(players_meta),
                board=json.dumps(board),
                actions=json.dumps(actions),
                awards=json.dumps(awards),
            ))
            await s.commit()
    except Exception:
        logger.exception("failed to record hand for table %s", table_id)


async def upsert_player_stats(deltas: list[dict]) -> None:
    """Accumulate per-name stats for human players. Never raises."""
    try:
        async with SessionLocal() as s:
            for d in deltas:
                if not d.get("is_human"):
                    continue
                row = (await s.execute(
                    select(PlayerStatsRecord).where(
                        PlayerStatsRecord.name == d["name"])
                )).scalar_one_or_none()
                if row is None:
                    row = PlayerStatsRecord(name=d["name"])
                    s.add(row)
                row.hands += 1
                row.wins += 1 if d.get("won") else 0
                row.net_chips += d.get("delta", 0)
            await s.commit()
    except Exception:
        logger.exception("failed to upsert player stats")


def schedule_recording(coro) -> None:
    """Fire-and-forget a recording coroutine (errors logged inside)."""
    asyncio.create_task(coro)
```

- [x] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 224 + 3 = 227 passed
git add backend/
git commit -m "feat: models layer — hand records and player stats persistence

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 后端 — 结算挂钩 + 历史 REST

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`（_resolve_showdown 调 recorder）
- Create: `backend/sekhmet/api/history.py`
- Modify: `backend/sekhmet/main.py`（挂路由 + lifespan 加 init_db）
- Test: `backend/tests/test_models.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 recorder
- Produces:
  - `GET /api/history/hands?limit=20&table_id=` — 倒序，含解析后的 JSON 字段
  - `GET /api/history/players` — net_chips 降序

- [ ] **Step 1: 写失败测试**

```python
async def test_hand_recorded_after_showdown(mem_db):
    """真实打一手牌（fold-out）→ 落库一条 HandRecord，战绩累计。"""
    import asyncio
    from sqlalchemy import select
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    sb = session.game_state.current_player_idx
    await tm.handle_player_action(tid, sb, "FOLD")
    await asyncio.sleep(0.05)  # fire-and-forget 落库

    async with db.SessionLocal() as s:
        hands = (await s.execute(select(records.HandRecord))).scalars().all()
        stats = (await s.execute(select(records.PlayerStatsRecord))).scalars().all()
    assert len(hands) == 1
    assert hands[0].table_id == tid
    assert len(stats) == 1 and stats[0].name == "Hero"  # bot 不入库
    assert stats[0].hands == 1


def test_history_endpoints(mem_db_sync_client):
    ...（用 TestClient + mem_db fixture 的组合；实现者自行组装：
         先 recorder.record_hand 两条，再 GET /api/history/hands 断言倒序与字段，
         GET /api/history/players 断言降序）
```

（`mem_db` fixture 与 TestClient 的组合细节由实现者处理——注意 TestClient 是同步的、recorder 是异步的：可以先 `asyncio.run(recorder.record_hand(...))` 准备数据再用 client 查询。）

- [ ] **Step 2: 确认红**

- [ ] **Step 3: 实现**

`_resolve_showdown` 末尾（stacks 更新、awards 计算之后）：

```python
    # Persist the completed hand (fire-and-forget; never blocks the game)
    winner_seats = {a.winner_seat_idx for a in awards_list}
    recorder.schedule_recording(recorder.record_hand(
        table_id=session.table_id,
        players_meta=[
            {
                "seat_idx": p.seat_idx, "name": p.name, "is_human": p.is_human,
                "stack_before": stacks_before[p.seat_idx],
                "stack_after": p.stack,
            }
            for p in players_list
        ],
        board=[str(c) for c in gs.community_cards],
        actions=[
            {"seat": a.player_idx, "action": a.type.name, "amount": a.amount}
            for a in gs.round_history
        ],
        awards=[
            {"seat_idx": a.winner_seat_idx, "amount": a.amount,
             "hand": a.hand_description}
            for a in awards_list
        ],
    ))
    recorder.schedule_recording(recorder.upsert_player_stats([
        {
            "name": p.name, "is_human": p.is_human,
            "won": p.seat_idx in winner_seats,
            "delta": p.stack - stacks_before[p.seat_idx],
        }
        for p in players_list
    ]))
```

注意：`_resolve_showdown` 现有结构是先在 `players_list` 上做 stack 更新再 `session.game_state = gs.with_players(...)`。在函数开头（stacks 更新前）快照 `stacks_before = {p.seat_idx: p.stack for p in gs.players}`；`from ..models import recorder` 加到 import（顶部，避免循环——models 不 import api，安全）。

`api/history.py`：

```python
"""Read-only REST endpoints for persisted hand history and player stats."""

from fastapi import APIRouter

from ..models.db import SessionLocal
from ..models.records import HandRecord, PlayerStatsRecord

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/hands")
async def list_hands(limit: int = 20, table_id: str | None = None):
    from sqlalchemy import select
    async with SessionLocal() as s:
        q = select(HandRecord).order_by(HandRecord.id.desc()).limit(min(limit, 100))
        if table_id:
            q = q.where(HandRecord.table_id == table_id)
        rows = (await s.execute(q)).scalars().all()
    import json
    return {"hands": [
        {
            "id": r.id, "table_id": r.table_id,
            "players": json.loads(r.players), "board": json.loads(r.board),
            "actions": json.loads(r.actions), "awards": json.loads(r.awards),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]}


@router.get("/players")
async def list_players():
    from sqlalchemy import select
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(PlayerStatsRecord).order_by(PlayerStatsRecord.net_chips.desc())
        )).scalars().all()
    return {"players": [
        {"name": r.name, "hands": r.hands, "wins": r.wins,
         "net_chips": r.net_chips, "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]}
```

`main.py`：`from .api import game, trainer, ws` → 加 `history`；`app.include_router(history.router)`；lifespan 里 `await tm.init...` 不对——加：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from .models.db import init_db
    await init_db()
    sweeper = asyncio.create_task(tm.sweeper_loop())
    try:
        yield
    finally:
        sweeper.cancel()
```

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 227 + 2 = 229 passed
git add backend/
git commit -m "feat: record hands on showdown, history REST endpoints

Co-Authored-By: Claude <noreply@anthropic.com>"
```

注意：测试套件现在共享同一个默认 DB（config.database_url 指向 ./sekhmet.db）——**测试之间会污染**。处理：tests/conftest.py 加一个 autouse fixture，把 DB 指到 tmp 文件：

```python
@pytest.fixture(autouse=True)
async def _isolated_db(tmp_path):
    from sekhmet.models import db
    db.configure(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    yield
    await db.engine.dispose()
```

（与 test_models.py 里的 mem_db fixture 合并——conftest 放 autouse 版，test_models 直接用。实现者注意 asyncio fixture 在 auto 模式下可用。）

---

### Task 3: 前端 — vitest 设施 + 组件测试 + CI job

**Files:**
- Modify: `frontend/package.json`（devDeps + test script）
- Modify: `frontend/vite.config.ts`（test 配置）
- Create: `frontend/src/test/setup.ts`、`frontend/src/__tests__/Toast.test.tsx`、`Leaderboard.test.tsx`、`CardView.test.tsx`
- Modify: `.github/workflows/ci.yml`（+frontend job）

**Interfaces:**
- Produces: `npm run test`（vitest run）；CI `frontend` job

- [ ] **Step 1: 装依赖**

```bash
cd frontend && npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom --registry=https://registry.npmmirror.com
```

package.json scripts 加 `"test": "vitest run"`。

- [ ] **Step 2: 配置与 setup**

`vite.config.ts`（现有内容保留，加 test 段；顶部加 reference）：

```ts
/// <reference types="vitest/config" />
// ...existing defineConfig({...}) 内加：
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
```

`src/test/setup.ts`：

```ts
import '@testing-library/jest-dom';
```

- [ ] **Step 3: 组件测试**

`src/__tests__/CardView.test.tsx`：

```tsx
import { render } from '@testing-library/react';
import CardView from '../components/table/CardView';

test('renders corner rank and suit', () => {
  const { container } = render(<CardView card="A♥" />);
  expect(container.querySelector('.corner')!.textContent).toBe('A♥');
  expect(container.querySelector('.pip')!.textContent).toBe('♥');
  expect(container.querySelector('.card')!.className).toContain('card-red');
});

test('black suit gets card-black, face-down gets card-back', () => {
  const { container } = render(<CardView card="K♠" />);
  expect(container.querySelector('.card')!.className).toContain('card-black');
  const back = render(<CardView />);
  expect(back.container.querySelector('.card-back')).toBeTruthy();
});

test('ten renders two-char rank', () => {
  const { container } = render(<CardView card="10♦" />);
  expect(container.querySelector('.corner')!.textContent).toBe('10♦');
});
```

`src/__tests__/Toast.test.tsx`：

```tsx
import { render, screen, fireEvent, act } from '@testing-library/react';
import Toast from '../components/shared/Toast';

test('renders and dismisses on click', () => {
  const onDismiss = vi.fn();
  render(<Toast items={[{ id: 1, kind: 'error', text: 'boom' }]} onDismiss={onDismiss} />);
  fireEvent.click(screen.getByText('boom'));
  expect(onDismiss).toHaveBeenCalledWith(1);
});

test('auto-dismisses after 3.5s', () => {
  vi.useFakeTimers();
  const onDismiss = vi.fn();
  render(<Toast items={[{ id: 1, kind: 'info', text: 'hi' }]} onDismiss={onDismiss} />);
  act(() => { vi.advanceTimersByTime(3600); });
  expect(onDismiss).toHaveBeenCalledWith(1);
  vi.useRealTimers();
});
```

`src/__tests__/Leaderboard.test.tsx`：

```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import Leaderboard from '../components/table/Leaderboard';

const seats = [
  { seat_idx: 0, name: 'Hero', is_human: true, bot_level: null, stack: 200, hands: 2, wins: 1, net_chips: 15, connected: true, is_owner: true },
  { seat_idx: 1, name: 'Bot', is_human: false, bot_level: 3, stack: 200, hands: 2, wins: 1, net_chips: -15, connected: true, is_owner: false },
];

test('collapsed by default, expands on click, sorted by net desc', () => {
  render(<Leaderboard seats={seats} />);
  expect(screen.queryByText('Hero')).toBeNull();
  fireEvent.click(screen.getByText(/Leaderboard/));
  const rows = screen.getAllByRole('row');
  expect(rows[1].textContent).toContain('Hero');   // +15 first
  expect(rows[2].textContent).toContain('Bot');    // -15 second
  expect(rows[2].textContent).toContain('L3');     // bot level badge
});
```

（Leaderboard 的 SeatInfo 字段以当前 useGameState.ts 为准——实现者核对字段名。）

- [ ] **Step 4: 验证 + CI job**

```bash
cd frontend && npm run test && npm run build && npx oxlint src
```

`.github/workflows/ci.yml` 在 test job 后加：

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Lint
        working-directory: frontend
        run: npx oxlint src
      - name: Unit tests
        working-directory: frontend
        run: npm run test
      - name: Build
        working-directory: frontend
        run: npm run build
```

- [ ] **Step 5: 提交**

```bash
git add frontend/ .github/workflows/ci.yml
git commit -m "feat: vitest component tests and frontend CI job

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 全量验证 + PR

- [ ] **Step 1: 全量验证**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -q   # 229 passed
cd ../frontend && npm run test && npm run build && npx oxlint src
```

- [ ] **Step 2: 推送并开 PR**（HTTPS+token 备用通道）

PR 标题：`feat: SQLite 持久化（对局记录+玩家战绩）+ 前端测试设施与 CI`
- [ ] **Step 3: 等 CI 绿（两个 job），请用户确认后合入**
