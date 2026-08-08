# 房间配置与 URL 路由 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建房可配置（盲注/默认买入/座位数）、房内手动加/踢 bot（可选 L1–L3）、URL 体现房间号（react-router + 入座确认页）。

**Architecture:** 后端 `TableConfig` 值对象随 `TableSession` 持有，bot 等级按座位存 `bot_levels`；前端引入 react-router-dom，Lobby 建房带配置，GameTable 改为 URL 驱动 + 未入座时渲染入座确认页。

**Tech Stack:** FastAPI + pytest（后端）、React 19 + Vite + react-router-dom（前端）。

**Spec:** `docs/superpowers/specs/2026-08-08-room-config-and-routing-design.md`

## Global Constraints

- 禁止直接提交 main；当前工作分支 `feat/room-config-routing`（spec 已提交在此分支）
- 后端测试：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`
- 前端安装依赖必须加 `--registry=https://registry.npmmirror.com`（网络环境要求）
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- TDD：先写失败测试，看红，再实现
- 本计划破坏式变更 ws `table_state` 消息的 `seats` 字段（map → 明细数组），前后端在同一 PR 内同步切换，无兼容负担

---

### Task 1: 后端 — TableConfig 与带配置建桌

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`（TableConfig、create_table、TableSession.config、sit_down 默认买入）
- Modify: `backend/sekhmet/api/game.py`（POST 接受配置 body）
- Test: `backend/tests/test_tables.py`（新建）

**Interfaces:**
- Consumes: 现有 `tm.create_table()`、`app_config`（仅默认值参考）
- Produces:
  - `TableConfig(small_blind=5, big_blind=10, default_buyin=200, max_seats=9)`——frozen dataclass，构造时校验，非法值抛 `ValueError`；`TableConfig.from_dict(d: dict) -> TableConfig`
  - `create_table(config: TableConfig | None = None) -> str`（不传用 TableConfig() 默认值）
  - `session.config: TableConfig`；`session.n_seats` 改读 `config.max_seats`

- [ ] **Step 1: 写失败测试**（新建 `backend/tests/test_tables.py`）

```python
"""Tests for table creation with room configuration."""

import pytest
from fastapi.testclient import TestClient

from sekhmet.main import app
from sekhmet.api import table_manager as tm
from sekhmet.api.table_manager import TableConfig
from sekhmet.game_engine.deck import Deck
from sekhmet.game_engine.action_processor import deal_new_hand
from sekhmet.game_engine.game_state import Player


async def test_create_table_with_custom_blinds():
    cfg = TableConfig(small_blind=10, big_blind=20, default_buyin=2000, max_seats=6)
    tid = await tm.create_table(cfg)
    session = await tm.get_table(tid)
    assert session is not None
    assert session.config.big_blind == 20
    assert session.n_seats == 6
    assert session.game_state.big_blind == 20


async def test_custom_blinds_reach_dealt_hand():
    cfg = TableConfig(small_blind=10, big_blind=20)
    tid = await tm.create_table(cfg)
    await tm.sit_down(tid, 0, "A", buyin=2000)
    await tm.sit_down(tid, 1, "B", buyin=2000)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    bets = {p.seat_idx: p.total_bet for p in session.game_state.players}
    assert sorted(bets.values()) == [10, 20]  # custom blinds posted


async def test_default_buyin_from_config():
    cfg = TableConfig(default_buyin=500)
    tid = await tm.create_table(cfg)
    await tm.sit_down(tid, 0, "A")  # no explicit buyin
    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.player(0).stack == 500


def test_config_validation():
    with pytest.raises(ValueError, match="small_blind"):
        TableConfig(small_blind=10, big_blind=10)   # sb must be < bb
    with pytest.raises(ValueError, match="max_seats"):
        TableConfig(max_seats=10)
    with pytest.raises(ValueError, match="default_buyin"):
        TableConfig(big_blind=50, small_blind=25, default_buyin=200)  # < 20bb
    with pytest.raises(ValueError, match="Unknown"):
        TableConfig.from_dict({"blinds": 10})


def test_rest_create_table_with_config():
    client = TestClient(app)
    resp = client.post("/api/game/tables",
                       json={"small_blind": 10, "big_blind": 20, "default_buyin": 2000})
    assert resp.status_code == 200
    detail = client.get(f"/api/game/tables/{resp.json()['table_id']}")
    assert detail.json()["config"]["big_blind"] == 20


def test_rest_create_table_invalid_config_400():
    client = TestClient(app)
    resp = client.post("/api/game/tables", json={"small_blind": 20, "big_blind": 10})
    assert resp.status_code == 400


def test_rest_create_table_no_body_still_works():
    client = TestClient(app)
    resp = client.post("/api/game/tables")
    assert resp.status_code == 200
