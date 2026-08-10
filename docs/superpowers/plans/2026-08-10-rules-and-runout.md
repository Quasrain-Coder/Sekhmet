# 包 A：规则与牌局完整性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 盲注顺延（死盲注/稀疏座位修复）、all-in runout 逐街广播、位置标记 D/SB/BB。

**Architecture:** 引擎盲注分配改为"按钮后有筹码者顺延"并记录 sb_seat/bb_seat 进 GameState；runout 从原子跳跃改为逐街 `_advance_phase` + 公开 `runout_step`；桌层在 `auto_bot_actions` 内逐街广播（可配置延迟）；前端座位头像旁渲染位置徽章。

**Tech Stack:** FastAPI + pytest；React 19 + Vite。

**Spec:** `docs/superpowers/specs/2026-08-10-rules-and-runout-design.md`

## Global Constraints

- 工作分支 `feat/rules-and-runout`（spec 已提交）；禁止直接提交 main
- 后端测试：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`（当前 204 passed）
- 前端门禁：`cd frontend && npm run build && npx oxlint src` 绿
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- TDD：先写失败测试，看红，再实现
- GameState 新增字段（sb_seat/bb_seat）时，所有构造函数点（with_players/with_phase/execute/_advance/_advance_phase/deal_new_hand）都必须携带——参照 acted_seats 的前例

---

### Task 1: 引擎 — 盲注顺延（死盲注 + 稀疏座位）

**Files:**
- Modify: `backend/sekhmet/game_engine/action_processor.py`（deal_new_hand 盲注分配）
- Test: `backend/tests/test_action_processor.py`（改 1 + 新增 2）

**Interfaces:**
- Produces: deal_new_hand 中 sb_seat/bb_seat 的新语义——按钮位之后**有筹码**的玩家顺时针顺延；对调用方透明

**背景（brief 之外）**：现实现 `sb_seat = (dealer_idx + 1) % n`（n = len(players)）有两个问题：0 筹码玩家仍被分盲注位（死盲注收不到）；选座功能上线后座位号可能不连续（如 0 和 3），`% n` 直接算错。

- [ ] **Step 1: 改/写失败测试**

把 `test_deal_skips_zero_stack_player` 的底池断言从 10 改为 15（SB 顺延到 seat 2 缴 5、BB 落到 seat 0 缴 10），注释更新为"SB/BB 顺延给有筹码玩家"。新增：

```python
def test_blinds_skip_busted_and_sparse_seats():
    """Blinds rotate over players WITH CHIPS, across sparse seat indices."""
    p1 = make_player("A", 0, stack=200)   # dealer
    p2 = make_player("B", 2, stack=0)     # busted, sparse seat
    p3 = make_player("C", 5, stack=200)   # sparse seat
    state = GameState(
        phase=GamePhase.WAITING,
        players=(p1, p2, p3),
        dealer_idx=0, small_blind=5, big_blind=10,
    )
    deck = Deck(); deck.shuffle()
    s = deal_new_hand(state, deck.cards[:], dealer_idx=0)

    # 2 live players (seats 0 and 5) → HU blinds: dealer(0)=SB 5, seat 5=BB 10
    assert s.player(0).total_bet == 5
    assert s.player(5).total_bet == 10
    assert s.player(2).total_bet == 0
    assert s.pot.main_pot == 15
    # HU first to act preflop = SB (seat 0)
    assert s.current_player_idx == 0


def test_blinds_three_live_sparse_seats():
    p1 = make_player("A", 1, stack=200)
    p2 = make_player("B", 3, stack=200)
    p3 = make_player("C", 4, stack=200)
    state = GameState(
        phase=GamePhase.WAITING,
        players=(p1, p2, p3),
        dealer_idx=1, small_blind=5, big_blind=10,
    )
    deck = Deck(); deck.shuffle()
    s = deal_new_hand(state, deck.cards[:], dealer_idx=1)

    # dealer=1 → SB=3, BB=4, first to act = seat 1 (left of BB, wraps)
    assert s.player(3).total_bet == 5
    assert s.player(4).total_bet == 10
    assert s.current_player_idx == 1
```

- [ ] **Step 2: 确认红**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_action_processor.py -q -k "blinds or zero_stack"`
Expected: FAIL（`% n` 逻辑在稀疏座位上错位 / 死盲注断言不符）

- [ ] **Step 3: 实现 deal_new_hand 盲注段替换**

