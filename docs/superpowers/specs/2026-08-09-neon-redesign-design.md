# Sekhmet — 前端视觉重设计（青蓝霓虹夜场）· 设计文档

> 2026-08-09 · 纯视觉重设计：不改路由、不改协议、不改后端。经可视化设计稿逐步确认（霓虹三方向 → 完整页构图 → 桌面质感 → 真实桌形），定稿于青蓝霓虹 + 胶囊跑道桌。

## 1. 背景与目标

现前端是占位级样式：扁平绿台面、细小牌面（深底卡片糊成一团）、纯文字座位、无筹码视觉。用户在三个霓虹方向中选定**青蓝夜场**，并明确两点迭代意见：桌面要有质感（多层结构）、桌形要像真实赌场桌（胶囊跑道形，非椭圆）。

目标：将 Lobby 与 GameTable 两页全面换肤为青蓝霓虹风格，达到设计稿（`.superpowers/brainstorm/319441-1786211467/content/neon-table-v3.html`、`neon-lobby.html`）的视觉效果。

非目标：不改任何 ws/REST 协议与后端代码；不改路由结构；不引入 UI 框架或构建工具变更（纯 CSS + 组件内标记调整）；不新增功能。

## 2. 设计令牌（CSS custom properties）

```
--bg:        #05080f   /* 页面底 */
--surface:   #0b1424   /* 卡片/输入框底 */
--cyan:      #22d3ee   /* 主霓虹色 */
--cyan-dim:  #164e63   /* 弱描边 */
--cyan-text: #a5f3fc   /* 青色文字 */
--gold:      #fbbf24   /* 你的位置/加注/下注额 */
--gold-text: #fde68a
--rose:      #fb7185   /* 红桃花色 */
--purple:    #a78bfa   /* bot 标记 */
--text:      #e2e8f0
--text-dim:  #64748b
```

## 3. 牌桌页（GameTable）

### 3.1 桌面（胶囊跑道形）

- 容器 `aspect-ratio: 2.35/1`、`border-radius: 999px`（跑道形的关键），深色宽包边 `#0a1018` 模拟扶手垫，上缘一道皮垫高光（inset shadow）
- 包边外：青色勾线 + 三层外辉光 + 桌面落地影
- 台呢内嵌包边内（inset ~16px），深蓝径向渐变 + SVG feTurbulence 织物噪点（overlay，opacity 0.10）+ 顶部射灯（径向高光 50% 26% 处）
- 内圈虚线投注环（cyan 32% 透明）、中央 ♠ SEKHMET 水印（10% 透明）

### 3.2 座位

- 圆形头像：cyan 描边 + 辉光，内容直接是 bot 等级（L1/L2/L3）或玩家名首字
- 你的座位：金色描边 + 更强辉光，略大（50px vs 42px）
- 轮到行动：头像呼吸光环动画（box-shadow pulse 1.2s）
- 下注额：金色小胶囊，浮于座位朝向桌心一侧
- bot 移除按钮（×）保留在徽章上，样式随新主题
- 空位 "+ Bot" 与等级选择器保留，样式随新主题
- 9 人桌槽位（seat-0..8 + SLOTS/S9 排列）逻辑不变，仅改视觉

### 3.3 牌面

- 标准角标式：左上角点数+花色小角标，中央大花色
- 黑花色（♠♣）：cyan 描边 + 辉光，浅文字；红花色（♥♦）：rose 描边 + 辉光
- 牌背：斜纹 repeating-linear-gradient + cyan-dim 描边
- 你的手牌放大（52×74 vs 公共牌 42×60）并悬浮压桌沿

### 3.4 动作栏与其他

- 描边霓虹按钮：弃牌灰、过牌/跟注 cyan、加注 gold、全下暗红
- 加注金额用 range 滑杆（accent-color cyan），按钮文案"加注到 N"实时联动
- 页头极简：← 大厅 / ♠ SEKHMET / 房间号·阶段
- 摊牌结果面板、历史记录行：随主题换肤（cyan 描边面板、gold 赢家）

## 4. 大厅页（Lobby）

- 居中 ♠ SEKHMET 发光 logo（spade 符号 cyan 大辉光 + 字母间距大标题）
- 建房面板：cyan 弱描边容器，输入框深底 cyan 描边（focus 辉光），金色"开桌"按钮
- 房卡：surface 底 + cyan-dim 描边，hover 提亮辉光；座位占用小圆点（青=人类、紫=bot、空心=空位）；阶段胶囊（等待中=绿、进行中=金）
- 入座确认页（join panel）同主题换肤

## 5. 实现要点

- 全部视觉集中在 `frontend/src/styles/game.css` 重写 + 组件 className/标记微调
- `CardView.tsx`：从"整卡居中文本"改为角标+中央花色结构（增加角标元素）
- `PlayerSeat.tsx`：从文字块改为圆形头像结构（头像 + 名 + 筹码 + 下注胶囊）；等级徽章逻辑保留
- `ActionBar.tsx`：加注输入框改 range 滑杆 + 动态文案；接口（props）不变
- `OvalTable.tsx`：座位定位类逻辑（seat-0..8、displaySlot、SLOTS/S9）不动，仅 CSS 重写；`.seat-wrap` 的徽章锚定方案（position:absolute + 内部 static）保持
- 移动端：现有媒体查询很少，本迭代不新增移动端专项（与原状一致）
- 无后端变更、无协议变更、无新依赖

## 6. 测试与验收

- `npm run build` 绿、`oxlint` 干净
- 后端 184 个测试不受影响（无后端改动）
- 人工视觉验收对照设计稿：桌面多层结构、头像光环、牌面角标、滑杆加注、大厅房卡
- CI 无需改动

## 7. 参考资产

- 设计稿（持久化在仓库）：`.superpowers/brainstorm/319441-1786211467/content/neon-table-v3.html`（牌桌）、`neon-lobby.html`（大厅）、`neon-style.html`（三方向，A 入选）
- 主设计文档 §6.2 视觉风格一节在实现完成后需更新为新主题（替换"经典赌场暗调"描述）