```

- [ ] **Step 2: 跑测试确认红**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tables.py -q`
Expected: FAIL（`ImportError: cannot import name 'TableConfig'`）

- [ ] **Step 3: 实现 TableConfig 与 create_table**

`backend/sekhmet/api/table_manager.py` — 在 `_short_id()` 前加入：

```python
@dataclass(frozen=True)
class TableConfig:
    """Per-table room configuration, fixed at creation time."""

    small_blind: int = 5
    big_blind: int = 10
    default_buyin: int = 200
    max_seats: int = 9

    def __post_init__(self):
        if not (0 < self.small_blind < self.big_blind):
            raise ValueError(
                f"Require 0 < small_blind < big_blind, "
                f"got {self.small_blind}/{self.big_blind}"
            )
        if not (2 <= self.max_seats <= 9):
            raise ValueError(f"max_seats must be 2-9, got {self.max_seats}")
        if self.default_buyin < 20 * self.big_blind:
            raise ValueError(
                f"default_buyin must be >= 20 big blinds "
                f"({20 * self.big_blind}), got {self.default_buyin}"
            )

    @classmethod
    def from_dict(cls, d: dict) -> "TableConfig":
        known = {"small_blind", "big_blind", "default_buyin", "max_seats"}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"Unknown config keys: {sorted(unknown)}")
        return cls(**{k: int(v) for k, v in d.items()})
```

同文件修改：

```python
@dataclass
class TableSession:
    table_id: str
    game_state: GameState
    deck: Deck
    clients: dict[int, WebSocket] = field(default_factory=dict)
    player_names: dict[int, str] = field(default_factory=dict)
    config: TableConfig = field(default_factory=TableConfig)  # was: Any = app_config.game
```

`create_table` 改为：

```python
async def create_table(config: TableConfig | None = None) -> str:
    """Create a new table with the given room config (defaults if None)."""
    cfg = config or TableConfig()
    tid = _short_id()
    session = TableSession(
        table_id=tid,
        game_state=GameState(
            small_blind=cfg.small_blind,
            big_blind=cfg.big_blind,
        ),
        deck=Deck(),
        config=cfg,
    )
    async with _lock:
        _tables[tid] = session
    return tid
```

`sit_down` 中 `stack = buyin if buyin is not None else session.config.default_stack`
改为 `session.config.default_buyin`。

`backend/sekhmet/api/game.py` — POST 端点改为：

```python
from fastapi import APIRouter, HTTPException

@router.post("/tables")
async def create_table(body: dict | None = None):
    """Create a new poker table, optionally with a room config."""
    try:
        cfg = tm.TableConfig.from_dict(body or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    tid = await tm.create_table(cfg)
    return {"table_id": tid}
```

注意：`test_rest_create_table_with_config` 断言的 `config` 字段由 Task 2 的 `table_info` 提供，Task 1 阶段它保持红（Step 4 的 `-k` 已排除），Task 2 转绿。

- [ ] **Step 4: 跑测试**

Run: `python -m pytest tests/test_tables.py -q -k "not rest_create_table_with_config"`
Expected: 6 passed（REST 响应体断言那 1 个留待 Task 2）

- [ ] **Step 5: 全量回归 + 提交**

```bash
python -m pytest tests/ -q   # 既有 169 个测试不受影响（create_table() 无参兼容）
git add backend/sekhmet/api/table_manager.py backend/sekhmet/api/game.py backend/tests/test_tables.py
git commit -m "feat: add TableConfig and configurable table creation

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 后端 — bot 等级按座位、踢 bot、摘要带配置与座位明细

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`（bot_levels、sit_down、stand_up、auto_bot_actions、table_info/_table_summary）
- Modify: `backend/sekhmet/api/ws.py`（sit_down 传 bot_level；stand_up 支持踢 bot）
- Modify: `backend/sekhmet/api/game.py`（list/detail 用 table_info）
- Test: `backend/tests/test_tables.py`

**Interfaces:**
- Consumes: Task 1 的 `TableConfig`
- Produces:
  - `sit_down(..., bot_level: int | None = None)`——仅 `is_human=False` 时生效，范围 1–3，否则 `GameError`
  - `tm.table_info(session) -> dict`——`{table_id, phase, max_seats, config: {...}, seats: [{seat_idx, name, is_human, bot_level, stack}]}`
  - ws `table_state` 消息 = `{"type": "table_state", **table_info(session)}`（**`seats` 由 map 变为明细数组，破坏性变更**）
  - ws `stand_up` 消息接受可选 `seat_idx`：等于 `my_seat` 为离座；不等时仅允许移除非人类座位，否则回 error

- [ ] **Step 1: 写失败测试**（追加到 `backend/tests/test_tables.py`）

