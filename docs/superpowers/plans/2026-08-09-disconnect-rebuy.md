# 断线宽限重连 / 行动超时 / 爆掉重买 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 断线 60s 宽限 + 按名重连认领、30s 行动超时自动 check/fold、宽限期满安全移除、爆掉（0 筹码）重买。

**Architecture:** 计时器（宽限/行动超时）均为挂在 `TableSession` 上的 asyncio task；ws 断连从"立即离座"改为"标记+宽限"；重连认领走 sit_down 前的 try_reclaim 分支；广播/bot 驱动/统计刷新/计时器重排收敛为 tm 层 `after_action` 单一入口。

**Tech Stack:** FastAPI + pytest（asyncio_mode=auto）；React 19 + Vite。

**Spec:** `docs/superpowers/specs/2026-08-09-disconnect-rebuy-design.md`

## Global Constraints

- 工作分支 `feat/disconnect-rebuy`（spec 已提交）；禁止直接提交 main
- 后端测试：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`（当前 189 passed）
- 前端门禁：`cd frontend && npm run build && npx oxlint src` 绿
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- TDD：先写失败测试，看红，再实现
- seats 明细加 `connected` 字段是兼容式变更，但 `tests/test_e2e_game_journey.py` 的 seats 全等断言要同步
- 计时器在测试里通过 monkeypatch 配置值缩短（`tm.app_config.game.disconnect_grace_seconds` / `action_timeout_seconds`），不得写死短值
- 引擎不可变状态机纪律：除"强制弃牌"外不直接改 GameState 内部

---

### Task 1: 引擎 — deal_new_hand 跳过 0 筹码玩家

**Files:**
- Modify: `backend/sekhmet/game_engine/action_processor.py`（deal_new_hand）
- Test: `backend/tests/test_action_processor.py`（追加）

**Interfaces:**
- Consumes: 现有 `deal_new_hand(state, deck_cards, dealer_idx)`
- Produces: stack==0 的玩家不发底牌、不收盲注、保持 `is_active=False`；人数检查改为"stack>0 的玩家 ≥ 2"

- [ ] **Step 1: 写失败测试**（追加到 test_action_processor.py）

```python
def test_deal_skips_zero_stack_player():
    """Busted players sit out: no hole cards, no blinds, stays inactive."""
    p1 = make_player("A", 0, stack=200)
    p2 = make_player("B", 1, stack=0)    # busted — holds the SB seat
    p3 = make_player("C", 2, stack=200)
    state = GameState(
        phase=GamePhase.WAITING,
        players=(p1, p2, p3),
        dealer_idx=0, small_blind=5, big_blind=10,
    )
    deck = Deck(); deck.shuffle()
    new_state = deal_new_hand(state, deck.cards[:], dealer_idx=0)

    busted = new_state.player(1)
    assert busted is not None
    assert busted.hole_cards in (None, ())
    assert busted.is_active is False
    assert busted.current_bet == 0 and busted.total_bet == 0
    # SB 是爆掉玩家 → 死盲注不收（不重排），只有 BB 的 10 入池
    assert new_state.pot.main_pot == 10
    # 有筹码的玩家都拿到了底牌
    for p in new_state.players:
        if p.stack > 0:
            assert p.hole_cards is not None and len(p.hole_cards) == 2


def test_deal_requires_two_players_with_chips():
    p1 = make_player("A", 0, stack=200)
    p2 = make_player("B", 1, stack=0)
    state = GameState(phase=GamePhase.WAITING, players=(p1, p2))
    with pytest.raises(InvalidActionError, match="at least 2"):
        deal_new_hand(state, Deck().cards[:], 0)
```

- [ ] **Step 2: 跑测试确认红**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_action_processor.py -q -k "zero_stack or with_chips"`
Expected: FAIL（爆掉玩家也被发牌 / 误通过人数检查）

- [ ] **Step 3: 实现 deal_new_hand 修改**

