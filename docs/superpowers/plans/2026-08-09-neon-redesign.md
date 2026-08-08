# 前端霓虹重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Lobby 与 GameTable 全面换肤为青蓝霓虹夜场风格（胶囊跑道桌、角标牌面、头像座位、滑杆加注），纯前端改动。

**Architecture:** 全量重写 `game.css`（设计令牌 + 所有样式）为地基；随后逐组件改标记（CardView 角标、PlayerSeat 头像、OvalTable 桌面多层、Lobby logo/房卡、ActionBar 滑杆）。无后端/协议/依赖变更。

**Tech Stack:** React 19 + Vite + TypeScript，纯 CSS。

**Spec:** `docs/superpowers/specs/2026-08-09-neon-redesign-design.md`
**设计稿（对照资产）:** `.superpowers/brainstorm/319441-1786211467/content/neon-table-v3.html`、`neon-lobby.html`

## Global Constraints

- 工作分支 `feat/neon-redesign`（已包含 spec 提交）；禁止直接提交 main
- 纯前端换肤：**不改 ws/REST 协议、不改后端、不加 npm 依赖、不改路由**
- 每个任务结束必须 `cd frontend && npm run build` 绿 + `npx oxlint src` 干净
- 后端测试不受影响，但每个任务提交前跑一遍确认：`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`（184 passed）
- commit 带 `Co-Authored-By: Claude <noreply@anthropic.com>` 尾注
- UI 文案保持英文（Fold/Check/Call/Raise/All-in 等现有文案不动；设计稿里的中文仅示意）
- `.seat-wrap` 锚定机制（wrapper 带 seat-N + position:absolute，内层 player-seat static）必须保持——这是 PR #10 修过的 bug

---

### Task 1: game.css 全量重写（纯 CSS 地基）

**Files:**
- Modify: `frontend/src/styles/game.css`（整文件替换）

**Interfaces:**
- Consumes: 现有组件 className（.card, .player-seat, .seat-0..8, .seat-wrap, .action-bar 等）
- Produces: 后续任务 markup 会用到的类：`.corner`、`.pip`、`.avatar`、`.felt-cloth`、`.felt-rail`、`.bet-line`、`.felt-watermark`、`.hero-cards`、`.lobby-logo`、`.lobby-panel`、`.seat-dots`、`.dot`（`.full`/`.bot`）、`.phase-pill`（`.waiting`/`.playing`）、`.raise-slider`。本任务只落 CSS，这些类在 Task 2/3/4 的 markup 中启用。

- [ ] **Step 1: 整文件替换 game.css**

