# Sekhmet

> 德州扑克游戏与训练平台 — Python FastAPI + WebSocket + React

## 开发原则

1. **禁止直接向 `main` 提交或推送代码，没有任何例外**（包括文档、配置、Claude 自己的提交）。所有改动必须：新建分支 → 提交 → push 分支 → 开 PR → 合并进 `main`。
2. **新增或修改模块时，必须同步更新 CI 的 test/coverage 步骤**，不得遗漏。
3. 设计层面的变更必须与 `docs/superpowers/specs/` 下的设计文档同步更新，设计文档与代码不分离。
4. **游戏引擎是不可变状态机**：每次动作通过 `action_processor.execute()` 产生新 `GameState` 快照，不在原对象上修改。

## Git 工作流

- 分支命名：`feat/...`、`fix/...`、`docs/...`、`refactor/...`
- PR 合并前 CI 必须通过
- commit message 中英文均可；Claude 参与的提交带 `Co-Authored-By` 尾注
- 向 `main` 合入代码必须通过 Pull Request，**由用户确认后才能合入**

## Build & Test

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/ -v
```

## 架构速览

```
浏览器                         服务端
┌──────────────┐  WebSocket    ┌──────────────────────────────┐
│ React App    │◄─────────────►│ FastAPI                       │
│ (Vite + TS)  │  JSON msgs    │  ├─ api/ws.py (消息路由)       │
│              │               │  ├─ game_engine/ (核心逻辑)    │
│              │  REST         │  ├─ ai_engine/ (Bot 工厂)      │
│              │◄─────────────►│  ├─ trainer/ (训练器)          │
│              │  (历史/场景)    │  ├─ models/ (ORM + 记录)       │
│              │               │  └─ config.py (全局配置)       │
└──────────────┘               └──────────────────────────────┘
```

## 项目结构

```
Sekhmet/
├── backend/sekhmet/
│   ├── game_engine/        # 德州扑克核心引擎
│   │   ├── deck.py         # 牌组管理
│   │   ├── hand_evaluator.py  # 手牌强度评估
│   │   ├── game_state.py   # 游戏状态机
│   │   ├── action_processor.py  # 动作校验与执行
│   │   ├── pot_manager.py  # 底池管理
│   │   └── rules/          # 规则配置（盲注等）
│   ├── ai_engine/          # AI 引擎（待实现）
│   ├── trainer/            # 情景训练器（待实现）
│   ├── api/                # FastAPI 路由（待实现）
│   ├── models/             # ORM 模型（待实现）
│   └── config.py           # 全局配置
├── frontend/               # React (Vite + TS)（待实现）
├── docs/superpowers/specs/  # 设计文档
└── .claude/skills/         # Claude 开发技能
```

## 实现进度

- [x] P1 游戏引擎核心（deck, hand_evaluator, game_state, action_processor, pot_manager）
- [ ] P2 API + WebSocket 通道
- [ ] P3 AI 引擎（rule_bot, bot_registry, gto_bot, rl_bot）
- [ ] P4 前端（React 牌桌界面）
- [ ] P5 训练器
- [ ] P6 收尾（ORM, 回放, 部署）
