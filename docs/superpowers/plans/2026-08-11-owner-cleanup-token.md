# 包 B：房主权限 / 房间回收 / 认领 token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 房主制（发牌/踢 bot 权限）、闲置房间自动回收、防冒领的重连 token。

**Architecture:** 全部为 table_manager/ws 层增强：owner_seat 追踪与移交、last_activity + lifespan sweeper、reclaim_tokens 私发与轮换；前端透传角标/禁用态/localStorage 自动携带。

**Tech Stack:** FastAPI + pytest（asyncio_mode=auto）；React 19 + Vite。

**Spec:** `docs/superpowers/specs/2026-08-11-owner-cleanup-token-design.md`

## Global Constraints

- 工作分支 `feat/owner-cleanup-token`（spec 已提交）；禁止直接提交 main
- 后端测试：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`（当前 208 passed）
- 前端门禁：`cd frontend && npm run build && npx oxlint src` 绿
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- TDD：先写失败测试，看红，再实现
- 协议变更均为兼容式加字段/加消息；`tests/test_e2e_game_journey.py` 的 seats 全等断言需同步 `is_owner`

---

### Task 1: 后端 — 房主制

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`（owner_seat、_reassign_owner、sit_down/stand_up/_expire_seat、table_info）
- Modify: `backend/sekhmet/api/ws.py`（start_hand/踢 bot 权限校验）
- Test: `backend/tests/test_tables.py`（追加）
- Modify: `backend/tests/test_e2e_game_journey.py`（seats 全等断言 +is_owner）

**Interfaces:**
- Produces:
  - `TableSession.owner_seat: int | None = None`
  - seats 明细 + `is_owner: bool`
  - ws 权限错误：`"Only the table owner can start a hand"` / `"Only the table owner can remove bots"`

- [ ] **Step 1: 写失败测试**

```python
async def test_first_human_becomes_owner():
    tid = await tm.create_table()
    await tm.sit_down(tid, 2, "Bot", buyin=200, is_human=False)
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    session = await tm.get_table(tid)
    assert session is not None
    assert session.owner_seat == 0  # bot 不当房主；第一个人类接任
    info = tm.table_info(session)
    owners = {s["seat_idx"]: s["is_owner"] for s in info["seats"]}
    assert owners == {0: True, 2: False}


async def test_owner_reassigned_on_removal():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Friend", buyin=200)
    await tm.stand_up(tid, 0)
    session = await tm.get_table(tid)
    assert session is not None
    assert session.owner_seat == 1
    await tm.stand_up(tid, 1)
    session = await tm.get_table(tid)
    assert session.owner_seat is None


def test_ws_non_owner_cannot_start_hand():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Owner"})
        ws1.receive_json()
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Guest"})
        ws2.receive_json(); ws1.receive_json()
        ws2.send_json({"type": "start_hand"})
        err = ws2.receive_json()
        assert err["type"] == "error"
        assert "owner" in err["message"]
        # 房主可以发
        ws1.send_json({"type": "start_hand"})
        msg = ws1.receive_json()
        assert msg["type"] == "hand_start"


def test_ws_non_owner_cannot_kick_bot():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Owner"})
        ws1.receive_json()
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Guest"})
        ws2.receive_json(); ws1.receive_json()
        ws1.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot", "is_human": False})
        ws1.receive_json(); ws2.receive_json()
        ws2.send_json({"type": "stand_up", "seat_idx": 2})
        err = ws2.receive_json()
        assert err["type"] == "error" and "owner" in err["message"]
        # 房主可以踢
        ws1.send_json({"type": "stand_up", "seat_idx": 2})
        msg = ws1.receive_json()
        assert msg["type"] == "table_state"
        assert all(s["seat_idx"] != 2 for s in msg["seats"])
```

- [ ] **Step 2: 确认红**（owner_seat/is_owner 不存在、权限不拦截）

- [ ] **Step 3: 实现**

`table_manager.py`：

```python
# TableSession 加字段：
    owner_seat: int | None = None


def _reassign_owner(session: TableSession) -> None:
    """Hand ownership to the lowest-seated remaining human (or None)."""
    if session.owner_seat is not None:
        p = session.game_state.player(session.owner_seat)
        if p is not None and p.is_human and session.owner_seat in session.player_names:
            return  # current owner still valid
    humans = [
        p.seat_idx for p in session.game_state.players
        if p.is_human and p.seat_idx in session.player_names
    ]
    session.owner_seat = min(humans) if humans else None
```