人数检查处（当前是 `len(state.players) < 2`）：

```python
    # Only players with chips can be dealt in; busted players sit out.
    live_count = sum(1 for p in state.players if p.stack > 0)
    if live_count < 2:
        raise InvalidActionError("Need at least 2 players with chips to deal")
```

发牌循环处——对 0 筹码玩家跳过：

```python
    updated: list[Player] = []
    for p in state.players:
        if p.stack == 0:
            # Busted — sits out this hand (can rebuy between hands)
            updated.append(Player(
                name=p.name, seat_idx=p.seat_idx, stack=0,
                hole_cards=(), is_active=False, is_all_in=False,
                current_bet=0, total_bet=0, is_human=p.is_human,
            ))
            continue
        card1 = deck_cards.pop()
        card2 = deck_cards.pop()
        ...（原有盲注/发牌逻辑不变）
```

注意：盲注座位计算（sb_seat/bb_seat）基于座位号而非活跃玩家——若 SB/BB 座位恰好是爆掉玩家，盲注就收不到。处理：爆掉玩家的 `blind_total` 为 0（skip 分支已保证），其余玩家盲注照常——保留现有 sb_seat/bb_seat 计算即可（德州惯例：死盲注位直接跳过，不重排）。`first_to_act` 用 `_next_active_seat` 已会跳过 is_active=False 的座位。

- [ ] **Step 4: 跑测试确认绿 + 全量回归 + 提交**

```bash
python -m pytest tests/ -q   # 189 + 2 = 191 passed
git add backend/sekhmet/game_engine/action_processor.py backend/tests/test_action_processor.py
git commit -m "feat: busted players sit out the deal

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 后端 — rebuy（爆掉重买）

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`（+`rebuy`）
- Modify: `backend/sekhmet/api/ws.py`（+`rebuy` 消息分支）
- Test: `backend/tests/test_tables.py`（追加）

**Interfaces:**
- Consumes: `TableSession.total_buyin`（排行榜 PR）、Task 1 的坐观机制
- Produces: `async def rebuy(table_id: str, seat_idx: int, amount: int) -> dict`——成功返回 `_table_summary`；ws 新消息 `{"type": "rebuy", "amount": int}`（以 my_seat 为目标）

- [ ] **Step 1: 写失败测试**

```python
async def _bust_player(tid: str, seat: int) -> None:
    """直接构造 0 筹码状态（比真打一手牌快且确定）。"""
    session = await tm.get_table(tid)
    assert session is not None
    gs = session.game_state
    session.game_state = gs.with_players(tuple(
        type(p)(name=p.name, seat_idx=p.seat_idx, stack=0 if p.seat_idx == seat else p.stack,
                hole_cards=p.hole_cards, is_active=p.is_active, is_all_in=p.is_all_in,
                current_bet=p.current_bet, total_bet=p.total_bet, is_human=p.is_human)
        for p in gs.players
    ))


async def test_rebuy_success_when_busted():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await _bust_player(tid, 0)

    summary = await tm.rebuy(tid, 0, 500)

    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.player(0).stack == 500
    assert session.total_buyin[0] == 700  # 200 + 500 → net_chips 语义保持
    seat0 = next(s for s in summary["seats"] if s["seat_idx"] == 0)
    assert seat0["stack"] == 500 and seat0["net_chips"] == -200


async def test_rebuy_rejected_with_chips():
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    with pytest.raises(GameError, match="busted"):
        await tm.rebuy(tid, 0, 500)


async def test_rebuy_rejected_mid_hand():
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    await _bust_player(tid, 0)
    with pytest.raises(GameError, match="mid-hand"):
        await tm.rebuy(tid, 0, 500)


async def test_rebuy_amount_bounds():
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()  # blinds 5/10 → bounds [200, 2000]
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await _bust_player(tid, 0)
    with pytest.raises(GameError, match="20"):
        await tm.rebuy(tid, 0, 100)   # < 20bb
    with pytest.raises(GameError, match="200"):
        await tm.rebuy(tid, 0, 5000)  # > 200bb
```