```python
    # Blinds rotate clockwise over players WITH CHIPS (busted players sit
    # out; a busted blind seat is dead and the blind moves on).  Seat
    # indices may be sparse (custom seat picker), so rotate over the
    # actual live seat list, never modulo len(players).
    live_seats = sorted(p.seat_idx for p in state.players if p.stack > 0)

    def _after(seat: int) -> int:
        """First live seat clockwise after *seat* (wraps)."""
        for s in live_seats:
            if s > seat:
                return s
        return live_seats[0]

    if len(live_seats) == 2:
        # HU: dealer is SB when they have chips; otherwise first live seat
        # after the (dead) button.
        sb_seat = dealer_idx if dealer_idx in live_seats else _after(dealer_idx)
        bb_seat = _after(sb_seat)
    else:
        sb_seat = _after(dealer_idx)
        bb_seat = _after(sb_seat)
```

（替换现有 `n = len(state.players)` 与 if n == 2 的 sb/bb 计算段；后续发牌循环、pot、first_to_act 逻辑不变。）

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 204 + 1 = 205 passed（1 改 2 新增净 +1... 以实际为准）
git add backend/sekhmet/game_engine/action_processor.py backend/tests/test_action_processor.py
git commit -m "feat: blinds rotate to players with chips (dead blind + sparse seats)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 引擎 — runout 逐街推进

**Files:**
- Modify: `backend/sekhmet/game_engine/action_processor.py`（_advance、_advance_phase、删 _runout、+runout_step）
- Test: `backend/tests/test_full_hand.py`（三个 runout 测试改逐街）、`backend/tests/test_action_processor.py`（test_players_all_in_goes_to_showdown 改断言）

**Interfaces:**
- Produces: `runout_step(state: GameState) -> GameState`（公开）——在下注阶段且无人能行动时推进一条街；`current_player_idx is None` 表示"等待继续 runout"

- [ ] **Step 1: 改失败测试**

`test_full_hand.py` 的 `test_all_in_runout_heads_up` 改为：

```python
def test_all_in_runout_heads_up():
    """Both players all-in preflop → streets deal one at a time to showdown."""
    state = deal(waiting_state(
        make_player("SB", 0, stack=200),
        make_player("BB", 1, stack=200),
        dealer_idx=0,
    ))
    state = act(state, 0, ActionType.ALL_IN)
    state = act(state, 1, ActionType.CALL)

    # No one can act — the engine deals ONE street and waits (current=None)
    assert state.phase == GamePhase.FLOP
    assert len(state.community_cards) == 3
    assert state.current_player_idx is None

    from sekhmet.game_engine.action_processor import runout_step
    state = runout_step(state)
    assert state.phase == GamePhase.TURN and len(state.community_cards) == 4
    state = runout_step(state)
    assert state.phase == GamePhase.RIVER and len(state.community_cards) == 5
    state = runout_step(state)
    assert state.phase == GamePhase.SHOWDOWN
    assert len(state.deck) + 5 + 4 == 52
```

`test_runout_when_one_player_still_has_chips` 与 `test_side_pots_with_uneven_all_ins` 同样改：all-in 落定后 `while state.phase != GamePhase.SHOWDOWN: state = runout_step(state)`，保留原有断言（牌面 5 张、分池金额、守恒）。

`test_action_processor.py::test_players_all_in_goes_to_showdown` 断言改为：

```python
    state = execute(state, Action(1, ActionType.CHECK))
    # 无人能行动 → 推进一条街并等待 runout（不再是直接摊牌）
    assert state.phase == GamePhase.FLOP
    assert state.current_player_idx is None
```

- [ ] **Step 2: 确认红**

Run: `python -m pytest tests/test_full_hand.py tests/test_action_processor.py -q`
Expected: FAIL（当前原子 runout 直接到 SHOWDOWN / runout_step 不存在）

- [ ] **Step 3: 实现**

`action_processor.py`：

1. `_advance` 中 `if _count_players_who_can_act(state.players) <= 1: return _runout(state)` → `return _advance_phase(state)`；`next_seat is None` 分支同样改为 `return _advance_phase(state)`
2. `_advance_phase` 的 first_to_act 计算：

```python
    # No more betting is possible with ≤1 actor — signal "runout pending"
    # with current_player_idx=None instead of offering a phantom turn.
    if _count_players_who_can_act(players) <= 1:
        first_to_act = None
    else:
        n_seats = max((p.seat_idx + 1 for p in players), default=0)
        first_to_act = _next_active_seat(players, state.dealer_idx, n_seats)
```

