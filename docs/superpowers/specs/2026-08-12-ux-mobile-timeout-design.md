# Sekhmet — 包 C：前端体验与托管 · 设计文档

> 2026-08-12 · 选座实时刷新 / toast 替换 alert / 移动端基础适配 / 连续超时自动离座

## 1. 背景

- 选座确认页的占用信息是一次性 REST 快照，停留期间别人入座不刷新（靠服务端拒绝兜底，体验差）
- 错误提示用原生 `alert()`，打断操作且丑
- 移动端从未适配（主设计文档 §6.5 写了但没实现）：窄屏下椭圆桌溢出、动作栏挤压
- 连着但长期放置的玩家每手被自动 check/fold，但永远占着座位

## 2. 选座图实时刷新

- 入座确认页的座位占用改由 **ws `table_state` 广播驱动**（reducer `state.seats` 已有）——REST detail 仅作首次填充
- 任何入座/离座/掉线/重连都实时反映到选座图；`detail` 里仅保留房间配置（盲注/买入/座位数）展示

## 3. Toast 替换 alert

- 新增轻量 `Toast` 组件：右上角滑入，错误玫红描边、信息青色描边，3.5s 自动消失，可叠加（队列）
- 替换 GameTable 所有 `alert()`：ws error 消息、room_closed、Table full 等
- room_closed 改为 toast 提示 + 延迟 1.5s 回大厅（让用户看到提示）

## 4. 移动端基础适配

`@media (max-width: 768px)`：

- 牌桌：`max-width: 100%`，aspect-ratio 调小（1.6/1），座位头像缩小（34px），公共牌缩小
- 动作栏：垂直堆叠全宽按钮，滑杆全宽
- 大厅：建房表单垂直堆叠，输入框全宽
- 排行榜/摊牌面板：全宽
- 入座确认页：选座图缩小但保持胶囊形

## 5. 连续超时自动离座

- `TableSession.consecutive_timeouts: dict[int, int]`：行动超时自动 check/fold 时 +1；该座位主动行动时清零；离座/移除时清理
- 达到 `max_consecutive_timeouts`（GameConfig 新增，默认 3）→ 按 `_expire_seat` 同路径强制离座（局中弃牌、局间移除、广播）
- 前端无改动（离座走既有 table_state/广播链路）

## 6. 实现要点

- 后端：`table_manager.py`（consecutive_timeouts 追踪 + 离座触发）、`config.py`
- 前端：`GameTable.tsx`（picker 数据源、toast 挂载）、新 `components/shared/Toast.tsx`、`game.css`（toast + 媒体查询）
- 无协议破坏性变更

## 7. 测试

- 后端：连续 3 次超时 → 座位被移除（局中路径弃牌 + 守恒）；主动行动清零计数
- 既有 219 测试保持绿
- 前端 build + oxlint
