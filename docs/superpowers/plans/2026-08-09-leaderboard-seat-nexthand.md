# 排行榜 / 自定义选座 / 下一局开关 + 头像挡牌修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 房间内排行榜（内存版）、确认页点选座位、摊牌后显式 Next Hand 按钮，并修复霓虹重设计的"头像挡牌"视觉回归。

**Architecture:** 后端在 `TableSession` 加内存 stats 并随 `table_info` 的 seats 明细暴露（兼容式加字段）；前端 GameTable 加排行榜面板与 Next Hand 按钮，确认页加选座示意图。

**Tech Stack:** FastAPI + pytest；React 19 + Vite。

**Spec:** `docs/superpowers/specs/2026-08-09-leaderboard-seat-next-hand-design.md`

## Global Constraints

- 工作分支 `feat/leaderboard-seat-nexthand`（spec 已提交）；禁止直接提交 main
- 后端测试：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`（当前 184 passed）
- 前端门禁：`cd frontend && npm run build && npx oxlint src` 绿
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- seats 明细加字段是兼容式变更；但 `tests/test_e2e_game_journey.py` 有 seats **全等断言**，必须同步更新
- seat-wrap 锚定机制（PR #10/#12 的不变量）不得破坏：seat-wrap 持 seat-N 绝对定位；内层 .player-seat 为 relative（#12 修复后）且无 seat-N 类
- TDD：先写失败测试，看红，再实现

---

### Task 1: 后端 — 房间内 stats 追踪

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`
- Test: `backend/tests/test_tables.py`（追加）
- Modify: `backend/tests/test_e2e_game_journey.py`（seats 全等断言同步）

**Interfaces:**
- Consumes: 现有 `start_hand`、`_resolve_showdown`、`sit_down`、`stand_up`、`table_info`
- Produces:
  - `@dataclass class PlayerStats: hands: int = 0; wins: int = 0`（table_manager 模块级）
  - `TableSession.stats: dict[int, PlayerStats]`、`TableSession.total_buyin: dict[int, int]`
  - `table_info` 的 seats 明细新增字段：`hands: int`、`wins: int`、`net_chips: int`（= stack − total_buyin）

- [ ] **Step 1: 写失败测试**（追加到 `backend/tests/test_tables.py`）

```python
async def test_stats_accumulate_over_a_hand():
    """Hands/wins/net_chips tracked per seat and exposed via table_info."""
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)

    session = await tm.get_table(tid)
    assert session is not None
    sb_seat = session.game_state.current_player_idx  # HU: SB acts first

    # SB folds → BB wins the 15 pot (blinds 5+10)
    await tm.handle_player_action(tid, sb_seat, "FOLD")

    session = await tm.get_table(tid)
    info = tm.table_info(session)
    seats = {s["seat_idx"]: s for s in info["seats"]}
    assert seats[0]["hands"] == 1 and seats[1]["hands"] == 1
    winner = 1 - sb_seat
    loser = sb_seat
    assert seats[winner]["wins"] == 1 and seats[loser]["wins"] == 0
    assert seats[winner]["net_chips"] == 5    # 205 - 200
    assert seats[loser]["net_chips"] == -5    # 195 - 200


async def test_stats_cleared_on_stand_up():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.stand_up(tid, 1)
    session = await tm.get_table(tid)
    assert session is not None
    assert 1 not in session.stats and 1 not in session.total_buyin


async def test_wins_and_hands_accumulate_over_multiple_hands():
    """Two fold-out hands: every seated player gains hands, winners gain wins."""
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    for _ in range(2):
        await tm.start_hand(tid)
        session = await tm.get_table(tid)
        sb = session.game_state.current_player_idx
        await tm.handle_player_action(tid, sb, "FOLD")
    session = await tm.get_table(tid)
    info = tm.table_info(session)
    assert sum(s["wins"] for s in info["seats"]) == 2
    assert sum(s["hands"] for s in info["seats"]) == 4


def test_ws_table_state_broadcast_on_hand_end():
    """Stats ride the table_state broadcast — it must follow hand_result,
    or the leaderboard would only refresh on sit/stand."""
    import random
    random.seed(7)
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200,
                      "is_human": False})
        ws.send_json({"type": "start_hand"})

        saw_hand_result = False
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] == "hand_result":
                saw_hand_result = True
                continue
            if saw_hand_result and msg["type"] == "table_state":
                seats = {s["seat_idx"]: s for s in msg["seats"]}
                assert sum(s["hands"] for s in seats.values()) == 2
                assert sum(s["wins"] for s in seats.values()) == 1
                return
            cur = msg.get("current_player_idx")
            if msg["type"] in ("game_state_update", "hand_start") and cur == 0:
                ws.send_json({"type": "player_action", "action": "FOLD"})
        raise AssertionError("no table_state followed the hand_result")
```