```python
from sekhmet.game_engine.game_state import GamePhase


async def _table_with_bot(level: int) -> str:
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False, bot_level=level)
    return tid


async def test_bot_level_drives_registry(monkeypatch):
    created: list[str] = []
    monkeypatch.setattr(
        "sekhmet.ai_engine.bot_registry.create",
        lambda name: created.append(name) or __import__(
            "sekhmet.ai_engine.rule_bot", fromlist=["RuleBot"]
        ).RuleBot(level=int(name[-1])),
    )
    tid = await _table_with_bot(3)
    await tm.start_hand(tid)
    await tm.auto_bot_actions(tid)
    assert "rule_lv3" in created


async def test_bot_level_default_is_2():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "B", is_human=False)  # no level given
    session = await tm.get_table(tid)
    assert session is not None
    assert session.bot_levels[0] == 2


async def test_bot_level_out_of_range_rejected():
    tid = await tm.create_table()
    from sekhmet.game_engine import GameError
    with pytest.raises(GameError, match="bot_level"):
        await tm.sit_down(tid, 0, "B", is_human=False, bot_level=9)


async def test_table_info_shape():
    tid = await _table_with_bot(1)
    session = await tm.get_table(tid)
    info = tm.table_info(session)
    assert info["config"]["big_blind"] == 10
    seats = {s["seat_idx"]: s for s in info["seats"]}
    assert seats[0]["is_human"] is True and seats[0]["bot_level"] is None
    assert seats[1]["is_human"] is False and seats[1]["bot_level"] == 1
    assert seats[1]["stack"] == 200


def test_ws_kick_bot_and_reject_kicking_human():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero"})
        ws1.receive_json()                      # ws1's join broadcast
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Friend"})
        ws2.receive_json()                      # ws2's join broadcast
        ws1.receive_json()                      # ws2's join, echoed to ws1

        # ws1 adds a bot, then kicks it
        ws1.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot",
                       "is_human": False, "bot_level": 3})
        ws1.receive_json(); ws2.receive_json()  # bot join broadcast
        ws1.send_json({"type": "stand_up", "seat_idx": 2})
        msg = ws1.receive_json()
        assert msg["type"] == "table_state"
        assert all(s["seat_idx"] != 2 for s in msg["seats"])
        ws2.receive_json()                      # drain kick broadcast on ws2

        # ws2 tries to kick the human at seat 0 — rejected
        ws2.send_json({"type": "stand_up", "seat_idx": 0})
        msg = ws2.receive_json()
        assert msg["type"] == "error"


async def test_sit_down_rejected_mid_hand():
    """Joining mid-hand would corrupt the round-close logic — reject it."""
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "A", buyin=200)
    await tm.sit_down(tid, 1, "B", buyin=200)
    await tm.start_hand(tid)
    with pytest.raises(GameError, match="mid-hand"):
        await tm.sit_down(tid, 2, "Late", buyin=200)
```

（`test_rest_create_table_with_config` 从 Task 1 遗留，此时应转绿。）

- [ ] **Step 2: 跑测试确认红**

Run: `python -m pytest tests/test_tables.py -q`
Expected: FAIL（`sit_down() got an unexpected keyword argument 'bot_level'` 等）

- [ ] **Step 3: 实现**

`table_manager.py`：

```python
@dataclass
class TableSession:
    ...
    bot_levels: dict[int, int] = field(default_factory=dict)  # seat_idx → 1-3
```

`sit_down` 签名与逻辑（在桌已满/座位占用检查之后）：

```python
async def sit_down(
    table_id: str,
    seat_idx: int,
    name: str,
    buyin: int | None = None,
    is_human: bool = True,
    bot_level: int | None = None,
) -> dict[str, Any]:
    ...
    # Mid-hand joins corrupt the betting round (a fresh player has matched
    # no bets and holds no cards) — only allow seating between hands.
    if session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        raise GameError("Table is mid-hand — wait for the next hand")
    if not is_human:
        level = 2 if bot_level is None else int(bot_level)
        if level not in (1, 2, 3):
            raise GameError(f"bot_level must be 1-3, got {bot_level}")
        session.bot_levels[seat_idx] = level
    ...
```

`stand_up` 末尾清 bot_levels：`session.bot_levels.pop(seat_idx, None)`。
（**不给 tm.stand_up 加 mid-hand 守卫**——断连离座走这条路，保持既有行为，见 spec §7 已知限制。踢 bot 的 mid-hand 守卫放在 ws 层，见下。）

`auto_bot_actions` 中：

```python
        level = session.bot_levels.get(cur_idx, 2)
        bot = create_bot(f"rule_lv{level}")
```

新增 `table_info`，并改 `_table_summary`：

