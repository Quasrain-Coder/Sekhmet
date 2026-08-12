# Sekhmet — 包 B：房主权限 / 房间回收 / 认领 token · 设计文档

> 2026-08-11 · 发牌与踢 bot 的权限、闲置房间自动回收、防冒领的重连 token

## 1. 背景

- **无权限**：任何连接（含未入座的旁观者）都能 `start_hand`；任何连接都能踢 bot。链接可分享后这是真实的搅局面。已定决策：**房主制**。
- **房间不销毁**：`_tables` 只增不减，无人房间永久驻留内存。
- **同名冒领**：重连认领只看名字，知道名字就能接管别人的座位（筹码+底牌）。

## 2. 房主制

- `TableSession.owner_seat: int | None`——**第一个入座的人类**成为房主；bot 不能当房主
- 房主离座或宽限到期被移除 → 房主**移交给座位号最小的其他在座人类**；无在座人类则 owner_seat=None（下一个人类入座时接任）
- 仅房主可：`start_hand`、踢 bot（`stand_up {seat_idx}` 踢人路径）
- 非房主尝试 → error（"Only the table owner can ..."）；入座/离座/rebuy/动作不受限
- 前端：房主头像加 👑 角标（seats 明细加 `is_owner: bool`）；非房主时 Deal 按钮禁用并提示

## 3. 闲置房间回收

- `TableSession.last_activity: float`——任何 ws 消息处理与 REST 访问时刷新
- FastAPI lifespan 启动一个 sweeper task：每 60s 扫描，回收闲置超过 **30 分钟**（`room_idle_timeout_seconds: int = 1800`，GameConfig 新增）的房间：
  - 先取消该房间的 grace_timers / action_timer（复用现有清理），再从 `_tables` 移除
  - 房间内仍有连接的玩家收到 `{"type": "room_closed"}` 广播（前端回大厅并提示）
- 测试：monkeypatch 缩短 timeout + 手动触发 sweep 函数（不依赖真实等待）

## 4. 认领 token

- `sit_down` 成功（人类）→ 服务端生成 `reclaim_token`（uuid hex），存 `session.reclaim_tokens[seat]`，**私发**给该连接：`{"type": "reclaim_token", "token": ...}`（不广播，防泄漏）
- 前端存 `localStorage["reclaimToken_<tableId>"]`；断线重连入座时 sit_down 消息带 `reclaim_token`
- `try_reclaim` 改为必须 token 匹配（名字用于定位座位，token 用于证明身份）；不匹配/缺失 → error（"reclaim token mismatch"），不再仅凭名字认领
- 每次认领成功**轮换**新 token 并私发
- 前端认领流程对用户无感（localStorage 自动携带）

## 5. 实现要点

- 后端：`table_manager.py`（owner_seat、回收、token）、`ws.py`（权限校验、token 私发、reclaim 校验）、`config.py`（idle timeout）、`main.py`（lifespan sweeper）
- 前端：owner 角标 + Deal 禁用态 + reclaim_token 存取 + room_closed 处理
- 协议：seats 明细 + `is_owner`；新增私发消息 `reclaim_token`、广播 `room_closed`；sit_down + 可选 `reclaim_token` 字段

## 6. 测试

- 房主制：第一个入座人类为房主；非房主 start_hand/踢 bot 被拒；房主移除后移交
- 回收：last_activity 刷新；过期房间被 sweep（timer 取消、广播 room_closed、从注册表移除）
- token：sit_down 私发 token；无 token/错 token 认领被拒；正确 token 认领成功并轮换
- 既有 208 测试保持绿（start_hand 调用方均为房主——e2e 旅程测试不受影响，因首个入座者就是操作者）
- 前端 build + oxlint