`sit_down`（人类入座成功后）：`session.owner_seat = seat_idx if is_human and session.owner_seat is None else session.owner_seat` —— 直接写法：在 player 加入后调 `_reassign_owner(session)`（它会保持现有房主；无房主时选最小人类座位——但若人类先于 bot 入座顺序不同也能正确取到第一个人类）。注意：_reassign_owner 在 owner None 时取 min(humans)，多人后房主离开则移交最小座位人类，语义一致。

`stand_up` 与 `_expire_seat` 的身份清理之后各调一次 `_reassign_owner(session)`。

`table_info` seats 明细加：`"is_owner": seat == session.owner_seat`。

`ws.py`：

- `start_hand` 分支开头（`tm.start_hand` 之前）：

```python
                elif msg_type == "start_hand":
                    session = await tm.get_table(table_id)
                    if session is None or my_seat != session.owner_seat:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Only the table owner can start a hand",
                        })
                        continue
                    broadcast_msg = await tm.start_hand(table_id)
                    ...（原有逻辑不变）
```

- 踢 bot 分支（target != my_seat 的 stand_up）在既有检查前加：

```python
                        session = await tm.get_table(table_id)
                        if session is None or my_seat != session.owner_seat:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Only the table owner can remove bots",
                            })
                            continue
```

（注意原有 `session = await tm.get_table(table_id)` 行合并，别重复声明。）

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 208 + 4 = 212 passed
git add backend/
git commit -m "feat: table ownership — only owner can start hands and remove bots

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 后端 — 闲置房间回收

**Files:**
- Modify: `backend/sekhmet/config.py`（+room_idle_timeout_seconds）
- Modify: `backend/sekhmet/api/table_manager.py`（last_activity、touch、sweep_idle_tables、sweeper_loop）
- Modify: `backend/sekhmet/api/ws.py`（每条消息 touch）
- Modify: `backend/sekhmet/main.py`（lifespan 启动 sweeper）
- Test: `backend/tests/test_tables.py`（追加）

**Interfaces:**
- Produces:
  - `GameConfig.room_idle_timeout_seconds: int = 1800`
  - `TableSession.last_activity: float`
  - `async def tm.touch(table_id)` / `async def tm.sweep_idle_tables() -> list[str]`（返回被回收的 table_id）/ `async def tm.sweeper_loop()`
  - 广播消息 `{"type": "room_closed", "table_id": ...}`

- [ ] **Step 1: 写失败测试**

```python
async def test_touch_refreshes_activity():
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    assert session is not None
    session.last_activity -= 100  # 手动老化
    await tm.touch(tid)
    import time
    assert time.monotonic() - session.last_activity < 5


async def test_sweep_removes_idle_room():
    import time
    monkeypatch_timeout = 60  # 直接改字段比 patch 时间简单
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    assert session is not None
    session.last_activity = time.monotonic() - 3700  # 超过 30 分钟
    closed = await tm.sweep_idle_tables()
    assert tid in closed
    assert await tm.get_table(tid) is None


async def test_sweep_keeps_active_room():
    tid = await tm.create_table()
    closed = await tm.sweep_idle_tables()
    assert tid not in closed
    assert await tm.get_table(tid) is not None
```

（sweep 的 room_closed 广播在有连接时发出——测试无连接场景即可，广播函数对空 clients 安全。）

- [ ] **Step 2: 确认红**

- [ ] **Step 3: 实现**

`config.py`：`room_idle_timeout_seconds: int = 1800`

`table_manager.py`（顶部加 `import time`）：

```python
# TableSession 加字段：
    last_activity: float = field(default_factory=time.monotonic)


async def touch(table_id: str) -> None:
    session = await get_table(table_id)
    if session is not None:
        session.last_activity = time.monotonic()


async def sweep_idle_tables() -> list[str]:
    """Close rooms idle beyond the configured timeout. Returns closed ids."""
    timeout = app_config.game.room_idle_timeout_seconds
    now = time.monotonic()
    closed: list[str] = []
    for tid, session in list(_tables.items()):
        if now - session.last_activity <= timeout:
            continue
        for task in session.grace_timers.values():
            task.cancel()
        if session.action_timer is not None:
            session.action_timer.cancel()
        await broadcast(tid, {"type": "room_closed", "table_id": tid})
        await remove_table(tid)
        closed.append(tid)
    return closed


async def sweeper_loop(interval_seconds: float = 60.0) -> None:
    """Background task: periodically sweep idle rooms."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await sweep_idle_tables()
        except Exception:
            logger.exception("sweeper iteration failed")
```