```python
def table_info(session: TableSession) -> dict[str, Any]:
    """Serializable public table info — shared by REST and ws summary."""
    seats = []
    for seat, name in sorted(session.player_names.items()):
        p = session.game_state.player(seat)
        seats.append({
            "seat_idx": seat,
            "name": name,
            "is_human": p.is_human if p is not None else True,
            "bot_level": session.bot_levels.get(seat),
            "stack": p.stack if p is not None else 0,
        })
    return {
        "table_id": session.table_id,
        "phase": session.game_state.phase.name,
        "max_seats": session.n_seats,
        "config": {
            "small_blind": session.config.small_blind,
            "big_blind": session.config.big_blind,
            "default_buyin": session.config.default_buyin,
            "max_seats": session.config.max_seats,
        },
        "seats": seats,
    }


def _table_summary(session: TableSession) -> dict[str, Any]:
    return {"type": "table_state", **table_info(session)}
```

`game.py` 两个 GET 端点改为用 `tm.table_info(session)`（list 遍历 `tm._tables` 的现有写法保留，返回项换成 `table_info`；`n_players` 字段删除，前端同 PR 切换）。

`ws.py` — sit_down 传入 bot_level：

```python
                    bot_level = msg.get("bot_level")
                    ...
                    summary = await tm.sit_down(
                        table_id, seat_idx, name, buyin, is_human,
                        bot_level=bot_level,
                    )
```

ws.py — stand_up 支持踢 bot（替换现有 stand_up 分支）。踢人（target ≠ my_seat）只允许在非进行中阶段、且目标是非人类座位：

```python
                elif msg_type == "stand_up":
                    target = msg.get("seat_idx", my_seat)
                    if target is None:
                        continue
                    target = int(target)
                    if target == my_seat:
                        summary = await tm.stand_up(table_id, my_seat)
                        my_seat = None
                        await tm.broadcast(table_id, summary)
                    else:
                        session = await tm.get_table(table_id)
                        p = session.game_state.player(target) if session else None
                        mid_hand = session is not None and session.game_state.phase not in (
                            GamePhase.WAITING, GamePhase.SHOWDOWN,
                        )
                        if p is None or p.is_human:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Can only remove bot seats",
                            })
                            continue
                        if mid_hand:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Cannot remove players mid-hand",
                            })
                            continue
                        summary = await tm.stand_up(table_id, target)
                        await tm.broadcast(table_id, summary)
```

（ws.py 顶部 import 需加 `GamePhase`：`from ..game_engine import GameError, GamePhase`。）

- [ ] **Step 4: 跑测试**

Run: `python -m pytest tests/test_tables.py tests/test_ws.py -q`
Expected: 全绿。注意 `test_ws.py` 既有测试用 `seats` map 的地方（`ts1a["type"] == "table_state"` 只断言 type，无破坏）。

- [ ] **Step 5: 全量回归 + 提交**

```bash
python -m pytest tests/ -q
git add backend/sekhmet/api/table_manager.py backend/sekhmet/api/ws.py backend/sekhmet/api/game.py backend/tests/test_tables.py
git commit -m "feat: per-seat bot levels, kick-bot, table info with config

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 前端 — react-router 与 Lobby 建房表单

**Files:**
- Modify: `frontend/package.json`（+react-router-dom）
- Modify: `frontend/src/App.tsx`（改为 Router）
- Modify: `frontend/src/pages/Lobby.tsx`（建房表单 + navigate）

**Interfaces:**
- Consumes: Task 2 的 REST list/detail 形状（`seats` 数组、`config`）
- Produces:
  - 路由：`/` → Lobby，`/game/:tableId` → GameTablePage（Task 4 改 GameTablePage 为无 props）
  - `TableInfo` 类型：`{ table_id: string; phase: string; max_seats: number; config: { small_blind: number; big_blind: number; default_buyin: number; max_seats: number }; seats: { seat_idx: number; name: string; is_human: boolean; bot_level: number | null; stack: number }[] }`

- [ ] **Step 1: 装依赖**

```bash
cd frontend && npm install react-router-dom --registry=https://registry.npmmirror.com
```

- [ ] **Step 2: App.tsx 改为 Router**（完整替换）

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Lobby from './pages/Lobby';
import GameTablePage from './pages/GameTable';
import './styles/game.css';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Routes>
          <Route path="/" element={<Lobby />} />
          <Route path="/game/:tableId" element={<GameTablePage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
```

- [ ] **Step 3: Lobby.tsx 重写**（完整替换）