`test_e2e_game_journey.py` 的全等断言（第 3 步入座后的 `assert ts["seats"] == [...]`）同步加入新字段：

```python
        assert ts["seats"] == [{
            "seat_idx": 0, "name": "Hero", "is_human": True,
            "bot_level": None, "stack": 2000,
            "hands": 0, "wins": 0, "net_chips": 0,
        }]
```

- [ ] **Step 2: 跑测试确认红**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tables.py -q -k stats`
Expected: FAIL（`AttributeError: stats` / KeyError hands 等）；e2e 旅程测试也会因 seats 全等断言失败（预期）

- [ ] **Step 3: 实现**

`table_manager.py`：

```python
@dataclass
class PlayerStats:
    """Per-seat in-memory stats for the room leaderboard (resets on stand_up)."""
    hands: int = 0
    wins: int = 0
```

`TableSession` 加两个字段：

```python
    stats: dict[int, PlayerStats] = field(default_factory=dict)      # seat_idx → stats
    total_buyin: dict[int, int] = field(default_factory=dict)        # seat_idx → chips bought
```

`sit_down`（在 player 加入 game_state 之后）：

```python
    session.stats[seat_idx] = PlayerStats()
    session.total_buyin[seat_idx] = stack
```

`stand_up` 加清理：

```python
    session.stats.pop(seat_idx, None)
    session.total_buyin.pop(seat_idx, None)
```

`start_hand`（deal_new_hand 成功之后）：

```python
    for p in session.game_state.players:
        if p.seat_idx in session.stats:
            session.stats[p.seat_idx].hands += 1
```

`_resolve_showdown`（awards 计算之后）：

```python
    for award in awards_list:
        if award.winner_seat_idx in session.stats:
            session.stats[award.winner_seat_idx].wins += 1
```

`table_info` 的 seats 明细构造处加字段：

```python
        st = session.stats.get(seat)
        buyin = session.total_buyin.get(seat, p.stack if p is not None else 0)
        seats.append({
            "seat_idx": seat,
            "name": name,
            "is_human": p.is_human if p is not None else True,
            "bot_level": session.bot_levels.get(seat),
            "stack": p.stack if p is not None else 0,
            "hands": st.hands if st else 0,
            "wins": st.wins if st else 0,
            "net_chips": (p.stack if p is not None else 0) - buyin,
        })
```

**ws.py——手牌结束后补发 table_state**（否则 stats 只在入座/离座时刷新，排行榜会过期）。`player_action` 分支和 `start_hand` 分支的 bot_msgs 广播循环之后，各加：

```python
                    # Leaderboard stats changed with the hand result —
                    # push a fresh table_state so clients see them.
                    session = await tm.get_table(table_id)
                    if session and session.game_state.phase in (
                        GamePhase.WAITING, GamePhase.SHOWDOWN,
                    ):
                        await tm.broadcast(table_id, tm._table_summary(session))
```

放在两处：（1）`player_action` 分支——`handle_player_action` 广播 + bot_msgs 广播之后；（2）`start_hand` 分支的 bot_msgs 广播之后（bot 可能在第一手自动打完整手，不可能——开局不会直接摊牌；但 fold-out 会发生在 player_action 之后。统一加在两处兜底）。`GamePhase` 已在 Task 2（房间配置）中引入 ws.py 的 import；若无则补上。

- [ ] **Step 4: 跑测试确认绿**

Run: `python -m pytest tests/test_tables.py tests/test_e2e_game_journey.py -q`
Expected: 全绿

- [ ] **Step 5: 全量回归 + 提交**

```bash
python -m pytest tests/ -q   # 184 + 4 新 = 188 passed
git add backend/sekhmet/api/table_manager.py backend/sekhmet/api/ws.py backend/tests/test_tables.py backend/tests/test_e2e_game_journey.py
git commit -m "feat: per-seat room stats (hands/wins/net_chips) for leaderboard

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 前端 — 排行榜面板 + Next Hand 按钮 + 头像挡牌修复