`ws.py` 消息循环内、JSON 解析成功后：`await tm.touch(table_id)`。

`main.py`：

```python
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    sweeper = asyncio.create_task(tm.sweeper_loop())
    try:
        yield
    finally:
        sweeper.cancel()

app = FastAPI(
    title="Sekhmet",
    description="Texas Hold'em game & training platform",
    version="0.1.0",
    lifespan=lifespan,
)
```

（main.py 需 `from .api import table_manager as tm`。）

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 212 + 3 = 215 passed
git add backend/
git commit -m "feat: idle room sweeper with room_closed broadcast

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 后端 — 认领 token

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`（reclaim_tokens、try_reclaim 改造）
- Modify: `backend/sekhmet/api/ws.py`（sit_down 私发 token、reclaim 校验与轮换）
- Test: `backend/tests/test_tables.py`（追加）

**Interfaces:**
- Consumes: Task 3（断线 PR）的 try_reclaim / disconnected
- Produces:
  - `TableSession.reclaim_tokens: dict[int, str]`
  - sit_down 可选字段 `reclaim_token`
  - 私发消息 `{"type": "reclaim_token", "token": str}`（人类入座成功 + 认领成功后轮换）
  - `tm.try_reclaim(table_id, name, token) -> tuple[int, str] | None`——返回 (seat, new_token)

- [ ] **Step 1: 写失败测试**

```python
async def test_reclaim_requires_token():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    session = await tm.get_table(tid)
    token = session.reclaim_tokens[0]

    await tm.handle_disconnect(tid, 0)
    # 无 token / 错 token 拒
    assert await tm.try_reclaim(tid, "Hero", None) is None
    assert await tm.try_reclaim(tid, "Hero", "wrong") is None
    # 正确 token → 认领成功并轮换
    result = await tm.try_reclaim(tid, "Hero", token)
    assert result is not None
    seat, new_token = result
    assert seat == 0
    assert new_token != token
    assert session.reclaim_tokens[0] == new_token


def test_ws_sit_down_sends_private_token():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        msgs = [ws.receive_json(), ws.receive_json()]
        token_msg = next(m for m in msgs if m["type"] == "reclaim_token")
        assert len(token_msg["token"]) == 32
```

既有测试适配：`test_reclaim_by_name_restores_seat`（断线 PR 引入，无 token 调用 try_reclaim）同步更新——先从 `session.reclaim_tokens[0]` 取 token 再调用；`tm.try_reclaim(tid, "Stranger", token)` 仍应返回 None（名字不匹配）。

- [ ] **Step 2: 确认红**

- [ ] **Step 3: 实现**

`table_manager.py`：

```python
# TableSession 加字段：
    reclaim_tokens: dict[int, str] = field(default_factory=dict)
```

`sit_down`（人类部分）：

```python
    if is_human:
        import secrets
        session.reclaim_tokens[seat_idx] = secrets.token_hex(16)
```

（secrets 提到模块顶部 import。bot 不发 token；stand_up/_expire_seat 清理 reclaim_tokens 条目。）

`try_reclaim` 改造：

```python
async def try_reclaim(
    table_id: str, name: str, token: str | None
) -> tuple[int, str] | None:
    """Reclaim a disconnected seat by name + token. Returns (seat, new_token)."""
    session = await get_table(table_id)
    if session is None or token is None:
        return None
    for seat in list(session.disconnected):
        if (
            session.player_names.get(seat) == name
            and session.reclaim_tokens.get(seat) == token
        ):
            timer = session.grace_timers.pop(seat, None)
            if timer is not None:
                timer.cancel()
            session.disconnected.discard(seat)
            new_token = secrets.token_hex(16)
            session.reclaim_tokens[seat] = new_token
            return seat, new_token
    return None
```

`ws.py`：

1. sit_down 成功且 is_human 后私发：

```python
                    if is_human:
                        session.clients[seat_idx] = websocket
                        my_seat = seat_idx
                        token = session.reclaim_tokens.get(seat_idx)
                        if token:
                            await websocket.send_json({
                                "type": "reclaim_token", "token": token,
                            })