```tsx
import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface SeatInfo {
  seat_idx: number;
  name: string;
  is_human: boolean;
  bot_level: number | null;
  stack: number;
}

interface TableInfo {
  table_id: string;
  phase: string;
  max_seats: number;
  config: { small_blind: number; big_blind: number; default_buyin: number; max_seats: number };
  seats: SeatInfo[];
}

const BLIND_TIERS = [
  { label: '1/2', sb: 1, bb: 2 },
  { label: '5/10', sb: 5, bb: 10 },
  { label: '10/20', sb: 10, bb: 20 },
  { label: '25/50', sb: 25, bb: 50 },
];

export default function Lobby() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [name, setName] = useState(() => localStorage.getItem('pokerName') || '');
  const [tier, setTier] = useState(BLIND_TIERS[1]);
  const [buyin, setBuyin] = useState(BLIND_TIERS[1].bb * 100);
  const [maxSeats, setMaxSeats] = useState(9);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      const resp = await fetch('/api/game/tables');
      const data = await resp.json();
      setTables(data.tables || []);
    } catch { /* server may not be running */ }
  }, []);

  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [refresh]);

  const create = async () => {
    try {
      const resp = await fetch('/api/game/tables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          small_blind: tier.sb,
          big_blind: tier.bb,
          default_buyin: buyin,
          max_seats: maxSeats,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        alert(err.detail ?? 'Create failed');
        return;
      }
      const data = await resp.json();
      localStorage.setItem('pokerName', name);
      navigate(`/game/${data.table_id}`);
    } catch { alert('Cannot reach server'); }
  };

  return (
    <div className="lobby">
      <h1 className="page-title">♠ Sekhmet Poker</h1>

      <div className="lobby-actions">
        <input className="input" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} />
        <select className="input" value={tier.label}
                onChange={e => {
                  const t = BLIND_TIERS.find(x => x.label === e.target.value)!;
                  setTier(t);
                  setBuyin(t.bb * 100);
                }}>
          {BLIND_TIERS.map(t => <option key={t.label} value={t.label}>Blinds {t.label}</option>)}
        </select>
        <input className="input" type="number" placeholder="Default buy-in" value={buyin}
               onChange={e => setBuyin(Number(e.target.value))} style={{ width: 130 }} />
        <select className="input" value={maxSeats} onChange={e => setMaxSeats(Number(e.target.value))}>
          {[2, 3, 4, 5, 6, 7, 8, 9].map(n => <option key={n} value={n}>{n} seats</option>)}
        </select>
        <button className="btn" onClick={create} disabled={!name}>+ New Table</button>
      </div>

      <div className="table-list">
        {tables.length === 0 && <div className="waiting-text">No active tables. Create one!</div>}
        {tables.map(t => (
          <div key={t.table_id} className="table-card"
               onClick={() => { localStorage.setItem('pokerName', name); navigate(`/game/${t.table_id}`); }}>
            <span className="id">{t.table_id}</span>
            <span className="info">
              {t.config.small_blind}/{t.config.big_blind} · {t.seats.length}/{t.max_seats} · {t.phase}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

注意：Lobby 加入时**不再**选座位——座位选择移到 Task 4 的入座确认页。

- [ ] **Step 4: 构建验证**

```bash
cd frontend && npm run build
```
Expected: 构建成功（GameTable.tsx 仍收 props 会报类型错误——属于预期，Task 4 修掉；若想本任务即绿，可先把 GameTablePage 调用处包一层兼容。推荐：接受本任务 build 红，Task 4 完成后转绿，因为两任务在同一 PR）

- [ ] **Step 5: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/App.tsx frontend/src/pages/Lobby.tsx
git commit -m "feat: react-router and configurable table creation form

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 前端 — 入座确认页 + 手动加/踢 bot

**Files:**
- Modify: `frontend/src/hooks/useGameState.ts`（seats 明细 + config 入 state）
- Modify: `frontend/src/pages/GameTable.tsx`（URL 驱动 + 入座确认页 + 加/踢 bot，删自动加 bot）
- Modify: `frontend/src/components/table/OvalTable.tsx`（空位渲染 "+ Bot"，bot 徽章与移除）
- Modify: `frontend/src/styles/game.css`（新样式）

**Interfaces:**
- Consumes: Task 2 的 ws `table_state`（seats 明细数组 + config）、`sit_down.bot_level`、`stand_up.seat_idx`；Task 3 的路由
- Produces:
  - reducer state 新增：`seats: SeatInfo[]`、`config: TableConfigData | null`
  - `GameTablePage` 无 props（`useParams` 取 tableId）

- [ ] **Step 1: useGameState.ts 协议更新**

`GameMsg` 的 `table_state` 分支改为：

```typescript
export interface SeatInfo {
  seat_idx: number;
  name: string;
  is_human: boolean;
  bot_level: number | null;
  stack: number;
}

