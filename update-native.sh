#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[S-UI Manager] %s\n' "$*"
}

fail() {
  printf '[S-UI Manager] 错误：%s\n' "$*" >&2
  exit 1
}

if [ "$(id -u)" -ne 0 ]; then
  fail "请使用 root 用户执行：sudo bash update-native.sh"
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="/etc/s-ui-manager"
INSTALL_CONFIG="${CONFIG_DIR}/install.conf"
ENV_FILE="${CONFIG_DIR}/s-ui-manager.env"
BACKUP_DIR="/var/backups/s-ui-manager"
SERVICE_GROUP="sui-manager"

if [ -r "$INSTALL_CONFIG" ]; then
  # 该文件由 root 安装脚本生成，且权限为 0600。
  # shellcheck disable=SC1090
  . "$INSTALL_CONFIG"
else
  APP_DIR="$SCRIPT_DIR"
  HTTP_PORT="8080"
  BIND_ADDRESS="0.0.0.0"
fi

BIND_ADDRESS="${BIND_ADDRESS:-0.0.0.0}"

if [[ ! "${APP_DIR:-}" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  fail "安装路径无效"
fi
if [[ ! "${HTTP_PORT:-}" =~ ^[0-9]+$ ]]; then
  fail "安装端口无效"
fi
if [ "$BIND_ADDRESS" != "0.0.0.0" ] && [ "$BIND_ADDRESS" != "127.0.0.1" ]; then
  fail "监听地址无效"
fi
if [ ! -f "$APP_DIR/backend/requirements.txt" ]; then
  fail "未找到安装目录：$APP_DIR"
fi

install -d -m 0700 "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/s-ui-manager-$(date +%F-%H%M%S).tar.gz"
log "备份数据和配置到 $BACKUP_FILE"
tar -czf "$BACKUP_FILE" -C "$APP_DIR" data -C "$CONFIG_DIR" s-ui-manager.env

if [ -d "$APP_DIR/.git" ]; then
  log "拉取最新代码"
  git -C "$APP_DIR" pull --ff-only
else
  log "当前目录不是 Git 仓库，跳过 git pull"
fi

[ -f "$APP_DIR/frontend/dist/index.html" ] || fail "缺少预编译前端 frontend/dist/index.html"

log "更新 Python 后端依赖"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --disable-pip-version-check \
  -r "$APP_DIR/backend/requirements.txt"
getent group "$SERVICE_GROUP" >/dev/null 2>&1 || fail "未找到服务组：$SERVICE_GROUP，请先执行 bash suim.sh"
chown -R root:"$SERVICE_GROUP" "$APP_DIR/.venv"
chmod -R g+rX,o-rwx "$APP_DIR/.venv"

sed \
  -e "s|@APP_DIR@|$APP_DIR|g" \
  -e "s|@ENV_FILE@|$ENV_FILE|g" \
  "$APP_DIR/deploy/s-ui-manager.service" > /etc/systemd/system/s-ui-manager.service

sed \
  -e "s|@HTTP_PORT@|$HTTP_PORT|g" \
  -e "s|@BIND_ADDRESS@|$BIND_ADDRESS|g" \
  -e "s|@FRONTEND_DIST@|$APP_DIR/frontend/dist|g" \
  "$APP_DIR/deploy/nginx-native.conf" > /etc/nginx/conf.d/s-ui-manager.conf

find "$APP_DIR/frontend/dist" -type d -exec chmod 0755 {} +
find "$APP_DIR/frontend/dist" -type f -exec chmod 0644 {} +
nginx -t
systemctl daemon-reload
systemctl restart s-ui-manager
systemctl reload nginx

for _ in $(seq 1 15); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    log "更新完成，健康检查通过"
    printf '备份文件：%s\n' "$BACKUP_FILE"
    exit 0
  fi
  sleep 1
done

fail "更新后健康检查失败。备份位于：$BACKUP_FILE"