```css
/* ---- Neon Night Theme (青蓝夜场) ---- */
:root {
  --bg: #05080f;
  --surface: #0b1424;
  --cyan: #22d3ee;
  --cyan-dim: #164e63;
  --cyan-text: #a5f3fc;
  --gold: #fbbf24;
  --gold-text: #fde68a;
  --rose: #fb7185;
  --purple: #a78bfa;
  --text: #e2e8f0;
  --text-dim: #64748b;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

/* ---- Layout ---- */
.app { max-width: 960px; margin: 0 auto; padding: 16px; }
.page-title {
  font-size: 1.2rem; color: var(--cyan-text); letter-spacing: 4px;
  margin-bottom: 16px; text-transform: uppercase;
}

/* ---- Buttons & inputs ---- */
.btn {
  background: transparent; color: var(--cyan-text);
  border: 1.5px solid var(--cyan); border-radius: 6px;
  padding: 10px 20px; font-size: 0.95rem; font-weight: 600;
  cursor: pointer; transition: box-shadow 0.15s, opacity 0.15s;
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.25);
}
.btn:hover { box-shadow: 0 0 16px rgba(34, 211, 238, 0.5); }
.btn:disabled { opacity: 0.35; cursor: not-allowed; box-shadow: none; }
.btn-sm { padding: 6px 14px; font-size: 0.85rem; }
.btn.gold { border-color: var(--gold); color: var(--gold-text); box-shadow: 0 0 8px rgba(251, 191, 36, 0.3); }
.btn.gold:hover { box-shadow: 0 0 16px rgba(251, 191, 36, 0.55); }

.input {
  background: var(--surface); border: 1.5px solid var(--cyan-dim); color: var(--text);
  padding: 8px 12px; border-radius: 6px; font-size: 0.95rem; width: 180px;
}
.input:focus { outline: none; border-color: var(--cyan); box-shadow: 0 0 10px rgba(34, 211, 238, 0.35); }
select.input { width: auto; }

/* ---- Lobby ---- */
.lobby { display: flex; flex-direction: column; gap: 18px; }
.lobby-logo { text-align: center; margin: 4vh 0 8px; }
.lobby-logo .spade {
  font-size: 2.2rem; color: var(--cyan);
  text-shadow: 0 0 20px rgba(34, 211, 238, 0.8);
}
.lobby-logo h1 { font-size: 1.35rem; letter-spacing: 7px; font-weight: 800; margin-top: 4px; }
.lobby-logo .sub {
  font-size: 0.65rem; letter-spacing: 3px; color: var(--text-dim);
  margin-top: 4px; text-transform: uppercase;
}
.lobby-panel {
  background: rgba(34, 211, 238, 0.04); border: 1px solid rgba(34, 211, 238, 0.22);
  border-radius: 10px; padding: 14px 16px;
}
.lobby-panel .panel-label {
  font-size: 0.65rem; letter-spacing: 2px; color: var(--cyan-text);
  text-transform: uppercase; margin-bottom: 10px;
}
.lobby-actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.lobby-actions .input { width: auto; font-size: 0.85rem; }
.lobby-actions .btn { margin-left: auto; }

.table-list { display: flex; flex-direction: column; gap: 10px; }
.table-card {
  background: var(--surface); border: 1.5px solid var(--cyan-dim);
  border-radius: 10px; padding: 12px 16px; cursor: pointer;
  display: flex; justify-content: space-between; align-items: center;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.08);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.table-card:hover { border-color: var(--cyan); box-shadow: 0 0 18px rgba(34, 211, 238, 0.3); }
.table-card .id { font-family: monospace; font-size: 0.9rem; color: var(--cyan-text); }
.table-card .info { font-size: 0.75rem; color: var(--text-dim); margin-top: 3px; }
.seat-dots { display: flex; gap: 4px; margin-top: 6px; }
.dot { width: 9px; height: 9px; border-radius: 50%; border: 1px solid var(--cyan-dim); }
.dot.full { background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 6px rgba(34, 211, 238, 0.6); }
.dot.bot { background: #7c3aed; border-color: var(--purple); box-shadow: 0 0 6px rgba(167, 139, 250, 0.5); }
.phase-pill {
  font-size: 0.62rem; padding: 3px 10px; border-radius: 8px; letter-spacing: 1px;
  text-transform: uppercase; white-space: nowrap;
}
.phase-pill.waiting { border: 1px solid rgba(52, 211, 153, 0.5); color: #6ee7b7; }
.phase-pill.playing { border: 1px solid rgba(251, 191, 36, 0.5); color: var(--gold-text); }

/* ---- Join panel ---- */
.join-panel { max-width: 480px; margin: 8vh auto; text-align: center; }
.join-panel h2 { color: var(--cyan-text); letter-spacing: 2px; margin-bottom: 10px; }
.join-panel .room-meta { color: var(--text-dim); font-size: 0.9rem; margin-bottom: 6px; }
.join-panel .lobby-actions { justify-content: center; margin-top: 14px; }
.join-hint { color: var(--gold-text); font-size: 0.85rem; margin-top: 10px; }

/* ---- Game table page ---- */
.game-table { display: flex; flex-direction: column; align-items: center; gap: 14px; }
.table-head { display: flex; justify-content: space-between; width: 100%; align-items: center; }
.table-head .logo {
  font-size: 0.75rem; letter-spacing: 3px; color: var(--cyan-text);
  text-transform: uppercase; font-weight: 700;
}
.phase-label { font-size: 0.75rem; color: var(--text-dim); font-family: monospace; }

/* ---- The table: capsule racetrack shape ---- */
.table-felt {
  position: relative; width: 100%; max-width: 780px; aspect-ratio: 2.35 / 1;
  border-radius: 999px;
  background: #0a1018;                                   /* 扶手垫基底 */
  box-shadow:
    0 0 0 2px rgba(34, 211, 238, 0.35),                  /* 外沿霓虹勾线 */
    0 0 26px rgba(34, 211, 238, 0.30),                   /* 外辉光 */
    0 0 90px rgba(34, 211, 238, 0.12),
    0 24px 60px rgba(0, 0, 0, 0.75);                     /* 落地影 */
}
.felt-rail {  /* 扶手垫圆柱高光 */
  position: absolute; inset: 3px; border-radius: 999px; pointer-events: none;
  box-shadow: inset 0 3px 4px rgba(160, 220, 255, 0.10), inset 0 -4px 8px rgba(0, 0, 0, 0.6);
}
.felt-cloth {  /* 台呢 */
  position: absolute; inset: 16px; border-radius: 999px; overflow: hidden;
  pointer-events: none;
  background: radial-gradient(ellipse at 50% 32%, #10273f 0%, #0a1a2e 45%, #060f1d 100%);
  box-shadow: inset 0 0 40px rgba(0, 0, 0, 0.65), inset 0 0 6px rgba(34, 211, 238, 0.25);
}
.felt-cloth::before {  /* 织物噪点 */
  content: ''; position: absolute; inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E");
  opacity: 0.10; mix-blend-mode: overlay;
}
.felt-cloth::after {  /* 顶部射灯 */
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(ellipse 65% 60% at 50% 26%, rgba(140, 210, 255, 0.12) 0%, transparent 70%);
}
.bet-line {
  position: absolute; inset: 15% 12%; border-radius: 999px; pointer-events: none;
  border: 1.5px dashed rgba(34, 211, 238, 0.32);
}
.felt-watermark {
  position: absolute; top: 44%; left: 50%; transform: translate(-50%, -50%);
  font-size: 0.9rem; letter-spacing: 6px; color: rgba(148, 197, 255, 0.10);
  font-weight: 800; pointer-events: none;
}

/* ---- Community cards ---- */
.community-cards {
  position: absolute; top: 52%; left: 50%; transform: translate(-50%, -50%);
  display: flex; gap: 7px;
}

/* ---- Card (角标式) ---- */
.card {
  width: 42px; height: 60px; border-radius: 6px;
  background: var(--surface); position: relative;
  display: flex; align-items: center; justify-content: center;
}
.card .corner {
  position: absolute; top: 3px; left: 4px;
  font-size: 0.62rem; font-weight: 700; line-height: 1.05; text-align: center;
}
.card .pip { font-size: 1.3rem; }
.card-black { border: 1.5px solid var(--cyan); color: var(--text); box-shadow: 0 0 12px rgba(34, 211, 238, 0.4); }
.card-red { border: 1.5px solid var(--rose); color: var(--rose); box-shadow: 0 0 12px rgba(251, 113, 133, 0.4); }
.card-back {
  border: 1.5px solid #155e75;
  background: repeating-linear-gradient(45deg, #0b1424, #0b1424 4px, #0e1a2e 4px, #0e1a2e 8px);
}
.card.big { width: 52px; height: 74px; }
.card.big .pip { font-size: 1.6rem; }
.card.big .corner { font-size: 0.72rem; }
.card.small { width: 30px; height: 42px; }
.card.small .pip { font-size: 0.9rem; }
.card.small .corner { font-size: 0.5rem; }

/* ---- Player seat (头像式) ---- */
.player-seat { display: flex; flex-direction: column; align-items: center; gap: 3px; }
.player-seat .avatar {
  width: 42px; height: 42px; border-radius: 50%;
  background: var(--surface); border: 1.5px solid var(--cyan); color: var(--cyan-text);
  display: flex; align-items: center; justify-content: center;
  font-size: 0.6rem; font-weight: 700;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.3);
  position: relative;
}
.player-seat.me .avatar {
  width: 50px; height: 50px;
  border-color: var(--gold); color: var(--gold-text);
  box-shadow: 0 0 16px rgba(251, 191, 36, 0.55);
}
.player-seat.active .avatar { animation: seat-pulse 1.2s infinite; }
@keyframes seat-pulse { 50% { box-shadow: 0 0 22px rgba(34, 211, 238, 0.85); } }
.player-seat.me.active .avatar { animation: seat-pulse-gold 1.2s infinite; }
@keyframes seat-pulse-gold { 50% { box-shadow: 0 0 24px rgba(251, 191, 36, 0.9); } }
.player-seat .name { font-size: 0.62rem; color: #94a3b8; max-width: 84px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.player-seat .stack { font-size: 0.64rem; color: var(--cyan-text); font-weight: 600; }
.player-seat.me .stack { color: var(--gold-text); }
.player-seat.folded .name { color: #555; text-decoration: line-through; }
.player-seat.folded .avatar { opacity: 0.4; box-shadow: none; }
.player-seat .bet {
  font-size: 0.6rem; color: var(--gold-text);
  background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.35);
  padding: 1px 8px; border-radius: 8px; white-space: nowrap;
}
.player-seat .cards { display: flex; gap: 5px; margin-top: 4px; }

/* Seat positions (逻辑不变，仍由 .seat-N 定位) */
.seat-0 { bottom: 5%; left: 50%; transform: translateX(-50%); }
.seat-1 { bottom: 18%; right: 8%; }
.seat-2 { top: 35%; right: 2%; }
.seat-3 { top: 8%; right: 20%; }
.seat-4 { top: 5%; left: 50%; transform: translateX(-50%); }
.seat-5 { top: 8%; left: 20%; }
.seat-6 { top: 35%; left: 2%; }
.seat-7 { bottom: 18%; left: 8%; }
.seat-8 { top: 6%; left: 32%; }

/* seat-wrap 锚定机制（PR #10 修复，勿动） */
.seat-wrap { position: absolute; }
.seat-wrap .player-seat { position: static; transform: none; }
.bot-badge {
  position: absolute; top: -6px; right: -8px;
  background: #1b1032; color: var(--purple); font-size: 11px;
  border: 1px solid rgba(167, 139, 250, 0.5); border-radius: 8px; padding: 0 5px;
}
.kick-btn {
  background: none; border: none; color: var(--rose); cursor: pointer;
  font-size: 12px; margin-left: 3px; padding: 0;
}

/* Empty seat + bot controls */
.empty-seat { position: absolute; }
.add-bot-btn {
  background: rgba(34, 211, 238, 0.06); color: var(--cyan-text);
  border: 1.5px dashed var(--cyan-dim); border-radius: 999px;
  width: 46px; height: 46px; cursor: pointer; font-size: 0.62rem;
  transition: box-shadow 0.15s;
}
.add-bot-btn:hover { box-shadow: 0 0 12px rgba(34, 211, 238, 0.4); border-color: var(--cyan); }
.bot-level-picker {
  display: flex; gap: 4px; background: var(--surface);
  border: 1px solid var(--cyan-dim); border-radius: 8px; padding: 4px;
}

/* ---- Pot ---- */
.pot-display {
  position: absolute; top: 30%; left: 50%; transform: translate(-50%, -50%);
  display: flex; align-items: center; gap: 4px;
}
.pot-amount {
  color: var(--cyan-text); font-weight: 700; font-size: 0.72rem;
  background: rgba(34, 211, 238, 0.1); border: 1px solid rgba(34, 211, 238, 0.45);
  padding: 3px 12px; border-radius: 10px;
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.25);
}

/* ---- Action bar ---- */
.action-bar {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  justify-content: center; padding: 8px 0;
}
.action-bar .btn { min-width: 64px; font-size: 0.8rem; padding: 8px 20px; }
.action-bar .btn.fold { border-color: #475569; color: #94a3b8; box-shadow: none; }
.action-bar .btn.check { border-color: var(--cyan); color: var(--cyan-text); }
.action-bar .btn.raise { border-color: var(--gold); color: var(--gold-text); box-shadow: 0 0 10px rgba(251, 191, 36, 0.3); }
.action-bar .btn.allin { border-color: #8b2020; color: #ffd0d0; box-shadow: none; }
.raise-slider { accent-color: var(--cyan); width: 150px; }

/* ---- Status / misc ---- */
.waiting-text { color: var(--text-dim); font-style: italic; }
.hand-result {
  background: rgba(34, 211, 238, 0.06); border: 1px solid rgba(34, 211, 238, 0.35);
  border-radius: 8px; padding: 12px 16px; max-width: 420px;
}
.hand-result h3 { color: var(--cyan-text); margin-bottom: 8px; letter-spacing: 2px; }
.award { display: flex; justify-content: space-between; font-size: 0.9rem; padding: 2px 0; }
.award .winner { color: var(--gold-text); }
.history { font-size: 0.75rem; color: var(--text-dim); max-height: 80px; overflow-y: auto; }
```