- [ ] **Step 2: 确认红**

Run: `python -m pytest tests/test_tables.py -q -k rebuy`
Expected: FAIL（`AttributeError: rebuy`）

- [ ] **Step 3: 实现**

`table_manager.py`：

```python
async def rebuy(table_id: str, seat_idx: int, amount: int) -> dict[str, Any]:
    """Top up a busted player between hands. Only stack==0 may rebuy."""
    session = await get_table(table_id)
    if session is None:
        raise GameError(f"Table {table_id} not found")
    if session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        raise GameError("Table is mid-hand — rebuy between hands")
    player = session.game_state.player(seat_idx)
    if player is None or seat_idx not in session.player_names:
        raise GameError(f"Seat {seat_idx} is not occupied")
    if player.stack > 0:
        raise GameError("Only busted players (0 chips) can rebuy")
    lo = 20 * session.config.big_blind
    hi = 200 * session.config.big_blind
    if not (lo <= amount <= hi):
        raise GameError(f"Rebuy must be between 20bb ({lo}) and 200bb ({hi})")

    session.game_state = session.game_state.with_players(tuple(
        Player(name=p.name, seat_idx=p.seat_idx,
               stack=p.stack + amount if p.seat_idx == seat_idx else p.stack,
               hole_cards=p.hole_cards, is_active=p.is_active, is_all_in=p.is_all_in,
               current_bet=p.current_bet, total_bet=p.total_bet, is_human=p.is_human)
        for p in session.game_state.players
    ))
    session.total_buyin[seat_idx] = session.total_buyin.get(seat_idx, 0) + amount
    return _table_summary(session)
```

注意：with_players 生成的新 Player 保持 `is_active` 原值——局间状态下 SHOWDOWN 后玩家 is_active 可能是 False（fold 过）；rebuy 不改它，`deal_new_hand` 会重建。但 busted 坐观玩家在 SHOWDOWN 阶段 `is_active=False` 且 stack=0→500：下一手 deal_new_hand 现在会发牌给他（stack>0）——正确，无需额外处理。

`ws.py` 新分支（放在 `player_action` 之前）：

```python
                elif msg_type == "rebuy":
                    if my_seat is None:
                        await websocket.send_json({"type": "error", "message": "Sit down first"})
                        continue
                    amount = int(msg.get("amount", 0))
                    summary = await tm.rebuy(table_id, my_seat, amount)
                    await tm.broadcast(table_id, summary)
```

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 191 + 4 = 195 passed
git add backend/sekhmet/api/table_manager.py backend/sekhmet/api/ws.py backend/tests/test_tables.py
git commit -m "feat: rebuy for busted players between hands

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 后端 — 断线宽限 + 按名认领 + 安全移除

**Files:**
- Modify: `backend/sekhmet/config.py`（GameConfig + grace）
- Modify: `backend/sekhmet/api/table_manager.py`（disconnected、grace_timers、handle_disconnect、try_reclaim、_expire_seat、start_hand purge、table_info + connected）
- Modify: `backend/sekhmet/api/ws.py`（断连改宽限、sit_down 前认领分支）
- Test: `backend/tests/test_tables.py`（追加）
- Modify: `backend/tests/test_e2e_game_journey.py`（seats 全等断言 +connected）

**Interfaces:**
- Consumes: 现有 stand_up/_resolve_showdown/auto_bot_actions/_table_summary
- Produces:
  - `GameConfig.disconnect_grace_seconds: int = 60`
  - `TableSession.disconnected: set[int]`、`TableSession.grace_timers: dict[int, asyncio.Task]`
  - `async def handle_disconnect(table_id, seat_idx) -> None`
  - `async def try_reclaim(table_id, name) -> int | None`（返回认领的座位）
  - seats 明细 + `connected: bool`

- [ ] **Step 1: 写失败测试**

