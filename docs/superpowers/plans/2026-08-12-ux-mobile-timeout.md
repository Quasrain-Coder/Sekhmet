# 包 C：前端体验与托管 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 选座实时刷新、toast 替换 alert、移动端基础适配、连续超时自动离座。

**Spec:** `docs/superpowers/specs/2026-08-12-ux-mobile-timeout-design.md`

## Global Constraints

- 工作分支 `feat/ux-mobile-timeout`（spec 已提交）；禁止直接提交 main
- 后端测试：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`（当前 219 passed）
- 前端门禁：`cd frontend && npm run build && npx oxlint src` 绿
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- TDD：先写失败测试，看红，再实现

---

### Task 1: 后端 — 连续超时自动离座

**Files:**
- Modify: `backend/sekhmet/config.py`（+max_consecutive_timeouts）
- Modify: `backend/sekhmet/api/table_manager.py`（consecutive_timeouts、计数/清零、踢出、_expire_seat force 参数）
- Test: `backend/tests/test_tables.py`（追加）

**Interfaces:**
- Produces:
  - `GameConfig.max_consecutive_timeouts: int = 3`
  - `TableSession.consecutive_timeouts: dict[int, int]`
  - `_expire_seat(table_id, seat_idx, *, force: bool = False)`——force 跳过 disconnected 检查（超时踢出复用该路径）

- [ ] **Step 1: 写失败测试**

```python
async def test_consecutive_timeout_kicks_player(monkeypatch):
    """Hitting the timeout limit mid-hand: folded out and removed."""
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "action_timeout_seconds", 0.05)
    monkeypatch.setattr(tm.app_config.game, "max_consecutive_timeouts", 2)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    await asyncio.sleep(0.6)  # 两次超时（BB option + 翻后首条街）足够触发
    session = await tm.get_table(tid)
    assert session is not None
    assert 0 not in session.player_names          # 已踢出
    assert session.game_state.phase == GamePhase.SHOWDOWN  # 手牌善终
    assert sum(p.stack for p in session.game_state.players) == 400  # 守恒


async def test_manual_action_resets_timeout_counter():
    import random
    random.seed(7)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    session.consecutive_timeouts[0] = 1  # 预置计数
    await tm.auto_bot_actions(tid)       # bot 先行动（SB）
    await tm.handle_player_action(tid, 0, "CHECK")  # 人类主动行动
    assert session.consecutive_timeouts[0] == 0
```

（`GamePhase` 在 test_tables.py 已有 import——若无则补。）

- [ ] **Step 2: 确认红**

Run: `python -m pytest tests/test_tables.py -q -k timeout`
Expected: FAIL（consecutive_timeouts 不存在 / 踢出不发生）

- [ ] **Step 3: 实现**

`config.py`：`max_consecutive_timeouts: int = 3`

`table_manager.py`：

```python
# TableSession 加字段：
    consecutive_timeouts: dict[int, int] = field(default_factory=dict)
```

`_expire_seat` 签名与入口守卫改为：

```python
async def _expire_seat(table_id: str, seat_idx: int, *, force: bool = False) -> None:
    """Grace expired (or timeout-kicked): fold out of any running hand, then remove."""
    session = await get_table(table_id)
    if session is None or (not force and seat_idx not in session.disconnected):
        return
    session.disconnected.discard(seat_idx)
    ...
```

身份清理点（`_expire_seat` 的 finally 与 `stand_up`）加 `session.consecutive_timeouts.pop(seat_idx, None)`。

`handle_player_action`（execute 成功后）：`session.consecutive_timeouts[seat_idx] = 0`。

`_action_timeout` 在自动行动之后（after_action 之前）：

```python
    count = session.consecutive_timeouts.get(seat_idx, 0) + 1
    session.consecutive_timeouts[seat_idx] = count
    if count >= app_config.game.max_consecutive_timeouts:
        logger.info("seat %s kicked after %s consecutive timeouts at table %s",
                    seat_idx, count, table_id)
        await _expire_seat(table_id, seat_idx, force=True)
        return
```

注意时序：先 broadcast(msg) + after_action（手牌推进），再判定踢出；踢出内部再走广播。

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 219 + 2 = 221 passed
git add backend/
git commit -m "feat: kick players after consecutive action timeouts

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 前端 — Toast + 选座实时刷新

**Files:**
- Create: `frontend/src/components/shared/Toast.tsx`
- Modify: `frontend/src/pages/GameTable.tsx`（toast 状态、替换 alert、picker 实时数据源）
- Modify: `frontend/src/styles/game.css`

**Interfaces:**
- Produces:
  - `Toast({ items, onDismiss }: { items: ToastItem[]; onDismiss: (id: number) => void })`，`ToastItem = { id: number; kind: 'error' | 'info'; text: string }`
  - GameTable 内 `pushToast(kind, text)`；ws error 与 room_closed 走 toast
  - 选座图数据源：`liveSeats`（table_state 到达后优先）否则 REST detail

- [ ] **Step 1: Toast.tsx 新建**

```tsx
import { useEffect } from 'react';

export interface ToastItem {
  id: number;
  kind: 'error' | 'info';
  text: string;
}

interface Props {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}

