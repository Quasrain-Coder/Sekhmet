# Sekhmet — 房间配置与 URL 路由 · 设计文档

> 2026-08-08 · 建房可配置（盲注/买入/座位数）、房内手动加 bot（可选等级）、URL 体现房间号

## 1. 背景与目标

现状问题：

- 建桌无任何配置：`POST /api/game/tables` 不接受参数，盲注/买入/座位数全部读全局 `app_config` 默认值
- 进入牌桌时前端**无条件自动塞一个 bot**（写死 `rule_lv2`、买入 200），无法选择数量、等级，也无法不加
- 前端无路由库，`App.tsx` 用条件渲染切换页面——URL 永远不变，房间不可分享、刷新即丢

目标：

1. 建房时可配置：盲注档位、默认买入、最大座位数
2. Bot 改为房内手动添加：点空位 "+ Bot"，选等级（L1/L2/L3），可移除
3. URL 体现房间号（`/game/:tableId`），可刷新、可分享；通过链接进房先进入座确认页

非目标（YAGNI）：

- 房内修改房间配置（改盲注/座位数会影响进行中的牌局，建房时定死）
- 牌局进行中刷新/断线重连恢复座位（见 §7 已知限制）
- Trainer/History 页面（路由框架为其预留，本迭代不实现）

## 2. 后端：房间配置

### 2.1 TableConfig

```python
@dataclass(frozen=True)
class TableConfig:
    small_blind: int = 5
    big_blind: int = 10
    default_buyin: int = 200
    max_seats: int = 9
```

- 校验规则（不满足返回 400）：`big_blind > small_blind > 0`、`2 <= max_seats <= 9`、`default_buyin >= 20 * big_blind`
- `POST /api/game/tables` 接受可选 JSON body（四个字段均可选，缺省用默认值）：

```json
{ "small_blind": 10, "big_blind": 20, "default_buyin": 1000, "max_seats": 6 }
```

### 2.2 TableSession 变更

- `TableSession.config: TableConfig`（替代现在的全局 `app_config.game` 引用）
- `create_table(config: TableConfig)`：`GameState` 的盲注从 config 取值
- `sit_down` 的默认买入：`buyin or session.config.default_buyin`
- 新增 `bot_levels: dict[int, int]`——seat_idx → bot 等级（1–3）

### 2.3 Bot 等级按座位驱动

`auto_bot_actions` 目前写死 `create_bot("rule_lv2")`，改为：

```python
level = session.bot_levels.get(cur_idx, 2)
bot = create_bot(f"rule_lv{level}")
```

## 3. 协议与 REST 变更

### 3.1 WebSocket 消息

| 消息 | 变更 |
|------|------|
| `sit_down` | + 可选 `bot_level: int`（1–3，默认 2；仅 `is_human=false` 时生效） |
| `stand_up` | + 可选 `seat_idx: int`——仅允许移除**非人类**座位（踢 bot）；人类座位仍只能由所属连接自己 stand_up |
| `table_state`（广播/摘要） | + `config: {small_blind, big_blind, default_buyin, max_seats}`；`seats` 由 `{seat: name}` 改为明细数组 `[{seat_idx, name, is_human, bot_level}]` |

### 3.2 REST

- `POST /api/game/tables`：接受 §2.1 的配置 body，非法值 400 + 错误信息
- `GET /api/game/tables`：列表项 + `config`、座位明细（Lobby 卡片展示盲注/人数）
- `GET /api/game/tables/{id}`：返回配置 + 座位明细 + 阶段（供入座确认页）

## 4. 前端：路由

引入 `react-router-dom`，`App.tsx` 改为 Router：

```
/                → Lobby
/game/:tableId   → GameTablePage
```

- Lobby 建房/加入 → `useNavigate` 跳转 `/game/:tableId`
- GameTablePage 用 `useParams` 取 tableId
- 后续 Trainer/History 按主设计文档 §6.1 直接加路由

## 5. 前端：页面改造

### 5.1 Lobby 建房表单

现有 名字/买入 输入扩展为：名字、盲注档位（下拉：1/2、5/10、10/20、25/50）、默认买入、最大座位数（2–9）。买入输入框从 Lobby 移除（买入是入座时的事，且房间有默认买入）。切换盲注档位时，默认买入输入联动为该档位的 100bb（用户可再改），避免触发 §2.1 的 20bb 校验失败。

### 5.2 入座确认页（/game/:tableId 未入座时）

- 显示房间信息：盲注、默认买入、已坐人数/座位数、当前阶段、已在座玩家列表
- 名字（预填 localStorage）+ 买入（预填房间默认买入）输入框 + "入座"按钮
- 入座 = 选第一个空位 → 发送 `sit_down`
- 房间不存在 → 提示 + 返回 Lobby 链接

### 5.3 房内手动加/踢 bot

- 空座位渲染为 "+ Bot" 按钮 → 弹出等级选择（L1/L2/L3）→ 发送 `sit_down {is_human: false, bot_level}`
- bot 座位显示等级徽章（如 "L2"）+ 移除按钮（×）→ 发送 `stand_up {seat_idx}`
- **删除** GameTable 中无条件自动加 bot 的 effect
- 人类玩家的入座确认页状态由 `my_seat` 是否已确定驱动（入座后进入牌桌视图）

## 6. 测试

后端（`pytest`，CI 自动收集）：

- 带配置建桌：盲注生效到 `deal_new_hand` 发出的牌局
- 非法配置（bb≤sb、座位数越界、买入过低）→ 400
- 按座位等级驱动 bot：monkeypatch `bot_registry.create` 捕获 bot 名称
- 踢 bot：`stand_up {seat_idx}` 移除非人类座位成功；试图踢人类座位 → error
- 桌子列表/摘要包含配置与座位明细

前端：

- `npm run build` 通过
- 手动冒烟：建房 → 分享链接 → 另一浏览器标签入座确认页加入 → 手动加 L3 bot → 开打

CI 无需改动（无新后端模块，tests/ 全目录自动收集）。

## 7. 已知限制（本迭代不修）

- **牌局进行中刷新页面**：断连触发 `stand_up` 把玩家从 `game_state.players` 移除——重新入座即新玩家身份；若手牌正好轮到被移出的玩家，该手牌会停住（需打完整手或等下一手）。这是既有行为，涉及断线重连设计，另行立项。
- 房间无生命周期管理：无人房间永久驻留内存（既有行为）。