```python
async def test_disconnect_marks_seat_and_keeps_player():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.handle_disconnect(tid, 0)
    session = await tm.get_table(tid)
    assert session is not None
    assert 0 in session.player_names  # 座位保留
    info = tm.table_info(session)
    assert info["seats"][0]["connected"] is False


async def test_reclaim_by_name_restores_seat():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.handle_disconnect(tid, 0)
    seat = await tm.try_reclaim(tid, "Hero")
    assert seat == 0
    session = await tm.get_table(tid)
    assert session is not None
    assert tm.table_info(session)["seats"][0]["connected"] is True
    assert await tm.try_reclaim(tid, "Stranger") is None


async def test_grace_expiry_between_hands_removes_seat(monkeypatch):
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "disconnect_grace_seconds", 0.05)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.handle_disconnect(tid, 0)
    await asyncio.sleep(0.15)
    session = await tm.get_table(tid)
    assert session is not None
    assert 0 not in session.player_names


async def test_grace_expiry_mid_hand_force_folds(monkeypatch):
    """掉线者在手牌中且轮到TA：宽限期满 → 自动 FOLD，手牌继续。"""
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "disconnect_grace_seconds", 0.05)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    cur = session.game_state.current_player_idx  # HU: SB 先行动

    await tm.handle_disconnect(tid, cur)
    await asyncio.sleep(0.2)

    session = await tm.get_table(tid)
    assert session is not None
    gs = session.game_state
    # 掉线者已被强制弃牌 → 手牌结束（fold-out），对手赢得底池
    assert gs.phase == GamePhase.SHOWDOWN
    assert gs.player(cur).is_active is False
    assert cur not in session.player_names  # 身份映射已清
    # 手牌没有卡死：另一玩家筹码增加
    winner = 1 - cur
    assert gs.player(winner).stack > 200
```

- [ ] **Step 2: 确认红**

Run: `python -m pytest tests/test_tables.py -q -k "disconnect or reclaim or grace"`
Expected: FAIL（`AttributeError: handle_disconnect`）

- [ ] **Step 3: 实现**

`config.py` GameConfig 加字段：

```python
    disconnect_grace_seconds: int = 60
```

`table_manager.py` 顶部 import 加 `from dataclasses import replace`（field 已有），TableSession 加：

```python
    disconnected: set[int] = field(default_factory=set)
    grace_timers: dict[int, asyncio.Task] = field(default_factory=dict)
```

新增函数：

```python
async def handle_disconnect(table_id: str, seat_idx: int) -> None:
    """Mark the seat disconnected and start the grace timer (no instant removal)."""
    session = await get_table(table_id)
    if session is None:
        return
    session.clients.pop(seat_idx, None)  # dead socket
    session.disconnected.add(seat_idx)
    await broadcast(table_id, _table_summary(session))

    async def _expire() -> None:
        try:
            await asyncio.sleep(app_config.game.disconnect_grace_seconds)
        except asyncio.CancelledError:
            return
        await _expire_seat(table_id, seat_idx)

    session.grace_timers[seat_idx] = asyncio.create_task(_expire())


async def try_reclaim(table_id: str, name: str) -> int | None:
    """Reclaim a disconnected seat by player name. Returns the seat or None."""
    session = await get_table(table_id)
    if session is None:
        return None
    for seat in list(session.disconnected):
        if session.player_names.get(seat) == name:
            timer = session.grace_timers.pop(seat, None)
            if timer is not None:
                timer.cancel()
            session.disconnected.discard(seat)
            return seat
    return None


async def _expire_seat(table_id: str, seat_idx: int) -> None:
    """Grace expired: fold out of any running hand, then remove the seat."""
    session = await get_table(table_id)
    if session is None or seat_idx not in session.disconnected:
        return
    session.disconnected.discard(seat_idx)
    session.grace_timers.pop(seat_idx, None)

    gs = session.game_state
    mid_hand = gs.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN)

    if not mid_hand:
        await stand_up(table_id, seat_idx)
        await broadcast(table_id, _table_summary(session))
        return

    # Mid-hand: force-fold (engine fold if it's their turn, else mark inactive —
    # the engine's round logic skips inactive players either way).
    p = gs.player(seat_idx)
    if p is not None and p.is_active and not p.is_all_in:
        if gs.current_player_idx == seat_idx:
            gs = execute(gs, Action(seat_idx, ActionType.FOLD))
        else:
            gs = gs.with_players(tuple(
                replace(pl, is_active=False) if pl.seat_idx == seat_idx else pl
                for pl in gs.players
            ))
        session.game_state = gs

    # Identity mappings go now; the folded shell stays until the hand ends
    # (start_hand purges it before the next deal).
    session.player_names.pop(seat_idx, None)
    session.stats.pop(seat_idx, None)
    session.total_buyin.pop(seat_idx, None)
    session.bot_levels.pop(seat_idx, None)

    result = None
    if session.game_state.phase == GamePhase.SHOWDOWN:
        result = _resolve_showdown(session)
    await broadcast(table_id, _state_broadcast(session, result))
    for msg in await auto_bot_actions(table_id):
        await broadcast(table_id, msg)
    await broadcast(table_id, _table_summary(session))
```