注意：旧类 `.card-red/.card-black` 的"整卡居中文本"样式被角标结构（`.corner` + `.pip`）取代；`.rank/.suit` 两类的旧样式删除（Task 2 改 CardView markup 对应）。中间态（本任务完成后、Task 2 前）牌面文字会挤在一起——**视觉退化是预期的**，build 不受影响。

- [ ] **Step 2: 构建验证**

```bash
cd frontend && npm run build && npx oxlint src
```
Expected: 绿（纯 CSS 无 TS 影响）

- [ ] **Step 3: 后端回归 + 提交**

```bash
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q   # 184 passed
cd .. && git add frontend/src/styles/game.css
git commit -m "feat: neon night theme foundation (game.css rewrite)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 牌桌组件标记（CardView 角标、PlayerSeat 头像、OvalTable 多层桌面）

**Files:**
- Modify: `frontend/src/components/table/CardView.tsx`（整文件替换）
- Modify: `frontend/src/components/table/PlayerSeat.tsx`（整文件替换）
- Modify: `frontend/src/components/table/OvalTable.tsx`（桌面多层结构 + avatarLabel）
- Modify: `frontend/src/components/table/PotDisplay.tsx`（◈ 符号）
- Modify: `frontend/src/pages/GameTable.tsx`（页头加 logo、class table-head）

**Interfaces:**
- Consumes: Task 1 的 CSS 类
- Produces:
  - `CardView({ card?, small?, big? })`——新增可选 `big`；markup 为 `<span class="corner">{rank}<br/>{suit}</span><span class="pip">{suit}</span>`
  - `PlayerSeat({ player, seatIndex, isCurrent, holeCards?, avatarLabel, isMe })`——`holeCards` 仍在（仅我有）；**showCards prop 删除**（对手底牌从未有数据，死代码）；新增 `avatarLabel: string`、`isMe: boolean`
  - OvalTable 计算 avatarLabel：bot → `L{bot_level ?? 2}`；我 → `你`；其他人类 → 名字首字符

- [ ] **Step 1: CardView.tsx 替换**

```tsx
interface CardViewProps {
  card?: string;   // e.g. "A♠", "10♥", "K♦", "7♣" — or empty for face-down
  small?: boolean;
  big?: boolean;
}