export interface TableConfigData {
  small_blind: number;
  big_blind: number;
  default_buyin: number;
  max_seats: number;
}

// GameMsg union 中：
  | { type: 'table_state'; table_id: string; seats: SeatInfo[]; phase: string;
      max_seats: number; config: TableConfigData }
```

`AppState` 加两个字段并在 `initialState` 初始化：

```typescript
  seats: SeatInfo[];          // initial: []
  config: TableConfigData | null;  // initial: null
```

reducer 的 `TABLE_STATE` 分支：

```typescript
    case 'TABLE_STATE':
      return {
        ...state,
        seats: action.data.seats,
        config: action.data.config,
        maxSeats: action.data.max_seats,
      };
```

（`SeatInfo` 从本文件 export，供 OvalTable/GameTable 使用。）

- [ ] **Step 2: GameTable.tsx 重写**（完整替换）

```tsx
import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useWebSocket } from '../hooks/useWebSocket';
import { useGameState } from '../hooks/useGameState';
import type { GameMsg, TableConfigData, SeatInfo } from '../hooks/useGameState';
import OvalTable from '../components/table/OvalTable';
import ActionBar from '../components/table/ActionBar';

interface TableDetail {
  table_id: string;
  phase: string;
  max_seats: number;
  config: TableConfigData;
  seats: SeatInfo[];
}

