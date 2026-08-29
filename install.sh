#!/usr/bin/env bash
set -e
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker 未安装。请先安装 Docker Engine + Compose plugin。"
  exit 1
fi
[ -f .env ] || cp .env.example .env
echo "请确认 .env 中 ADMIN_PASSWORD 和 SECRET_KEY 已修改。"
docker compose up -d --build
echo "S-UI Manager 已启动。默认访问端口: ${HTTP_PORT:-8080}"