export default function Toast({ items, onDismiss }: Props) {
  return (
    <div className="toast-stack">
      {items.map(t => (
        <ToastCard key={t.id} item={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(item.id), 3500);
    return () => clearTimeout(t);
  }, [item.id, onDismiss]);
  return (
    <div className={`toast toast-${item.kind}`} onClick={() => onDismiss(item.id)}>
      {item.text}
    </div>
  );
}
```

- [ ] **Step 2: GameTable.tsx 改造**

状态与挂载：

```tsx
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastId = useRef(0);
  const pushToast = useCallback((kind: 'error' | 'info', text: string) => {
    const id = ++toastId.current;
    setToasts(ts => [...ts, { id, kind, text }]);
  }, []);
  const dismissToast = useCallback((id: number) => {
    setToasts(ts => ts.filter(t => t.id !== id));
  }, []);
```

（`useRef`/`useState` import 补齐；`<Toast items={toasts} onDismiss={dismissToast} />` 挂在组件根部——join panel 和牌桌视图都要覆盖，放在两个 return 里或提到共享外层。）

替换所有 alert：
- `case 'error': alert(m.message)` → `pushToast('error', m.message)`
- joinTable 的 `alert('Table is full')` → `pushToast('error', 'Table is full')`
- `case 'room_closed'` → `pushToast('info', 'Room was closed due to inactivity'); setTimeout(() => navigate('/'), 1500);`

选座实时：

```tsx
  const [liveSeats, setLiveSeats] = useState<SeatInfo[] | null>(null);
  const [livePhase, setLivePhase] = useState<string | null>(null);
```
onMessage `case 'table_state'` 分支追加：`setLiveSeats(m.seats); setLivePhase(m.phase);`

join panel 里所有 `detail.seats` / `detail.phase` 的使用点改为：

```tsx
  const seatsNow = liveSeats ?? (detail && detail !== 'not-found' ? detail.seats : []);
  const phaseNow = livePhase ?? (detail && detail !== 'not-found' ? detail.phase : 'WAITING');
```

（picker 的 occ 查找、reclaimable、midHand 判定、房间信息行全部改用 seatsNow/phaseNow；detail 仍用于 config 展示。）

- [ ] **Step 3: game.css 追加**

```css
/* ---- Toast ---- */
.toast-stack {
  position: fixed; top: 16px; right: 16px; z-index: 100;
  display: flex; flex-direction: column; gap: 8px; max-width: 320px;
}
.toast {
  background: var(--surface); border-radius: 8px; padding: 10px 14px;
  font-size: 0.82rem; cursor: pointer;
  animation: toast-in 0.18s ease-out;
}
.toast-error { border: 1.5px solid var(--rose); color: #fecdd3; box-shadow: 0 0 14px rgba(251, 113, 133, 0.25); }
.toast-info { border: 1.5px solid var(--cyan); color: var(--cyan-text); box-shadow: 0 0 14px rgba(34, 211, 238, 0.25); }
@keyframes toast-in { from { transform: translateX(30px); opacity: 0; } }
```

- [ ] **Step 4: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q   # 221 passed
cd .. && git add frontend/src
git commit -m "feat: toast notifications, live seat picker

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 前端 — 移动端基础适配

**Files:**
- Modify: `frontend/src/styles/game.css`（仅追加媒体查询）

- [ ] **Step 1: game.css 追加**

```css
/* ---- Mobile (≤768px) ---- */
@media (max-width: 768px) {
  .app { padding: 8px; }

  /* Lobby：表单堆叠 */
  .lobby-actions { flex-direction: column; align-items: stretch; }
  .lobby-actions .btn { margin-left: 0; }
  .lobby-actions .input { width: 100%; }

  /* 牌桌：更小更扁 */
  .table-felt { aspect-ratio: 1.6 / 1; margin-bottom: 84px; }
  .player-seat .avatar { width: 32px; height: 32px; font-size: 0.5rem; }
  .player-seat.me .avatar { width: 38px; height: 38px; }
  .player-seat .name, .player-seat .stack { font-size: 0.55rem; }
  .card { width: 30px; height: 43px; }
  .card .pip { font-size: 0.9rem; }
  .card .corner { font-size: 0.45rem; }
  .card.big { width: 40px; height: 57px; }
  .card.big .pip { font-size: 1.2rem; }

  /* 动作栏：垂直堆叠，拇指友好 */
  .action-bar { flex-direction: column; align-items: stretch; width: 100%; }
  .action-bar .btn { width: 100%; padding: 12px; }
  .raise-slider { width: 100%; }

  /* 面板全宽 */
  .leaderboard, .hand-result, .join-panel { max-width: 100%; }
  .seat-picker { max-width: 320px; }
  .toast-stack { left: 16px; max-width: none; }
}
```

- [ ] **Step 2: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd .. && git add frontend/src/styles/game.css
git commit -m "feat: mobile responsive layout (≤768px)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 全量验证 + PR

- [ ] **Step 1: 全量验证**（后端 221 passed + 前端 build/oxlint）
- [ ] **Step 2: 推送并开 PR**（HTTPS+token 备用通道）

PR 标题：`feat: toast 通知 + 选座实时 + 移动端适配 + 连续超时离座`
- [ ] **Step 3: 等 CI 绿，请用户确认后合入**