export default function GameTablePage() {
  const { tableId = '' } = useParams();
  const navigate = useNavigate();
  const [state, dispatch] = useGameState();
  const { connected, send, onMessage } = useWebSocket(tableId);
  const [detail, setDetail] = useState<TableDetail | null | 'not-found'>(null);
  const [name, setName] = useState(() => localStorage.getItem('pokerName') || '');
  const [buyin, setBuyin] = useState(200);

  // Fetch room info for the join panel
  useEffect(() => {
    fetch(`/api/game/tables/${tableId}`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then((d: TableDetail) => { setDetail(d); setBuyin(d.config.default_buyin); })
      .catch(() => setDetail('not-found'));
  }, [tableId]);

  // Dispatch messages to reducer
  useEffect(() => {
    onMessage((msg) => {
      const m = msg as GameMsg;
      switch (m.type) {
        case 'table_state': dispatch({ type: 'TABLE_STATE', data: m as any }); break;
        case 'hand_start': dispatch({ type: 'HAND_START', data: m as any }); break;
        case 'hole_cards': dispatch({ type: 'HOLE_CARDS', cards: m.cards }); break;
        case 'game_state_update': dispatch({ type: 'GAME_UPDATE', data: m as any }); break;
        case 'hand_result': dispatch({ type: 'HAND_RESULT', data: m as any }); break;
        case 'error': alert(m.message); break;  // never fail silently
      }
    });
  }, [onMessage, dispatch]);

  useEffect(() => {
    dispatch({ type: 'SET_TABLE', tableId });
    dispatch({ type: 'SET_CONNECTED', connected });
  }, [tableId, connected, dispatch]);

  const joinTable = () => {
    if (!detail || detail === 'not-found') return;
    // Use the freshly fetched REST detail for occupancy — the reducer's
    // seats only populate on table_state broadcasts (sit/stand events).
    const taken = new Set(detail.seats.map(s => s.seat_idx));
    const free = Array.from({ length: detail.max_seats }, (_, i) => i)
      .find(i => !taken.has(i));
    if (free === undefined) { alert('Table is full'); return; }
    localStorage.setItem('pokerName', name);
    send({ type: 'sit_down', seat_idx: free, name, buyin });
    dispatch({ type: 'SET_MY_SEAT', seat: free });
  };

  const addBot = useCallback((seatIdx: number, level: number) => {
    send({ type: 'sit_down', seat_idx: seatIdx, name: `Bot L${level}`,
           buyin: state.config?.default_buyin ?? 200, is_human: false, bot_level: level });
  }, [send, state.config]);

  const kickBot = useCallback((seatIdx: number) => {
    send({ type: 'stand_up', seat_idx: seatIdx });
  }, [send]);

  const handleAction = useCallback((action: string, amount?: number) => {
    send({ type: 'player_action', action, amount: amount ?? 0 });
  }, [send]);

  // ---- Join panel (not seated yet) ----
  if (state.mySeat === null) {
    if (detail === 'not-found') {
      return (
        <div className="join-panel">
          <h2>Table not found</h2>
          <button className="btn" onClick={() => navigate('/')}>← Lobby</button>
        </div>
      );
    }
    if (!detail) return <div className="waiting-text">Loading…</div>;
    return (
      <div className="join-panel">
        <h2>Table {detail.table_id}</h2>
        <p>Blinds {detail.config.small_blind}/{detail.config.big_blind}
           {' '}· Buy-in {detail.config.default_buyin}
           {' '}· {detail.seats.length}/{detail.max_seats} players
           {' '}· {detail.phase}</p>
        {detail.seats.length > 0 && (
          <p>Seated: {detail.seats.map(s => s.name).join(', ')}</p>
        )}
        <div className="lobby-actions">
          <input className="input" placeholder="Your name" value={name}
                 onChange={e => setName(e.target.value)} />
          <input className="input" type="number" value={buyin} style={{ width: 110 }}
                 onChange={e => setBuyin(Number(e.target.value))} />
          <button className="btn" onClick={joinTable} disabled={!name || !connected}>
            Sit Down
          </button>
          <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        </div>
      </div>
    );
  }

  // ---- Table view (seated) ----
  const me = state.players.find(p => p.seat_idx === state.mySeat);

  return (
    <div className="game-table">
      <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
        <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        <span className="phase-label">
          {tableId} · {state.phase}{!connected && ' (disconnected)'}
        </span>
        <button className="btn btn-sm" onClick={() => send({ type: 'start_hand' })}
                disabled={state.phase !== 'WAITING' && state.phase !== 'SHOWDOWN'}>
          Deal
        </button>
      </div>

      <OvalTable
        seats={state.seats}
        players={state.players}
        maxSeats={state.maxSeats}
        communityCards={state.communityCards}
        pot={state.pot}
        currentPlayerIdx={state.currentPlayerIdx}
        mySeat={state.mySeat}
        holeCards={state.holeCards}
        phase={state.phase}
        onAddBot={addBot}
        onKickBot={kickBot}
      />

      <ActionBar
        isMyTurn={state.currentPlayerIdx === state.mySeat}
        currentBet={state.currentBet}
        myStack={me?.stack ?? 0}
        myCurrentBet={me?.current_bet ?? 0}
        bigBlind={state.config?.big_blind ?? 10}
        onAction={handleAction}
      />

      {state.showdown && (
        <div className="hand-result">
          <h3>Showdown</h3>
          {Object.entries(state.showdown.hands).map(([s, h]) => (
            <div key={s}>Seat {s}: {h}</div>
          ))}
          {state.showdown.awards.map((a, i) => (
            <div key={i} className="award">
              <span className="winner">Seat {a.seat_idx} wins {a.amount}</span>
              <span>{a.hand}</span>
            </div>
          ))}
        </div>
      )}

      <div className="history">
        {state.roundHistory.map((h, i) => (
          <span key={i}>P{h.seat} {h.action}{h.amount > 0 ? ` ${h.amount}` : ''} · </span>
        ))}
      </div>
    </div>
  );
}
```

要点：**自动加 bot 的 effect 已删除**；入座改为手动触发；URL 里有房间号（phase-label 也显示了 tableId）。

- [ ] **Step 3: OvalTable.tsx 重写**（完整替换）

```tsx
import { useState } from 'react';
import type { PlayerInfo, SeatInfo } from '../../hooks/useGameState';
import PlayerSeat from './PlayerSeat';
import CommunityCards from './CommunityCards';
import PotDisplay from './PotDisplay';

interface Props {
  seats: SeatInfo[];
  players: PlayerInfo[];
  maxSeats: number;
  communityCards: string[];
  pot: number;
  currentPlayerIdx: number | null;
  mySeat: number | null;
  holeCards: string[];
  phase: string;
  onAddBot: (seatIdx: number, level: number) => void;
  onKickBot: (seatIdx: number) => void;
}

/** Map a seat index to an oval display slot, rotating so *mySeat* is at
 *  position 0 (bottom center). */
function displaySlot(seatIdx: number, total: number, mySeat: number | null): number {
  if (mySeat === null) return seatIdx % 8;
  const rel = (seatIdx - mySeat + total) % total;
  const SLOTS = total <= 2 ? [0, 4] : [0, 2, 3, 4, 5, 6, 7, 1];
  if (total <= 8) return SLOTS[rel % SLOTS.length];
  return rel % 8;
}

export default function OvalTable({
  seats, players, maxSeats, communityCards, pot, currentPlayerIdx,
  mySeat, holeCards, phase, onAddBot, onKickBot,
}: Props) {
  const showCommunity = phase !== 'WAITING' && phase !== 'PREFLOP' && phase !== 'DEALING';
  // Mid-hand seating changes corrupt the engine — only offer bot seats
  // between hands (the server enforces this too; this is the UI half).
  const canAddBot = phase === 'WAITING' || phase === 'SHOWDOWN';
  const [pendingSeat, setPendingSeat] = useState<number | null>(null);
  const total = Math.min(Math.max(maxSeats, 2), 8);
  const occupied = new Map(seats.map(s => [s.seat_idx, s]));

  return (
    <div className="table-felt">
      {showCommunity && <CommunityCards cards={communityCards} />}
      <PotDisplay amount={pot} />

      {seats.map((seat) => {
        const p = players.find(pl => pl.seat_idx === seat.seat_idx);
        const isMe = mySeat === seat.seat_idx;
        const slot = displaySlot(seat.seat_idx, total, mySeat);
        // Merge lobby-level seat info with in-hand player info
        const merged: PlayerInfo = p ?? {
          seat_idx: seat.seat_idx,
          name: seat.name,
          stack: seat.stack,
          current_bet: 0,
          is_active: true,
          is_all_in: false,
          is_human: seat.is_human,
        };
        return (
          <div key={seat.seat_idx} className="seat-wrap">
            <PlayerSeat
              player={merged}
              seatIndex={slot}
              isCurrent={currentPlayerIdx === seat.seat_idx}
              holeCards={isMe ? holeCards : undefined}
              showCards={phase === 'SHOWDOWN' || isMe}
            />
            {!seat.is_human && (
              <span className="bot-badge">
                L{seat.bot_level ?? 2}
                <button className="kick-btn" title="Remove bot"
                        onClick={() => onKickBot(seat.seat_idx)}>×</button>
              </span>
            )}
          </div>
        );
      })}

      {canAddBot && Array.from({ length: maxSeats }, (_, i) => i)
        .filter(i => !occupied.has(i))
        .map(i => (
          <div key={`empty-${i}`} className={`empty-seat seat-${displaySlot(i, total, mySeat)}`}>
            {pendingSeat === i ? (
              <span className="bot-level-picker">
                {[1, 2, 3].map(lv => (
                  <button key={lv} className="btn btn-sm"
                          onClick={() => { onAddBot(i, lv); setPendingSeat(null); }}>
                    L{lv}
                  </button>
                ))}
              </span>
            ) : (
              <button className="add-bot-btn" onClick={() => setPendingSeat(i)}>+ Bot</button>
            )}
          </div>
        ))}
    </div>
  );
}
```

- [ ] **Step 4: game.css 追加样式**

```css
/* Join panel */
.join-panel { max-width: 480px; margin: 10vh auto; text-align: center; }
.join-panel h2 { color: #e8c15a; }

/* Empty seat + bot controls */
.empty-seat { position: absolute; }
.add-bot-btn {
  background: rgba(255,255,255,0.08); color: #9db89d;
  border: 1px dashed #4a6a4a; border-radius: 8px; padding: 8px 14px; cursor: pointer;
}
.add-bot-btn:hover { background: rgba(255,255,255,0.16); }
.bot-level-picker { display: flex; gap: 4px; }
.seat-wrap { position: relative; display: contents; }
.bot-badge {
  position: absolute; top: -8px; right: -8px;
  background: #2a4a2a; color: #8fd48f; font-size: 11px;
  border-radius: 8px; padding: 1px 5px;
}
.kick-btn {
  background: none; border: none; color: #d48f8f; cursor: pointer;
  font-size: 12px; margin-left: 3px; padding: 0;
}
```

（`.seat-N` 定位类已存在于 game.css 的椭圆桌布局中，empty-seat 复用同样的定位。）

- [ ] **Step 5: 构建 + 类型检查**

```bash
cd frontend && npm run build
```
Expected: 成功，无 TS 错误。

- [ ] **Step 6: 手动冒烟（需要起前后端）**

```bash
cd backend && source .venv/bin/activate && uvicorn sekhmet.main:app --port 8000 &
cd frontend && npm run dev
```

验证清单：
1. Lobby 选 10/20 档位 + 6 座位建房 → URL 变为 `/game/<id>`，入座确认页显示 10/20
2. 入座 → 点空位 "+ Bot" 选 L3 → bot 入座带 L3 徽章
3. 新开浏览器标签访问同一 URL → 入座确认页显示已坐 2 个 → 入座开打
4. 点 bot 徽章 × → bot 被移除
5. Deal → 盲注是 10/20

- [ ] **Step 7: 提交**

```bash
git add frontend/src frontend/src/styles/game.css
git commit -m "feat: join panel via URL, manual bot add/kick with level picker

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 推送、CI、PR

- [ ] **Step 1: 全量验证**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -q
cd ../frontend && npm run build
```

- [ ] **Step 2: 推送并开 PR**

```bash
git push -u origin feat/room-config-routing
```

PR 标题：`feat: 房间配置（盲注/买入/座位数）+ URL 路由 + 房内手动加 bot`
PR 正文引用 spec：`docs/superpowers/specs/2026-08-08-room-config-and-routing-design.md`

- [ ] **Step 3: 等 CI 绿，请用户确认后合入**（项目铁律：不自行 merge）
