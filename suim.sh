#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

log() {
  printf '[S-UI Manager] %s\n' "$*"
}

fail() {
  printf '[S-UI Manager] 错误：%s\n' "$*" >&2
  exit 1
}

if [ "$(id -u)" -ne 0 ]; then
  fail "请使用 root 用户执行：sudo bash suim.sh"
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${SUI_MANAGER_DIR:-$SCRIPT_DIR}"
HTTP_PORT="${SUI_HTTP_PORT:-8080}"
BIND_ADDRESS="${SUI_BIND_ADDRESS:-0.0.0.0}"
SERVICE_USER="sui-manager"
SERVICE_GROUP="sui-manager"
CONFIG_DIR="/etc/s-ui-manager"
ENV_FILE="${CONFIG_DIR}/s-ui-manager.env"
INSTALL_CONFIG="${CONFIG_DIR}/install.conf"
SERVICE_FILE="/etc/systemd/system/s-ui-manager.service"
NGINX_FILE="/etc/nginx/conf.d/s-ui-manager.conf"

if [[ ! "$APP_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  fail "项目路径只能包含字母、数字、点、下划线、短横线和斜杠"
fi
if [[ "$APP_DIR" == /root || "$APP_DIR" == /root/* ]]; then
  fail "请将项目放在 /opt/s-ui-manager 等非 /root 路径后再安装"
fi
if [[ ! "$HTTP_PORT" =~ ^[0-9]+$ ]] || [ "$HTTP_PORT" -lt 1 ] || [ "$HTTP_PORT" -gt 65535 ]; then
  fail "SUI_HTTP_PORT 必须是 1-65535 之间的端口号"
fi
if [ "$BIND_ADDRESS" != "0.0.0.0" ] && [ "$BIND_ADDRESS" != "127.0.0.1" ]; then
  fail "SUI_BIND_ADDRESS 只能是 0.0.0.0 或 127.0.0.1"
fi
if [ ! -f "$APP_DIR/backend/requirements.txt" ] || [ ! -f "$APP_DIR/deploy/s-ui-manager.service" ]; then
  fail "未找到完整源码，请在 S-UI Manager 项目根目录执行本脚本"
fi

if [ ! -r /etc/os-release ]; then
  fail "无法识别操作系统"
fi
. /etc/os-release
case "${ID:-}" in
  debian|ubuntu) ;;
  *) fail "当前仅支持 Debian 12 和 Ubuntu 22.04/24.04" ;;
esac

log "安装 Python、Nginx 和基础工具"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx curl ca-certificates openssl git

if [ ! -f "$APP_DIR/frontend/dist/index.html" ]; then
  log "未找到预编译前端，尝试在本机编译"
  command -v node >/dev/null 2>&1 || fail "缺少 frontend/dist，且未安装 Node.js 18+"
  command -v npm >/dev/null 2>&1 || fail "缺少 frontend/dist，且未安装 npm"
  NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
  [ "$NODE_MAJOR" -ge 18 ] || fail "前端编译需要 Node.js 18 或更高版本"
  (
    cd "$APP_DIR/frontend"
    if [ -f package-lock.json ]; then npm ci; else npm install; fi
    npm run build
  )
fi

log "创建独立运行用户和数据目录"
getent group "$SERVICE_GROUP" >/dev/null 2>&1 || groupadd --system "$SERVICE_GROUP"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_GROUP" --home-dir "$APP_DIR" \
    --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "$APP_DIR/data"

log "创建 Python 虚拟环境并安装后端依赖"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --disable-pip-version-check \
  -r "$APP_DIR/backend/requirements.txt"

# 虚拟环境由 root 创建；授予服务组只读和执行权限。
# umask 027 会让新目录默认为 0750，若仍属于 root:root，
# Systemd 中的低权限用户会以 203/EXEC、Permission denied 启动失败。
chown -R root:"$SERVICE_GROUP" "$APP_DIR/.venv"
chmod -R g+rX,o-rwx "$APP_DIR/.venv"

install -d -m 0750 "$CONFIG_DIR"
NEW_ADMIN_PASSWORD=""
if [ ! -f "$ENV_FILE" ]; then
  ADMIN_USERNAME_VALUE="${SUI_ADMIN_USERNAME:-admin}"
  ADMIN_PASSWORD_VALUE="${SUI_ADMIN_PASSWORD:-$(openssl rand -hex 18)}"
  SECRET_KEY_VALUE="${SUI_SECRET_KEY:-$(openssl rand -hex 32)}"
  NEW_ADMIN_PASSWORD="$ADMIN_PASSWORD_VALUE"

  umask 077
  cat >"$ENV_FILE" <<EOF
DATABASE_URL=sqlite:///$APP_DIR/data/sui_manager.db
SECRET_KEY=$SECRET_KEY_VALUE
TOKEN_ENCRYPTION_KEY=
ADMIN_USERNAME=$ADMIN_USERNAME_VALUE
ADMIN_PASSWORD=$ADMIN_PASSWORD_VALUE
ACCESS_TOKEN_MINUTES=720
NODE_TIMEOUT_SECONDS=8
EOF
  chmod 0600 "$ENV_FILE"
  umask 027
else
  log "保留已有管理员密码和系统密钥：$ENV_FILE"
fi

cat >"$INSTALL_CONFIG" <<EOF
APP_DIR='$APP_DIR'
HTTP_PORT='$HTTP_PORT'
BIND_ADDRESS='$BIND_ADDRESS'
EOF
chmod 0600 "$INSTALL_CONFIG"

log "安装 Systemd 服务"
sed \
  -e "s|@APP_DIR@|$APP_DIR|g" \
  -e "s|@ENV_FILE@|$ENV_FILE|g" \
  "$APP_DIR/deploy/s-ui-manager.service" >"$SERVICE_FILE"
chmod 0644 "$SERVICE_FILE"

log "安装 Nginx 配置"
sed \
  -e "s|@HTTP_PORT@|$HTTP_PORT|g" \
  -e "s|@BIND_ADDRESS@|$BIND_ADDRESS|g" \
  -e "s|@FRONTEND_DIST@|$APP_DIR/frontend/dist|g" \
  "$APP_DIR/deploy/nginx-native.conf" >"$NGINX_FILE"
chmod 0644 "$NGINX_FILE"

find "$APP_DIR/frontend/dist" -type d -exec chmod 0755 {} +
find "$APP_DIR/frontend/dist" -type f -exec chmod 0644 {} +

nginx -t
systemctl daemon-reload
systemctl enable --now s-ui-manager
systemctl enable --now nginx
systemctl reload nginx

log "等待后端健康检查"
HEALTH_OK=0
for _ in $(seq 1 15); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    HEALTH_OK=1
    break
  fi
  sleep 1
done
[ "$HEALTH_OK" -eq 1 ] || fail "服务未通过健康检查，请执行 journalctl -u s-ui-manager -n 100 查看日志"

printf '\nS-UI Manager 原生安装完成。\n'
if [ "$BIND_ADDRESS" = "127.0.0.1" ]; then
  printf '本机访问地址：http://127.0.0.1:%s（请配置 HTTPS 反向代理）\n' "$HTTP_PORT"
else
  printf '访问地址：http://服务器IP:%s\n' "$HTTP_PORT"
fi
if [ -n "$NEW_ADMIN_PASSWORD" ]; then
  printf '管理员用户名：%s\n' "$ADMIN_USERNAME_VALUE"
  printf '管理员密码：%s\n' "$NEW_ADMIN_PASSWORD"
  printf '请立即妥善保存该密码。\n'
else
  printf '管理员账号：沿用 %s 中的现有配置\n' "$ENV_FILE"
fi
printf '服务状态：systemctl status s-ui-manager\n'
printf '运行日志：journalctl -u s-ui-manager -f\n'