`start_hand` 在 deal_new_hand 之前加 purge：

```python
    # Purge shells of players removed mid-hand (grace expiry) before dealing.
    live = tuple(
        p for p in session.game_state.players
        if p.seat_idx in session.player_names
    )
    if len(live) != len(session.game_state.players):
        session.game_state = session.game_state.with_players(live)
```

`table_info` seats 明细加：`"connected": seat not in session.disconnected`。

`ws.py`：

1. sit_down 分支在 `tm.sit_down` 调用**之前**插入认领：

```python
                    # Reconnect path: a name matching a disconnected seat
                    # reclaims it (works mid-hand — the player never left).
                    reclaimed = await tm.try_reclaim(table_id, name)
                    if reclaimed is not None:
                        session.clients[reclaimed] = websocket
                        my_seat = reclaimed
                        await tm.broadcast(table_id, tm._table_summary(session))
                        # Re-send private state so the reclaimer catches up
                        p = session.game_state.player(reclaimed)
                        if p is not None and p.hole_cards:
                            await tm.send_to_player(table_id, reclaimed, {
                                "type": "hole_cards",
                                "cards": [str(c) for c in p.hole_cards],
                            })
                        continue
```

2. 断连处理器由 stand_up 改为宽限：

```python
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected from table %s (seat %s)", table_id, my_seat)
        if my_seat is not None:
            try:
                await tm.handle_disconnect(table_id, my_seat)
            except Exception:
                logger.exception("handle_disconnect failed for seat %s", my_seat)
```

`test_e2e_game_journey.py` 的 seats 全等断言加 `"connected": True`。

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 195 + 4 = 199 passed
git add backend/
git commit -m "feat: disconnect grace, name-based reclaim, safe mid-hand removal

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 后端 — 行动超时 + after_action 收敛

**Files:**
- Modify: `backend/sekhmet/api/table_manager.py`（action_timer、schedule_action_timeout、_action_timeout、after_action）
- Modify: `backend/sekhmet/api/ws.py`（player_action/start_hand 改用 after_action，消除重复广播块）
- Test: `backend/tests/test_tables.py`（追加）

**Interfaces:**
- Consumes: `app_config.game.action_timeout_seconds`（现有字段，默认 30）
- Produces:
  - `TableSession.action_timer: asyncio.Task | None = None`
  - `def schedule_action_timeout(session) -> None`
  - `async def after_action(table_id) -> None`——bot 驱动 + 局末 table_state + 重排计时器（ws 两个分支与超时回调共用的单一入口）

- [ ] **Step 1: 写失败测试**