**Files:**
- Modify: `frontend/src/hooks/useGameState.ts`（SeatInfo 加三字段）
- Create: `frontend/src/components/table/Leaderboard.tsx`
- Modify: `frontend/src/pages/GameTable.tsx`（面板挂载 + Next Hand 按钮）
- Modify: `frontend/src/styles/game.css`（排行榜样式 + 头像挡牌修复）

**Interfaces:**
- Consumes: Task 1 的 seats 新字段（hands/wins/net_chips）
- Produces:
  - `SeatInfo` 增加 `hands: number; wins: number; net_chips: number`
  - `Leaderboard({ seats }: { seats: SeatInfo[] })`——可折叠面板，默认折叠
  - 挡牌修复：`.player-seat.me .cards` 绝对定位挂座位盒下沿外

- [ ] **Step 1: useGameState.ts — SeatInfo 加字段**

```typescript
export interface SeatInfo {
  seat_idx: number;
  name: string;
  is_human: boolean;
  bot_level: number | null;
  stack: number;
  hands: number;
  wins: number;
  net_chips: number;
}
```

- [ ] **Step 2: Leaderboard.tsx 新建**

```tsx
import { useState } from 'react';
import type { SeatInfo } from '../../hooks/useGameState';

interface Props {
  seats: SeatInfo[];
}

export default function Leaderboard({ seats }: Props) {
  const [open, setOpen] = useState(false);
  const ranked = [...seats].sort((a, b) => b.net_chips - a.net_chips);

  return (
    <div className="leaderboard">
      <button className="lb-toggle" onClick={() => setOpen(!open)}>
        🏆 Leaderboard {open ? '▾' : '▸'}
      </button>
      {open && (
        <table className="lb-table">
          <thead>
            <tr><th>#</th><th>Player</th><th>Hands</th><th>Wins</th><th>Win%</th><th>Net</th></tr>
          </thead>
          <tbody>
            {ranked.map((s, i) => (
              <tr key={s.seat_idx}>
                <td>{i + 1}</td>
                <td>{s.name}{!s.is_human && <span className="lb-bot"> L{s.bot_level ?? 2}</span>}</td>
                <td>{s.hands}</td>
                <td>{s.wins}</td>
                <td>{s.hands > 0 ? Math.round((s.wins / s.hands) * 100) : 0}%</td>
                <td className={s.net_chips >= 0 ? 'lb-pos' : 'lb-neg'}>
                  {s.net_chips >= 0 ? '+' : ''}{s.net_chips}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 3: GameTable.tsx 挂载**

牌桌视图 return 中，`<OvalTable ... />` 之后加：

```tsx
      <Leaderboard seats={state.seats} />
```

（顶部 import Leaderboard。）摊牌面板（`.hand-result` 块）内、awards 列表之后加：

```tsx
          {state.phase === 'SHOWDOWN' && (
            <button className="btn gold next-hand"
                    onClick={() => send({ type: 'start_hand' })}>
              Next Hand
            </button>
          )}
```

- [ ] **Step 4: game.css 追加**

```css
/* ---- Leaderboard ---- */
.leaderboard { width: 100%; max-width: 780px; }
.lb-toggle {
  background: transparent; border: 1.5px solid var(--cyan-dim); color: var(--cyan-text);
  border-radius: 6px; padding: 5px 14px; font-size: 0.75rem; cursor: pointer;
}
.lb-toggle:hover { border-color: var(--cyan); box-shadow: 0 0 10px rgba(34, 211, 238, 0.3); }
.lb-table {
  width: 100%; margin-top: 8px; border-collapse: collapse;
  background: var(--surface); border: 1px solid var(--cyan-dim); border-radius: 8px;
  font-size: 0.78rem;
}
.lb-table th {
  text-align: left; padding: 7px 12px; color: var(--cyan-text);
  font-size: 0.65rem; letter-spacing: 1px; text-transform: uppercase;
  border-bottom: 1px solid var(--cyan-dim);
}
.lb-table td { padding: 6px 12px; border-bottom: 1px solid rgba(22, 78, 99, 0.4); }
.lb-table tr:last-child td { border-bottom: none; }
.lb-bot { color: var(--purple); font-size: 0.7rem; }
.lb-pos { color: var(--gold-text); font-weight: 700; }
.lb-neg { color: var(--text-dim); }
.next-hand { margin-top: 10px; width: 100%; }