```

2. 认领分支改为带 token，成功后私发新 token；失败回 error：

```python
                    reclaimed = await tm.try_reclaim(
                        table_id, name, msg.get("reclaim_token")
                    )
                    if reclaimed is not None:
                        seat, new_token = reclaimed
                        session.clients[seat] = websocket
                        my_seat = seat
                        await websocket.send_json({
                            "type": "reclaim_token", "token": new_token,
                        })
                        await tm.broadcast(table_id, tm._table_summary(session))
                        ...（原有 hole_cards + state 补发不变）
                        continue
                    if msg.get("reclaim_token") is not None or (
                        session.game_state.player(seat_idx) is not None
                        and seat_idx in session.disconnected
                    ):
                        await websocket.send_json({
                            "type": "error",
                            "message": "Reclaim token mismatch",
                        })
                        continue
```

（简化建议：认领失败不需要特意区分——只要 try_reclaim 返回 None 且目标座位在 disconnected 里，正常 sit_down 也会因为 seat occupied 报错，语义已足够。实现者可以把 error 分支简化为让正常 sit_down 的 "Seat is already occupied" 兜住，但**必须保证无 token 不能认领**。选一个实现并在报告里说明。）

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 215 + 2 = 217 passed
git add backend/
git commit -m "feat: reclaim token required for seat reclaim, rotated on success

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 前端 — 房主角标 / Deal 禁用 / token 存取 / room_closed

**Files:**
- Modify: `frontend/src/hooks/useGameState.ts`（SeatInfo + is_owner；reclaim_token/room_closed 消息类型）
- Modify: `frontend/src/pages/GameTable.tsx`（token 存取与携带、Deal 权限、room_closed 处理）
- Modify: `frontend/src/components/table/OvalTable.tsx`（房主 👑 角标）
- Modify: `frontend/src/styles/game.css`

**Interfaces:**
- Consumes: seats.is_owner、私发 reclaim_token、广播 room_closed
- Produces: GameMsg + `{ type: 'reclaim_token'; token: string }` 与 `{ type: 'room_closed'; table_id: string }`

- [ ] **Step 1: useGameState.ts**

`SeatInfo` 加 `is_owner: boolean`。GameMsg union 加两个消息类型（见 Produces）。reducer 无需新分支（这两个消息在 GameTable 的 onMessage 里直接处理，不进 state）。

- [ ] **Step 2: GameTable.tsx**

onMessage switch 加：

```tsx
        case 'reclaim_token':
          localStorage.setItem(`reclaimToken_${tableId}`, m.token);
          break;
        case 'room_closed':
          alert('Room was closed due to inactivity');
          navigate('/');
          break;
```

joinTable 的 sit_down 消息带 token：

```tsx
    const reclaimToken = localStorage.getItem(`reclaimToken_${tableId}`);
    send({ type: 'sit_down', seat_idx: selectedSeat, name, buyin,
           ...(reclaimToken ? { reclaim_token: reclaimToken } : {}) });
```

Deal 按钮权限（牌桌视图）：

```tsx
  const isOwner = state.seats.find(s => s.seat_idx === state.mySeat)?.is_owner ?? false;
  ...
        <button className="btn btn-sm gold" onClick={() => send({ type: 'start_hand' })}
                disabled={!isOwner || (state.phase !== 'WAITING' && state.phase !== 'SHOWDOWN')}
                title={isOwner ? '' : 'Only the table owner can deal'}>
          Deal
        </button>
```

- [ ] **Step 3: OvalTable 房主角标**

seat-wrap 内、bot-badge 之外并列（人类房主才显示）：

```tsx
            {seat.is_owner && <span className="owner-crown">👑</span>}
```

- [ ] **Step 4: game.css 追加**

```css
/* ---- Owner crown ---- */
.owner-crown {
  position: absolute; top: -10px; left: -8px; font-size: 0.7rem;
  filter: drop-shadow(0 0 6px rgba(251, 191, 36, 0.7));
}
```

- [ ] **Step 5: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q   # 217 passed
cd .. && git add frontend/src
git commit -m "feat: owner crown, deal permission, reclaim token storage, room_closed

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 全量验证 + PR

- [ ] **Step 1: 全量验证**（后端 pytest + 前端 build/oxlint）
- [ ] **Step 2: 推送并开 PR**（HTTPS+token 备用通道；网络抖动重试）

PR 标题：`feat: 房主制 + 闲置房间回收 + 认领 token`
- [ ] **Step 3: 等 CI 绿，请用户确认后合入**