const RED_SUITS = ['♥', '♦'];

export default function CardView({ card, small, big }: CardViewProps) {
  const size = big ? 'big' : small ? 'small' : '';
  if (!card) {
    return <span className={`card card-back ${size}`} />;
  }

  const suit = card.slice(-1);
  const rank = card.slice(0, -1);
  const isRed = RED_SUITS.includes(suit);

  return (
    <span className={`card ${isRed ? 'card-red' : 'card-black'} ${size}`} title={card}>
      <span className="corner">{rank}<br />{suit}</span>
      <span className="pip">{suit}</span>
    </span>
  );
}
```

- [ ] **Step 2: PlayerSeat.tsx 替换**

```tsx
import CardView from './CardView';
import type { PlayerInfo } from '../../hooks/useGameState';

interface Props {
  player: PlayerInfo;
  seatIndex: number;
  isCurrent: boolean;
  holeCards?: string[];   // only ever set for the hero
  avatarLabel: string;
  isMe: boolean;
}

export default function PlayerSeat({ player, seatIndex, isCurrent, holeCards, avatarLabel, isMe }: Props) {
  const folded = !player.is_active;
  const cls = [
    'player-seat',
    `seat-${seatIndex}`,
    isCurrent ? 'active' : '',
    folded ? 'folded' : '',
    isMe ? 'me' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={cls}>
      <div className="avatar">{avatarLabel}</div>
      <div className="name">{player.name}</div>
      <div className="stack">{player.stack}</div>
      {player.current_bet > 0 && <div className="bet">{player.current_bet}</div>}
      {holeCards && (
        <div className="cards">
          {holeCards.map((c, i) => <CardView key={i} card={c} big />)}
        </div>
      )}
    </div>
  );
}
```

注意：`showCards` prop 删除——它只对 isMe 有数据，而我的手牌永远正面朝上。对手位置的假牌背（两张 face-down）在新设计中删除（头像即座位标识）。

- [ ] **Step 3: OvalTable.tsx 修改**

在 `.table-felt` 内最前面插入桌面层（在 community cards / pot / seats 之前）：

```tsx
    <div className="table-felt">
      <div className="felt-rail" />
      <div className="felt-cloth" />
      <div className="bet-line" />
      <div className="felt-watermark">♠ SEKHMET</div>
      {showCommunity && <CommunityCards cards={communityCards} />}
      <PotDisplay amount={pot} />
      ...