```python
def test_action_timeout_auto_checks(monkeypatch):
    """轮到人类且迟迟不动 → 超时自动 CHECK（无注）/FOLD（有注）。"""
    import random
    monkeypatch.setattr(tm.app_config.game, "action_timeout_seconds", 0.1)
    random.seed(7)  # bot SB 跟注，人类 BB 获得 option（无注）
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200,
                      "is_human": False})
        ws.send_json({"type": "start_hand"})
        # 人类不行动，等超时：应在若干消息内看到 seat 0 的自动行动
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] in ("game_state_update", "hand_result"):
                auto = [a for a in msg.get("round_history", [])
                        if a["seat"] == 0 and a["action"] in ("CHECK", "FOLD")]
                if auto:
                    return  # 超时自动行动生效
            # 注意：绝不发送 player_action
        raise AssertionError("no auto action within 40 messages")
```

- [ ] **Step 2: 确认红**

Run: `python -m pytest tests/test_tables.py -q -k timeout`
Expected: FAIL（40 条消息内没有 seat 0 的自动行动——目前计时器不存在，人类不动就永远停着）

- [ ] **Step 3: 实现**

`table_manager.py`：

```python
# TableSession 加字段：
    action_timer: asyncio.Task | None = None


def schedule_action_timeout(session: TableSession) -> None:
    """(Re)arm the action timer if a human is to act in a betting round."""
    if session.action_timer is not None:
        session.action_timer.cancel()
        session.action_timer = None
    gs = session.game_state
    if gs.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        return
    cur = gs.current_player_idx
    if cur is None:
        return
    p = gs.player(cur)
    if p is None or not p.is_human:
        return
    session.action_timer = asyncio.create_task(_action_timeout(session.table_id, cur))


async def _action_timeout(table_id: str, seat_idx: int) -> None:
    try:
        await asyncio.sleep(app_config.game.action_timeout_seconds)
    except asyncio.CancelledError:
        return
    session = await get_table(table_id)
    if session is None:
        return
    gs = session.game_state
    if gs.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        return
    if gs.current_player_idx != seat_idx:
        return
    player = gs.player(seat_idx)
    if player is None or not player.is_human:
        return
    to_call = gs.current_bet - player.current_bet
    action_type = "CHECK" if to_call == 0 else "FOLD"
    logger.info("action timeout: auto %s for seat %s at table %s",
                action_type, seat_idx, table_id)
    msg = await handle_player_action(table_id, seat_idx, action_type)
    await broadcast(table_id, msg)
    await after_action(table_id)


async def after_action(table_id: str) -> None:
    """Drive bots, push fresh stats at hand end, re-arm the action timer."""
    for msg in await auto_bot_actions(table_id):
        await broadcast(table_id, msg)
    session = await get_table(table_id)
    if session is None:
        return
    if session.game_state.phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
        await broadcast(table_id, _table_summary(session))
    schedule_action_timeout(session)
```

（table_manager.py 顶部加 `import logging` + `logger = logging.getLogger(__name__)`——若没有的话。）

`ws.py` 重构两处（消除此前评审标记的重复块）：

`player_action` 分支尾部改为：

```python
                    state_msg = await tm.handle_player_action(
                        table_id, my_seat, action_type, amount,
                    )
                    await tm.broadcast(table_id, state_msg)
                    await tm.after_action(table_id)
```

`start_hand` 分支尾部（hole cards 循环之后）改为：

```python
                        await tm.after_action(table_id)
```

（删除两处"bot_msgs 循环 + 补发 table_state"旧代码。）

`_expire_seat`（Task 3）尾部的 bot 循环 + summary 也可改用 after_action——做掉：

```python
    result = None
    if session.game_state.phase == GamePhase.SHOWDOWN:
        result = _resolve_showdown(session)
    await broadcast(table_id, _state_broadcast(session, result))
    await after_action(table_id)
```

- [ ] **Step 4: 确认绿 + 回归 + 提交**

