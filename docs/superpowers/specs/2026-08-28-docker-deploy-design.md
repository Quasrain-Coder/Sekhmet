# Sekhmet — Docker 化一键部署 · 设计文档

> 2026-08-28 · P6 第三项：主设计文档非功能需求"docker-compose up 一键启动；本地优先，支持家庭服务器/云，需移动端适配"落地。

## 1. 背景

- 现状只有本地 dev 流程（vite dev server 代理到 uvicorn），没有任何容器化产物
- 生产形态缺失的两块：① 前端构建产物无人托管（FastAPI 不 serve 静态文件）② 配置硬编码（DB 路径相对 cwd，容器里无法挂卷持久化）

## 2. 方案：单容器 all-in-one

一个镜像同时跑后端 + 托管前端静态文件（家庭服务器场景，无多副本/横向扩展需求，不引入 nginx）：

- **Stage 1（node:22-alpine）**：`npm ci && npm run build` 产出 `frontend/dist`
- **Stage 2（python:3.12-slim）**：editable 安装 backend（`pip install -e ./backend`，保证 `GENERATED_DATA_DIR` 按源码树解析到 `/app/backend/data/scenarios`）+ 拷入 dist，`python` 起 uvicorn 于 8000

### 2.1 后端改动（最小侵入）

1. `config.py`：`database_url` 支持环境变量 `SEKHMET_DATABASE_URL` 覆盖（默认不变，dev 行为零影响）
2. `main.py`：新增 `mount_spa(app, static_dir)`——`index.html` 存在才把 SPA 挂到 `/{full_path:path}`（静态文件命中则直出，否则回落 index.html；路径逃逸防护）。静态目录取 `SEKHMET_STATIC_DIR`，默认仓库内 `frontend/dist`。本地 dev（无 dist）行为不变

### 2.2 容器产物（仓库根）

- `Dockerfile`（多阶段，上述）
- `docker-compose.yml`：端口 `8000:8000`；`sekhmet-data` 卷挂 `/app/data`（SQLite 落卷，`SEKHMET_DATABASE_URL=sqlite+aiosqlite:////app/data/sekhmet.db`）；`SEKHMET_AUTH_SECRET` 环境变量（签名密钥，生产必须改）
- `.dockerignore`：`.git` / `node_modules` / `dist` / `.venv` / `__pycache__` / `*.db` / tests / docs

## 3. CI（遵守 CI 记忆纪律）

新增 `docker` job：`docker build` → 起容器 → 轮询 `/health` → 断言 `/` 返回 HTML、`/api/trainer/scenarios` 返回场景 JSON。这是部署链路的冒烟测试（本地无 docker，CI 即验收）。

## 4. 测试

- `tests/test_static_spa.py`：tmp 目录伪 dist——index 直出、assets 文件直出、未知路径 SPA 回落、目录不存在时不挂载（dev 行为）
- README 增加 Docker 快速启动段

## 5. 明确不做

- 多容器编排（nginx + 后端分离）、HTTPS/TLS（家庭网络场景交给反向代理或 tailscale）
- PostgreSQL（`database_url` 已是连接串，需要时用户自行切换）
- 镜像发布到 registry（用户本地 build 即可）