```

PlayerSeat 调用处改为（seat-wrap 结构与 bot 徽章/踢按钮保持不变）：

```tsx
            <PlayerSeat
              player={merged}
              seatIndex={slot}
              isCurrent={currentPlayerIdx === seat.seat_idx}
              holeCards={isMe ? holeCards : undefined}
              avatarLabel={
                seat.is_human
                  ? (isMe ? '你' : seat.name.charAt(0))
                  : `L${seat.bot_level ?? 2}`
              }
              isMe={isMe}
            />
```

- [ ] **Step 4: PotDisplay 与 GameTable 页头**

PotDisplay.tsx：

```tsx
export default function PotDisplay({ amount }: Props) {
  return (
    <div className="pot-display">
      <span className="pot-amount">◈ POT {amount}</span>
    </div>
  );
}
```

GameTable.tsx 页头（替换现在 flex 那行 div）：

```tsx
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        <span className="logo">♠ Sekhmet</span>
        <span className="phase-label">
          {tableId} · {state.phase}{!connected && ' (disconnected)'}
        </span>
        <button className="btn btn-sm gold" onClick={() => send({ type: 'start_hand' })}
                disabled={state.phase !== 'WAITING' && state.phase !== 'SHOWDOWN'}>
          Deal
        </button>
      </div>
