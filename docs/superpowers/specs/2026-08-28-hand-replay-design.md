# Sekhmet — HandReplay 逐手回放页 · 设计文档

> 2026-08-28 · P6 第二项：主设计文档 6.1 规划的 `/history/:hand_id → HandReplay` 路由落地。紧接 `2026-08-28-history-page-design.md`（历史列表页）。

## 1. 背景

- 每手牌已持久化完整动作序列 + 全员底牌（hole-card patch 之后）+ 结算 awards
- 引擎是不可变状态机，`trainer/hand_to_scenario.py` 的 `rebuild_states()` 已验证：从发牌态重放同一动作序列可精确复现原局每个决策点的 `GameState`
- 历史页卡片当前只能展开文字流水——缺可视化逐帧回放

## 2. 范围

**做**：
- 后端：`GET /api/history/hands/{hand_id}/replay`——重放整手，返回逐帧快照
- 前端：`/history/:handId` → `HandReplay` 页（帧步进控制 + 简化桌面视图）
- 历史页卡片点击行为从"展开流水"改为跳转 `/history/:id`（兑现历史页设计文档的过渡约定）

**不做**：
- 完整 OvalTable 桌面复刻（回放用简化横向座位条即可，避免牌桌组件与 WS 状态耦合）
- runout（多次发牌）分支展示——`board` 只存最终牌面，重放按最终 run 呈现
- 回放内的 GTO 点评（训练器"导入这手牌"已覆盖该场景）

## 3. 后端设计

### 3.1 重放重构（`trainer/hand_to_scenario.py`）

`rebuild_states()` 返回每个动作**执行前**的 `(state, actor)`，但丢掉终态。抽出内部 `_replay()` 同时返回 `(points, final_state)`；`rebuild_states` 保持原签名（`build_scenario_from_hand` 不受影响）。新增 `replay_full()` 暴露二者。

### 3.2 帧模型与端点（`api/history.py`）

帧 = 动作**执行后**的状态；帧 0 为发牌后初态（盲注已投、未有任何动作）：

```
frames[0]     = 初态,               last_action=null
frames[i]     = points[i].state,    last_action=actions[i-1]   (1≤i<n)
frames[n]     = final_state,        last_action=actions[n-1]
```

即 `len(frames) == len(actions) + 1`（重放分歧提前停止时以实际执行为准）。

每帧序列化：
```json
{
  "phase": "FLOP",
  "board": ["A♣", "6♣", "3♥"],
  "pot": 120,
  "to_act": 3,
  "players": [{"seat_idx", "name", "is_human", "stack", "current_bet",
               "is_active", "is_all_in", "hole_cards": ["A♠","K♠"] | null}],
  "last_action": {"seat": 3, "action": "BET", "amount": 25} | null
}
```

响应另带 `id / table_id / created_at / awards / small_blind / big_blind`。手牌不存在 → 404。底牌全员明牌（已结束对局的上帝视角，学习用途）。

## 4. 前端设计（`pages/HandReplay.tsx`）

- 数据：进入页面 fetch replay 端点一次，全部帧本地步进，无 WS
- 视图（沿用青蓝霓虹主题）：
  - 头部：← History 返回、`#id · table_id · 时间`、阶段胶囊
  - 中央：公共牌（CardView）+ 底池
  - 座位条：每座位 名字 / 底牌（明牌小卡）/ stack / 当前轮下注徽标；fold 置灰、all-in 标记、last_action 的座位高亮
  - 末帧显示 awards 结算横幅（🏆 赢家 + 牌型 + 金额）
- 控制条：⏮ 首帧 · ◀ 上一步 · ▶/⏸ 自动播放（1.2s/帧）· ⏭ 末帧 + 进度滑杆 + `帧 i/n` 计数；动作 ticker 显示最近动作文本

## 5. 测试与 CI

- 后端 `tests/test_replay_api.py`：seed 一手完整牌 → 帧数 = 动作数+1、board 随阶段增长、last_action 对齐、初态盲注已投、未知 id 404；重放分歧（脏数据）时优雅截断
- 前端 `__tests__/HandReplay.test.tsx`：stub fetch，首帧渲染、◀▶ 步进、⏭ 到末帧出现结算横幅、fold 置灰
- 更新 `History.test.tsx`：点击卡片 → 跳转 `/history/:id`（替换原展开测试）
- CI 无需改动（pytest/vitest 均自动收集）