3. 删除 `_runout` 函数；新增公开函数：

```python
def runout_step(state: GameState) -> GameState:
    """Advance one street during an all-in runout (nobody left to act).

    The table layer calls this in a loop (broadcasting each street) until
    the state reaches SHOWDOWN.
    """
    if state.phase in (GamePhase.WAITING, GamePhase.DEALING, GamePhase.SHOWDOWN):
        raise PhaseError(f"Cannot run out from {state.phase.name}")
    return _advance_phase(state)
```

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q
git add backend/sekhmet/game_engine/action_processor.py backend/tests/
git commit -m "feat: stepwise engine runout via public runout_step

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 桌层 — 逐街广播 + 延迟 + sb/bb_seat 广播字段

**Files:**
- Modify: `backend/sekhmet/config.py`（+runout_delay_seconds）
- Modify: `backend/sekhmet/game_engine/game_state.py`（+sb_seat/bb_seat 字段与携带）
- Modify: `backend/sekhmet/game_engine/action_processor.py`（构造点携带新字段；deal_new_hand 设置）
- Modify: `backend/sekhmet/api/table_manager.py`（auto_bot_actions runout 分支；_state_broadcast/_hand_start_broadcast + sb_seat/bb_seat）
- Test: `backend/tests/test_tables.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `runout_step`
- Produces:
  - `GameState.sb_seat: int | None = None`、`GameState.bb_seat: int | None = None`
  - `GameConfig.runout_delay_seconds: float = 0.8`
  - 广播消息（game_state_update / hand_start / hand_result）+ `sb_seat` + `bb_seat`

- [ ] **Step 1: 写失败测试**

```python
def test_all_in_runout_broadcasts_each_street(monkeypatch):
    """All-in then call → clients see FLOP(3) → TURN(4) → RIVER(5) → result."""
    monkeypatch.setattr(tm.app_config.game, "runout_delay_seconds", 0)
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "A", "buyin": 200})
        ws1.receive_json()
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "B", "buyin": 200})
        ws2.receive_json(); ws1.receive_json()
        ws1.send_json({"type": "start_hand"})
        # 读到轮到我（seat 0，SB/dealer 先手）
        while True:
            msg = ws1.receive_json()
            if msg.get("current_player_idx") == 0:
                break
        ws1.send_json({"type": "player_action", "action": "ALL_IN"})
        # 等 seat 1 被问（ws2 是人类座位，手动 call）
        while True:
            msg = ws2.receive_json()
            if msg.get("current_player_idx") == 1:
                break
        ws2.send_json({"type": "player_action", "action": "CALL"})

        # 现在应逐街收到广播：3 张 → 4 张 → 5 张 → hand_result
        boards = []
        for _ in range(20):
            msg = ws1.receive_json()
            if msg["type"] == "game_state_update":
                boards.append(len(msg["community_cards"]))
            if msg["type"] == "hand_result":
                break
        assert boards == [3, 4, 5]
        # 位置字段
        assert msg["sb_seat"] is not None and msg["bb_seat"] is not None
```

注意：hand_start 后 ws1 是 dealer(1)→SB…… 两手玩家的按钮推进：初始 dealer=0 → 推进到 1；seat 1 = SB/dealer 先手。测试里 ws1(seat0) 未必先手——上面的"读到轮到我"循环处理了不确定性，但 ALL_IN 的座位必须是当前行动者。实现者注意按实际 current_player_idx 驱动（谁轮到谁 ALL_IN，另一方 CALL），断言 boards == [3,4,5] 不变。

- [ ] **Step 2: 确认红**（boards 序列不会出现 / 无 sb_seat 字段）

- [ ] **Step 3: 实现**

`config.py`：`runout_delay_seconds: float = 0.8`

`game_state.py`：`GameState` 加 `sb_seat: int | None = None`、`bb_seat: int | None = None`；`with_players`/`with_phase` 携带（with_phase 保留原值——街道切换不清盲注位）。

`action_processor.py`：所有 `GameState(...)` 构造点携带 `sb_seat=state.sb_seat, bb_seat=state.bb_seat`；`deal_new_hand` 返回时设置 `sb_seat=sb_seat, bb_seat=bb_seat`。

`table_manager.py` — `auto_bot_actions` 循环内、`cur_idx is None` 的 break 之前插入 runout 分支：

```python
        cur_idx = gs.current_player_idx
        if cur_idx is None:
            if gs.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
                break
            # All-in runout: deal the next street and broadcast it live.
            session.game_state = runout_step(gs)
            gs = session.game_state
            if gs.phase == GamePhase.SHOWDOWN:
                result = _resolve_showdown(session)
                broadcasts.append(_state_broadcast(session, result))
                break
            broadcasts.append(_state_broadcast(session))
            await asyncio.sleep(app_config.game.runout_delay_seconds)
            continue