```bash
python -m pytest tests/ -q   # 199 + 1 = 200 passed
git add backend/
git commit -m "feat: action timeout with auto check/fold, unify after-action pipeline

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 前端 — Rebuy 面板 + 掉线显示 + 选座认领入口

**Files:**
- Modify: `frontend/src/hooks/useGameState.ts`（SeatInfo + connected）
- Modify: `frontend/src/pages/GameTable.tsx`（Rebuy 面板；选座图掉线座位可认领）
- Modify: `frontend/src/components/table/OvalTable.tsx`（掉线座位样式）
- Modify: `frontend/src/styles/game.css`

**Interfaces:**
- Consumes: Task 2/3 的协议（rebuy 消息、seats.connected、按名认领）
- Produces: 无新接口

- [ ] **Step 1: SeatInfo + connected**

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
  connected: boolean;
}
```

- [ ] **Step 2: GameTable Rebuy 面板**

牌桌视图中（ActionBar 之后）加：

```tsx
      {me && me.stack === 0 && (state.phase === 'WAITING' || state.phase === 'SHOWDOWN') && (
        <div className="rebuy-panel">
          <span className="rebuy-label">You're busted.</span>
          <input className="input" type="number" value={rebuyAmount}
                 onChange={e => setRebuyAmount(Number(e.target.value))} />
          <button className="btn gold"
                  onClick={() => send({ type: 'rebuy', amount: rebuyAmount })}>
            Rebuy
          </button>
        </div>
      )}
```

状态：`const [rebuyAmount, setRebuyAmount] = useState(200)`；detail 加载或 config 到达时设为 default_buyin（在现有 config 相关 effect/赋值处同步）。

选座图：掉线座位若名字匹配输入的名字则可选（认领入口）。picker 按钮处：

```tsx
  const reclaimable = occ && !occ.connected && occ.name === name;
  ...
  disabled={!!occ && !reclaimable}
  className={`picker-seat seat-${i}${occ ? ' taken' : ''}${reclaimable ? ' reclaim' : ''}${selectedSeat === i ? ' selected' : ''}`}
```

（服务端逻辑：同名 sit_down 会先走 try_reclaim——前端只需放行选择。）

- [ ] **Step 3: OvalTable 掉线样式**

seat-wrap 的 className 加 offline：

```tsx
          <div key={seat.seat_idx}
               className={`seat-wrap seat-${slot}${seat.connected === false ? ' offline' : ''}`}>
```

- [ ] **Step 4: game.css 追加**

```css
/* ---- Rebuy ---- */
.rebuy-panel {
  display: flex; gap: 10px; align-items: center; justify-content: center;
  background: rgba(251, 191, 36, 0.06); border: 1px solid rgba(251, 191, 36, 0.35);
  border-radius: 8px; padding: 10px 16px;
}
.rebuy-panel .input { width: 110px; }
.rebuy-label { color: var(--gold-text); font-size: 0.85rem; }

/* ---- Offline seat ---- */
.seat-wrap.offline .avatar { opacity: 0.4; border-style: dashed; box-shadow: none; }
.seat-wrap.offline .name::after { content: ' (offline)'; color: var(--text-dim); }

/* ---- Reclaimable seat in picker ---- */
.picker-seat.reclaim { border-style: dashed; border-color: var(--gold); color: var(--gold-text); }
```

- [ ] **Step 5: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q   # 200 passed
cd .. && git add frontend/src
git commit -m "feat: rebuy panel, offline seat display, reclaim via seat picker

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 全量验证 + PR

- [ ] **Step 1: 全量验证**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -q   # 200 passed
cd ../frontend && npm run build && npx oxlint src
```

- [ ] **Step 2: 推送并开 PR**（HTTPS+token 备用通道；网络抖动重试）

PR 标题：`feat: 断线宽限重连 + 行动超时 + 爆掉重买`
- [ ] **Step 3: 等 CI 绿，请用户确认后合入**（项目铁律：不自行 merge）
