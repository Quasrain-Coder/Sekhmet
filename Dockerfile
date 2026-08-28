# syntax=docker/dockerfile:1
# Sekhmet all-in-one 镜像：FastAPI 后端 + 托管前端构建产物（单容器）

# ---- Stage 1: 前端构建 ----
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: 后端运行时 ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    # SPA 静态目录（mount_spa 读取；默认仓库内 frontend/dist 仅用于本地 dev）
    SEKHMET_STATIC_DIR=/app/frontend/dist \
    # SQLite 落 /app/data，compose 挂卷持久化
    SEKHMET_DATABASE_URL=sqlite+aiosqlite:////app/data/sekhmet.db

WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/sekhmet backend/sekhmet
# 生成的训练场景库（GENERATED_DATA_DIR 按源码树解析到 backend/data）
COPY backend/data backend/data
# editable 安装：__file__ 留在源码树，场景库路径解析与本地一致
RUN pip install --no-cache-dir -e ./backend
COPY --from=frontend /build/frontend/dist frontend/dist
RUN mkdir -p /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

WORKDIR /app/backend
CMD ["uvicorn", "sekhmet.main:app", "--host", "0.0.0.0", "--port", "8000"]