/* 头像挡牌修复：我的手牌挂到座位盒下沿之外，不再向上撑高压住公共牌 */
.player-seat.me .cards {
  position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
  margin-top: 6px;
}
/* 给悬出的手牌留出页面空间 */
.table-felt { margin-bottom: 70px; }
```

（`.player-seat` 已是 `position: relative`——PR #12 修复后的状态，手牌绝对定位锚定到它。）

- [ ] **Step 5: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q   # 188 passed
cd .. && git add frontend/src
git commit -m "feat: leaderboard panel, next-hand button, fix avatar covering board

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 前端 — 确认页选座示意图

**Files:**
- Modify: `frontend/src/pages/GameTable.tsx`（join panel 加选座图）
- Modify: `frontend/src/styles/game.css`（选座样式）

**Interfaces:**
- Consumes: REST detail（seats/max_seats）；现有 `seat-0..8` 定位类
- Produces: join panel 新增 `selectedSeat` 状态（默认第一个空位）；`joinTable` 使用选中座位

- [ ] **Step 1: GameTable.tsx 修改**

join panel 状态区加：

```tsx
  const [selectedSeat, setSelectedSeat] = useState<number | null>(null);
```

detail 加载完成后默认选第一个空位（修改现有 detail useEffect 的 then 分支）：

```tsx
      .then((d: TableDetail) => {
        setDetail(d);
        setBuyin(d.config.default_buyin);
        const taken = new Set(d.seats.map(s => s.seat_idx));
        const free = Array.from({ length: d.max_seats }, (_, i) => i).find(i => !taken.has(i));
        setSelectedSeat(free ?? null);
      })
```

joinTable 改用选中座位（替换 first-free 计算）：

```tsx
  const joinTable = () => {
    if (!detail || detail === 'not-found' || selectedSeat === null) return;
    localStorage.setItem('pokerName', name);
    send({ type: 'sit_down', seat_idx: selectedSeat, name, buyin });
    dispatch({ type: 'SET_MY_SEAT', seat: selectedSeat });
  };
```

入座表单上方插入选座示意图（在 room-meta 段落之后、输入框之前）：

```tsx
        <div className="seat-picker">
          {Array.from({ length: detail.max_seats }, (_, i) => {
            const occ = detail.seats.find(s => s.seat_idx === i);
            return (
              <button
                key={i}
                className={`picker-seat seat-${i}${occ ? ' taken' : ''}${selectedSeat === i ? ' selected' : ''}`}
                disabled={!!occ}
                title={occ ? occ.name : `Seat ${i}`}
                onClick={() => setSelectedSeat(i)}
              >
                {occ ? occ.name.charAt(0) : i}
              </button>
            );
          })}
        </div>
```

Sit Down 按钮的 disabled 条件加 `selectedSeat === null`。

- [ ] **Step 2: game.css 追加**

```css
/* ---- Seat picker (join panel) ---- */
.seat-picker {
  position: relative; aspect-ratio: 2.35 / 1; max-width: 420px; margin: 14px auto;
  border: 1.5px dashed var(--cyan-dim); border-radius: 999px;
}
.picker-seat {
  position: absolute; width: 34px; height: 34px; border-radius: 50%;
  background: var(--surface); border: 1.5px solid var(--cyan-dim); color: var(--cyan-text);
  font-size: 0.7rem; font-weight: 600; cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.picker-seat:hover:not(:disabled) { border-color: var(--cyan); box-shadow: 0 0 10px rgba(34, 211, 238, 0.4); }
.picker-seat.taken { opacity: 0.45; cursor: not-allowed; }
.picker-seat.selected {
  border-color: var(--gold); color: var(--gold-text);
  box-shadow: 0 0 12px rgba(251, 191, 36, 0.55);
}
```

（`.picker-seat` 复用全局 `seat-0..8` 定位类——picker 容器是缩放版桌面，百分比定位天然适用。）

- [ ] **Step 3: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q
cd .. && git add frontend/src
git commit -m "feat: seat picker in join panel

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 全量验证 + PR

- [ ] **Step 1: 全量验证**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -q   # 188 passed
cd ../frontend && npm run build && npx oxlint src
```

- [ ] **Step 2: 推送并开 PR**（网络抖动时用 HTTPS+token 备用通道）

PR 标题：`feat: 排行榜 + 自定义选座 + 摊牌 Next Hand + 头像挡牌修复`
- [ ] **Step 3: 等 CI 绿，请用户确认后合入**（项目铁律：不自行 merge）