```

- [ ] **Step 5: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q
cd .. && git add frontend/src
git commit -m "feat: neon table markup — corner-index cards, avatar seats, layered capsule felt

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Lobby 霓虹化（logo、建房面板、房卡圆点）

**Files:**
- Modify: `frontend/src/pages/Lobby.tsx`

**Interfaces:**
- Consumes: Task 1 的 `.lobby-logo/.lobby-panel/.seat-dots/.dot/.phase-pill` 样式；现有 `TableInfo` 类型（含 seats 明细与 config）
- Produces: 无新接口

- [ ] **Step 1: Lobby.tsx 修改**

`return` 部分替换为（create/refresh 逻辑不动）：

```tsx
  return (
    <div className="lobby">
      <div className="lobby-logo">
        <div className="spade">♠</div>
        <h1>SEKHMET</h1>
        <div className="sub">Poker Trainer</div>
      </div>

      <div className="lobby-panel">
        <div className="panel-label">New Table</div>
        <div className="lobby-actions">
          <input className="input" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} />
          <select className="input" value={tier.label}
                  onChange={e => {
                    const t = BLIND_TIERS.find(x => x.label === e.target.value)!;
                    setTier(t);
                    setBuyin(t.bb * 100);
                  }}>
            {BLIND_TIERS.map(t => <option key={t.label} value={t.label}>Blinds {t.label}</option>)}
          </select>
          <input className="input" type="number" placeholder="Default buy-in" value={buyin}
                 onChange={e => setBuyin(Number(e.target.value))} />
          <select className="input" value={maxSeats} onChange={e => setMaxSeats(Number(e.target.value))}>
            {[2, 3, 4, 5, 6, 7, 8, 9].map(n => <option key={n} value={n}>{n} seats</option>)}
          </select>
          <button className="btn gold" onClick={create} disabled={!name}>+ New Table</button>
        </div>
      </div>

      <div className="table-list">
        {tables.length === 0 && <div className="waiting-text">No active tables. Create one!</div>}
        {tables.map(t => (
          <div key={t.table_id} className="table-card"
               onClick={() => { localStorage.setItem('pokerName', name); navigate(`/game/${t.table_id}`); }}>
            <div>
              <span className="id">{t.table_id}</span>
              <div className="info">
                {t.config.small_blind}/{t.config.big_blind} · buy-in {t.config.default_buyin}
              </div>
              <div className="seat-dots">
                {t.seats.map(s => (
                  <span key={s.seat_idx} className={`dot ${s.is_human ? 'full' : 'bot'}`} />
                ))}
                {Array.from({ length: t.max_seats - t.seats.length }, (_, i) => (
                  <span key={`e${i}`} className="dot" />
                ))}
              </div>
            </div>
            <span className={`phase-pill ${t.phase === 'WAITING' ? 'waiting' : 'playing'}`}>
              {t.phase === 'WAITING' ? 'Waiting' : t.phase}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
```

（Lobby 头部不再用 `.page-title`；如该页已无 page-title 使用处，保留 CSS 类无妨。）

- [ ] **Step 2: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q
cd .. && git add frontend/src/pages/Lobby.tsx
git commit -m "feat: neon lobby — glowing logo, create panel, occupancy dots

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: ActionBar 滑杆加注

**Files:**
- Modify: `frontend/src/components/table/ActionBar.tsx`（整文件替换）

**Interfaces:**
- Consumes: 现有 props（不变）：`{ isMyTurn, currentBet, myStack, myCurrentBet, bigBlind, onAction }`
- Produces: 无接口变更；加注总额语义 = "加注到 N"（total this street），与后端 RAISE/BET 的 amount 语义一致

- [ ] **Step 1: ActionBar.tsx 替换**

```tsx
import { useState } from 'react';

interface Props {
  isMyTurn: boolean;
  currentBet: number;
  myStack: number;
  myCurrentBet: number;
  bigBlind: number;
  onAction: (action: string, amount?: number) => void;
}

export default function ActionBar({ isMyTurn, currentBet, myStack, myCurrentBet, bigBlind, onAction }: Props) {
  const toCall = Math.max(0, currentBet - myCurrentBet);
  const canCheck = toCall === 0;
  const minRaise = currentBet > 0 ? currentBet + bigBlind : bigBlind;
  const maxRaise = myStack + myCurrentBet;  // total commit this street
  const [raiseTo, setRaiseTo] = useState(minRaise);

  if (!isMyTurn) {
    return <div className="action-bar"><span className="waiting-text">Waiting for others...</span></div>;
  }

  const effectiveRaise = Math.min(Math.max(raiseTo, minRaise), maxRaise);

  return (
    <div className="action-bar">
      <button className="btn fold" onClick={() => onAction('FOLD')}>Fold</button>
      {canCheck ? (
        <button className="btn check" onClick={() => onAction('CHECK')}>Check</button>
      ) : (
        <button className="btn check" onClick={() => onAction('CALL')} disabled={toCall > myStack}>
          Call {toCall}
        </button>
      )}
      <input
        className="raise-slider"
        type="range"
        min={minRaise}
        max={Math.max(maxRaise, minRaise)}
        value={effectiveRaise}
        onChange={e => setRaiseTo(Number(e.target.value))}
        disabled={maxRaise < minRaise}
      />
      <button
        className="btn raise"
        onClick={() => onAction(currentBet > 0 ? 'RAISE' : 'BET', effectiveRaise)}
        disabled={maxRaise < minRaise}
      >
        {currentBet > 0 ? `Raise to ${effectiveRaise}` : `Bet ${effectiveRaise}`}
      </button>
      <button className="btn allin" onClick={() => onAction('ALL_IN')} disabled={myStack <= 0}>
        All-in
      </button>
    </div>
  );
}
```

要点：滑杆值是"本街总投入"（与后端 BET/RAISE 的 amount 语义一致，勿改成增量）；`maxRaise < minRaise`（筹码不足最小加注）时滑杆与加注按钮禁用，玩家只能 Fold/Call/All-in。

- [ ] **Step 2: 构建 + 回归 + 提交**

```bash
cd frontend && npm run build && npx oxlint src
cd ../backend && source .venv/bin/activate && python -m pytest tests/ -q
cd .. && git add frontend/src/components/table/ActionBar.tsx
git commit -m "feat: slider-based raise in action bar

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 主设计文档 §6.2 更新 + 全量验证 + PR

**Files:**
- Modify: `docs/superpowers/specs/2026-06-13-sekhmet-poker-platform-design.md`（§6.2 视觉风格）

- [ ] **Step 1: 更新主设计文档 §6.2**（项目原则 3：设计文档与代码不分离）

§6.2 整节替换为：

```markdown
### 6.2 视觉风格

**青蓝霓虹夜场**（2026-08-09 重设计定稿，详见 `2026-08-09-neon-redesign-design.md`）：

- **牌桌**：胶囊跑道形（长直边 + 半圆端头）——深色宽包边模拟扶手垫 + 内嵌台呢（织物噪点 + 顶部射灯）+ 青色虚线投注环
- **配色**：深底 #05080f + 青色霓虹 #22d3ee 主调；金色 #fbbf24 标记"你"和下注；红桃花色用 #fb7185
- **牌面**：角标式（左上点数+花色，中央大花色），黑花色青辉光、红花色玫红辉光，牌背斜纹
- **座位**：圆形头像（bot 直接显示等级 L1-3），你的位置金色放大，轮到行动有呼吸光环
- **加注**：滑杆（总额语义）+ 动态按钮文案
- **大厅**：发光 ♠ SEKHMET logo、座位占用圆点（青=人、紫=bot）、阶段胶囊
```

- [ ] **Step 2: 全量验证**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -q   # 184 passed
cd ../frontend && npm run build && npx oxlint src                        # 绿
```

- [ ] **Step 3: 提交、推送、开 PR**

```bash
cd .. && git add docs/
git commit -m "docs: update visual style section to neon night theme

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin feat/neon-redesign
```

（网络抖动时用 HTTPS+token 备用通道：`git push "https://x-access-token:$(gh auth token)@github.com/Quasrain-Coder/Sekhmet.git" feat/neon-redesign`。）

PR 标题：`feat: 前端霓虹夜场重设计`
PR 正文要点：设计稿链接（仓库内 .superpowers/brainstorm 路径）、四页对照（桌面/牌面/座位/大厅）、无协议无后端变更、附人工视觉验收清单。
- [ ] **Step 4: 等 CI 绿，请用户确认后合入**（项目铁律：不自行 merge）
