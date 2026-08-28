# Sekhmet

德州扑克游戏与训练平台 — Python FastAPI + WebSocket + React。

## Docker 一键部署（推荐）

```bash
docker compose up --build
# 浏览器访问 http://localhost:8000
```

- 单容器：FastAPI 后端 + 托管前端构建产物（`/api`、`/ws`、SPA 同端口）
- SQLite 数据（对局历史 / 账号 / 战绩）持久化在 `sekhmet-data` 卷
- 生产部署请设置签名密钥：`SEKHMET_AUTH_SECRET=... docker compose up -d`

## 本地开发

```bash
# 后端（端口 8000）
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn sekhmet.main:app --reload

# 前端（端口 5173，代理 /api 与 /ws 到 8000）
cd frontend && npm install && npm run dev
```

## 测试

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -v
cd frontend && npm run test
```