```

（`runout_step` 加入 `..game_engine` 的 import；`app_config` 已在。另：`auto_bot_actions` 的 `max_iterations = 20` 上调到 40——runout 每条街消耗一次迭代，多人桌全 all-in 时 20 可能不够。）

`_state_broadcast` 与 `_hand_start_broadcast` 加：

```python
        "sb_seat": gs.sb_seat,
        "bb_seat": gs.bb_seat,
```

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q
git add backend/
git commit -m "feat: broadcast all-in runout street by street, sb/bb seats in broadcasts

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 前端 — 位置徽章（D / SB / BB）

**Files:**
- Modify: `frontend/src/hooks/useGameState.ts`（state + dealerIdx/sbSeat/bbSeat）
- Modify: `frontend/src/components/table/OvalTable.tsx`（透传徽章）
- Modify: `frontend/src/components/table/PlayerSeat.tsx`（渲染徽章）
- Modify: `frontend/src/styles/game.css`

**Interfaces:**
- Consumes: 广播的 dealer_idx（已有）/ sb_seat / bb_seat
- Produces: reducer state + `dealerIdx: number | null`、`sbSeat: number | null`、`bbSeat: number | null`（HAND_START/GAME_UPDATE 填充）

- [ ] **Step 1: useGameState.ts**

GameStateData 与 HandStartData 加 `sb_seat: number | null; bb_seat: number | null`；AppState 加 `dealerIdx: number | null; sbSeat: number | null; bbSeat: number | null`（initial 全 null）；HAND_START 与 GAME_UPDATE 分支填充：

```typescript
        dealerIdx: action.data.dealer_idx ?? null,
        sbSeat: action.data.sb_seat ?? null,
        bbSeat: action.data.bb_seat ?? null,
```

（HAND_START 分支已有 dealer_idx 字段。）

- [ ] **Step 2: PlayerSeat 徽章**

Props 加 `positionTag?: 'D' | 'SB' | 'BB'`；avatar 旁渲染：

```tsx
      <div className="avatar">{avatarLabel}
        {positionTag && <span className={`pos-tag pos-${positionTag.toLowerCase()}`}>{positionTag}</span>}
      </div>
```

- [ ] **Step 3: OvalTable 透传**

Props 加 `dealerIdx/sbSeat/bbSeat: number | null`；对每个座位计算：

```tsx
        const tag = seat.seat_idx === dealerIdx ? 'D'
          : seat.seat_idx === sbSeat ? 'SB'
          : seat.seat_idx === bbSeat ? 'BB'
          : undefined;
```

传给 PlayerSeat 的 positionTag。GameTable.tsx 调用处从 state 传入三个新 prop。

- [ ] **Step 4: game.css 追加**

```css
/* ---- Position tags (D / SB / BB) ---- */
.pos-tag {
  position: absolute; top: -4px; left: -6px;
  font-size: 0.55rem; font-weight: 800; padding: 1px 5px; border-radius: 7px;
  background: var(--surface); border: 1px solid var(--cyan); color: var(--cyan-text);
}
.pos-tag.pos-d { border-color: var(--gold); color: var(--gold-text); }
```

（`.avatar` 已是 position:relative。与 bot-badge 分居左右上角，不冲突。）

- [ ] **Step 5: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q
cd .. && git add frontend/src
git commit -m "feat: dealer/SB/BB position tags on seats

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 全量验证 + PR

- [ ] **Step 1: 全量验证**（后端 pytest + 前端 build/oxlint）
- [ ] **Step 2: 推送并开 PR**（HTTPS+token 备用通道；网络抖动重试）

PR 标题：`feat: 盲注顺延 + all-in runout 逐街广播 + 位置标记`
- [ ] **Step 3: 等 CI 绿，请用户确认后合入**
