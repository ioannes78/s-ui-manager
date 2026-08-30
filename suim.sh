#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

PROGRAM_NAME="S-UI Manager"
SUIM_MANAGER_API=1
SUIM_MANAGER_VERSION=2
REPO_URL="${SUI_REPO_URL:-https://github.com/ioannes78/s-ui-manager.git}"
SERVICE_NAME="s-ui-manager"
SERVICE_USER="sui-manager"
SERVICE_GROUP="sui-manager"
CONFIG_DIR="/etc/s-ui-manager"
ENV_FILE="${CONFIG_DIR}/s-ui-manager.env"
INSTALL_CONFIG="${CONFIG_DIR}/install.conf"
SERVICE_FILE="/etc/systemd/system/s-ui-manager.service"
NGINX_FILE="/etc/nginx/conf.d/s-ui-manager.conf"
COMMAND_LINK="/usr/local/bin/suim"
BACKUP_DIR="/var/backups/s-ui-manager"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

APP_DIR=""
HTTP_PORT="8080"
BIND_ADDRESS="0.0.0.0"
INSTALL_REF=""
ADMIN_USERNAME_VALUE="admin"
ADMIN_PASSWORD_VALUE=""
ENABLE_AUTOSTART="1"
LAST_BACKUP_FILE=""

log() { printf '[S-UI Manager] %s\n' "$*"; }
warn() { printf '[S-UI Manager] 警告：%s\n' "$*" >&2; }
fail() { printf '[S-UI Manager] 错误：%s\n' "$*" >&2; exit 1; }
separator() { printf '%s\n' '————————————————————————————————'; }

clear_screen() {
  if [ -t 1 ] && command -v clear >/dev/null 2>&1; then clear; fi
}

pause_screen() {
  if [ -t 0 ]; then
    printf '\n按 Enter 键继续...'
    read -r _ || true
  fi
}

confirm() {
  local prompt="${1:-确认继续？}" answer=""
  printf '%s [y/N]: ' "$prompt"
  read -r answer || return 1
  [[ "$answer" =~ ^[Yy]$ ]]
}

require_root() {
  [ "$(id -u)" -eq 0 ] || fail "请使用 root 用户执行：sudo bash suim.sh"
}

source_tree_complete() {
  local directory="$1"
  [ -f "$directory/backend/requirements.txt" ] &&
    [ -f "$directory/deploy/s-ui-manager.service" ] &&
    [ -f "$directory/deploy/nginx-native.conf" ] &&
    [ -f "$directory/suim.sh" ]
}

validate_app_dir() {
  local directory="$1"
  [[ "$directory" =~ ^/[A-Za-z0-9._/-]+$ ]] || return 1
  case "$directory" in
    /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/opt|/proc|/root|/run|/sbin|/srv|/sys|/tmp|/usr|/var|/root/*)
      return 1 ;;
  esac
}

validate_port() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -ge 1 ] && [ "$port" -le 65535 ]
}

validate_bind_address() { [ "$1" = "0.0.0.0" ] || [ "$1" = "127.0.0.1" ]; }
validate_username() { [[ "$1" =~ ^[A-Za-z0-9._-]{1,64}$ ]]; }

validate_password() {
  local password="$1"
  [ "${#password}" -ge 12 ] && [ "${#password}" -le 128 ] &&
    [[ "$password" =~ ^[A-Za-z0-9@%+=:,._!?-]+$ ]]
}

validate_ref() {
  local ref="$1"
  [ -n "$ref" ] && [ "${#ref}" -le 128 ] && [[ "$ref" != -* ]] &&
    [[ "$ref" =~ ^[A-Za-z0-9._/-]+$ ]]
}

default_app_dir() {
  if source_tree_complete "$SCRIPT_DIR" && validate_app_dir "$SCRIPT_DIR"; then
    printf '%s\n' "$SCRIPT_DIR"
  else
    printf '%s\n' '/opt/s-ui-manager'
  fi
}

load_install_config() {
  APP_DIR="$(default_app_dir)"
  HTTP_PORT="8080"
  BIND_ADDRESS="0.0.0.0"
  if [ -r "$INSTALL_CONFIG" ]; then
    # 该文件仅由本脚本以 root:root 0600 创建。
    # shellcheck disable=SC1090
    . "$INSTALL_CONFIG"
  fi
  validate_app_dir "$APP_DIR" || fail "安装配置中的 APP_DIR 无效"
  validate_port "$HTTP_PORT" || fail "安装配置中的 HTTP_PORT 无效"
  validate_bind_address "$BIND_ADDRESS" || fail "安装配置中的 BIND_ADDRESS 无效"
}

is_installed() {
  [ -r "$INSTALL_CONFIG" ] && [ -r "$ENV_FILE" ] && [ -f "$SERVICE_FILE" ]
}

write_install_config() {
  local temporary
  install -d -m 0750 "$CONFIG_DIR"
  temporary="$(mktemp "${CONFIG_DIR}/install.conf.XXXXXX")"
  {
    printf "APP_DIR='%s'\n" "$APP_DIR"
    printf "HTTP_PORT='%s'\n" "$HTTP_PORT"
    printf "BIND_ADDRESS='%s'\n" "$BIND_ADDRESS"
  } >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$INSTALL_CONFIG"
}

get_env_value() {
  local key="$1"
  [ -r "$ENV_FILE" ] || return 1
  awk -v key="$key" 'index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }' "$ENV_FILE"
}

set_env_value() {
  local key="$1" value="$2" temporary
  [ -r "$ENV_FILE" ] || fail "未找到配置文件：$ENV_FILE"
  temporary="$(mktemp "${CONFIG_DIR}/s-ui-manager.env.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    index($0, key "=") == 1 { print key "=" value; updated = 1; next }
    { print }
    END { if (!updated) print key "=" value }
  ' "$ENV_FILE" >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$ENV_FILE"
}

generate_random_hex() {
  local byte_count="$1"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$byte_count"
  else
    od -An -N "$byte_count" -tx1 /dev/urandom | tr -d ' \n'
  fi
}

generate_password() { generate_random_hex 18; }
generate_secret() { generate_random_hex 32; }

detect_os() {
  [ -r /etc/os-release ] || fail "无法识别操作系统"
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    debian|ubuntu) ;;
    *) fail "当前仅支持 Debian 12 和 Ubuntu 22.04/24.04" ;;
  esac
}

install_system_dependencies() {
  detect_os
  log "安装 Python、Nginx 和基础工具"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y python3 python3-venv python3-pip nginx curl ca-certificates openssl git iproute2
}

prepare_source_tree() {
  if source_tree_complete "$APP_DIR"; then return; fi
  if [ -e "$APP_DIR" ] && [ -n "$(find "$APP_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    fail "目标目录非空且不是完整的 S-UI Manager 源码：$APP_DIR"
  fi
  log "从 GitHub 下载源码到 $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
  source_tree_complete "$APP_DIR" || fail "下载的源码不完整"
}

ensure_clean_repository() {
  [ -d "$APP_DIR/.git" ] || fail "程序目录不是 Git 仓库，无法使用在线更新：$APP_DIR"
  [ -z "$(git -C "$APP_DIR" status --porcelain --untracked-files=no)" ] ||
    fail "检测到未提交的源码修改。请先处理这些修改再更新"
}

ensure_unified_manager_ref() {
  local target="$1" script_content
  script_content="$(git -C "$APP_DIR" show "${target}:suim.sh" 2>/dev/null)" ||
    fail "指定版本缺少 suim.sh"
  [[ "$script_content" == *'SUIM_MANAGER_API=1'* ]] ||
    fail "指定版本不支持统一 suim 管理菜单，请选择 V1.1.0 或更高版本"
}

checkout_version() {
  local ref="$1" target=""
  validate_ref "$ref" || fail "版本名称格式无效"
  ensure_clean_repository
  log "获取版本信息"
  git -C "$APP_DIR" fetch --tags --prune origin
  if git -C "$APP_DIR" show-ref --verify --quiet "refs/remotes/origin/$ref"; then
    target="refs/remotes/origin/$ref"
    ensure_unified_manager_ref "$target"
    git -C "$APP_DIR" checkout -B "$ref" "origin/$ref"
  elif git -C "$APP_DIR" show-ref --verify --quiet "refs/tags/$ref"; then
    target="refs/tags/$ref"
    ensure_unified_manager_ref "$target"
    git -C "$APP_DIR" checkout --detach "refs/tags/$ref"
  elif git -C "$APP_DIR" rev-parse --verify --quiet "${ref}^{commit}" >/dev/null; then
    target="$ref"
    ensure_unified_manager_ref "$target"
    git -C "$APP_DIR" checkout --detach "$ref"
  else
    fail "没有找到指定版本：$ref"
  fi
}

build_frontend_if_needed() {
  if [ -f "$APP_DIR/frontend/dist/index.html" ]; then return; fi
  log "未找到预编译前端，尝试在本机编译"
  command -v node >/dev/null 2>&1 || fail "缺少预编译前端，且系统未安装 Node.js 18+"
  command -v npm >/dev/null 2>&1 || fail "缺少预编译前端，且系统未安装 npm"
  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])')"
  [ "$node_major" -ge 18 ] || fail "前端编译需要 Node.js 18 或更高版本"
  (
    cd "$APP_DIR/frontend"
    if [ -f package-lock.json ]; then npm ci; else npm install; fi
    npm run build
  )
}

create_runtime_user() {
  log "创建独立运行用户和数据目录"
  getent group "$SERVICE_GROUP" >/dev/null 2>&1 || groupadd --system "$SERVICE_GROUP"
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --gid "$SERVICE_GROUP" --home-dir "$APP_DIR" \
      --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
  install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "$APP_DIR/data"
}

install_python_dependencies() {
  log "创建 Python 虚拟环境并安装后端依赖"
  if [ ! -x "$APP_DIR/.venv/bin/python" ]; then python3 -m venv "$APP_DIR/.venv"; fi
  "$APP_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/backend/requirements.txt"
  chown -R root:"$SERVICE_GROUP" "$APP_DIR/.venv"
  chmod -R g+rX,o-rwx "$APP_DIR/.venv"
}

create_environment_file() {
  install -d -m 0750 "$CONFIG_DIR"
  if [ -f "$ENV_FILE" ]; then
    log "保留已有管理员凭据和系统密钥：$ENV_FILE"
    return
  fi
  local secret_key
  secret_key="$(generate_secret)"
  umask 077
  {
    printf 'DATABASE_URL=sqlite:///%s/data/sui_manager.db\n' "$APP_DIR"
    printf 'SECRET_KEY=%s\n' "$secret_key"
    printf 'TOKEN_ENCRYPTION_KEY=\n'
    printf 'ADMIN_USERNAME=%s\n' "$ADMIN_USERNAME_VALUE"
    printf 'ADMIN_PASSWORD=%s\n' "$ADMIN_PASSWORD_VALUE"
    printf 'ACCESS_TOKEN_MINUTES=720\n'
    printf 'NODE_TIMEOUT_SECONDS=8\n'
    printf 'HEALTH_MONITOR_ENABLED=true\n'
    printf 'HEALTH_CHECK_INTERVAL_SECONDS=60\n'
  } >"$ENV_FILE"
  chmod 0600 "$ENV_FILE"
  umask 027
}

render_service_file() {
  local temporary
  temporary="$(mktemp)"
  sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@ENV_FILE@|$ENV_FILE|g" \
    "$APP_DIR/deploy/s-ui-manager.service" >"$temporary"
  install -m 0644 "$temporary" "$SERVICE_FILE"
  rm -f "$temporary"
}

render_nginx_file() {
  local temporary
  temporary="$(mktemp)"
  sed -e "s|@HTTP_PORT@|$HTTP_PORT|g" -e "s|@BIND_ADDRESS@|$BIND_ADDRESS|g" \
    -e "s|@FRONTEND_DIST@|$APP_DIR/frontend/dist|g" \
    "$APP_DIR/deploy/nginx-native.conf" >"$temporary"
  install -m 0644 "$temporary" "$NGINX_FILE"
  rm -f "$temporary"
}

install_management_command() {
  local temporary
  temporary="$(mktemp)"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf 'exec bash "%s/suim.sh" "$@"\n' "$APP_DIR"
  } >"$temporary"
  install -m 0755 "$temporary" "$COMMAND_LINK"
  rm -f "$temporary"
}

apply_file_permissions() {
  install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "$APP_DIR/data"
  chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$APP_DIR/data"
  find "$APP_DIR/frontend/dist" -type d -exec chmod 0755 {} +
  find "$APP_DIR/frontend/dist" -type f -exec chmod 0644 {} +
  if [ -d "$APP_DIR/.venv" ]; then
    chown -R root:"$SERVICE_GROUP" "$APP_DIR/.venv"
    chmod -R g+rX,o-rwx "$APP_DIR/.venv"
  fi
  chmod 0600 "$ENV_FILE" "$INSTALL_CONFIG"
}

wait_for_health() {
  local attempts="${1:-15}" index
  for index in $(seq 1 "$attempts"); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}

configure_runtime() {
  write_install_config
  render_service_file
  render_nginx_file
  apply_file_permissions
  install_management_command
  nginx -t
  systemctl daemon-reload
}

start_installed_services() {
  if [ "$ENABLE_AUTOSTART" = "1" ]; then
    systemctl enable --now "$SERVICE_NAME"
  else
    systemctl disable "$SERVICE_NAME" >/dev/null 2>&1 || true
    systemctl start "$SERVICE_NAME"
  fi
  systemctl enable --now nginx
  systemctl reload nginx
  log "等待后端健康检查"
  wait_for_health 15 || fail "服务未通过健康检查，请执行 suim logs 查看日志"
}

detect_access_host() {
  local address=""
  if [ -n "${SUI_PUBLIC_HOST:-}" ]; then printf '%s\n' "$SUI_PUBLIC_HOST"; return; fi
  if command -v ip >/dev/null 2>&1; then
    address="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i == "src") { print $(i+1); exit } }')"
  fi
  if [ -z "$address" ]; then address="$(hostname -I 2>/dev/null | awk '{print $1}')"; fi
  case "$address" in
    10.*|127.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*|'') printf '%s\n' 'VPS公网IP' ;;
    *) printf '%s\n' "$address" ;;
  esac
}

login_address() {
  if [ "$BIND_ADDRESS" = "127.0.0.1" ]; then
    printf 'http://127.0.0.1:%s（仅本机或反向代理）\n' "$HTTP_PORT"
  else
    printf 'http://%s:%s\n' "$(detect_access_host)" "$HTTP_PORT"
  fi
}

current_version() {
  if [ -r "$APP_DIR/VERSION" ]; then tr -d '[:space:]' <"$APP_DIR/VERSION"; else printf 'unknown'; fi
}

service_state() {
  if systemctl is-active --quiet "$SERVICE_NAME"; then printf 'Running'
  elif systemctl is-failed --quiet "$SERVICE_NAME"; then printf 'Failed'
  else printf 'Stopped'; fi
}

nginx_state() { if systemctl is-active --quiet nginx; then printf 'Running'; else printf 'Stopped'; fi; }
health_state() { if curl -fsS --max-time 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then printf 'Passed'; else printf 'Failed'; fi; }
autostart_state() { if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then printf 'Yes'; else printf 'No'; fi; }

show_install_result() {
  local username password
  username="$(get_env_value ADMIN_USERNAME || true)"
  password="$(get_env_value ADMIN_PASSWORD || true)"
  printf '\n%s 安装完成\n' "$PROGRAM_NAME"
  separator
  printf '运行状态：%s\n' "$(service_state)"
  printf '开机启动：%s\n' "$(autostart_state)"
  printf '健康检查：%s\n\n' "$(health_state)"
  printf '登录地址：%s\n' "$(login_address)"
  printf '监听地址：%s\n登录端口：%s\n' "$BIND_ADDRESS" "$HTTP_PORT"
  printf '管理员用户名：%s\n管理员密码：%s\n\n' "$username" "$password"
  printf '安装目录：%s\n配置文件：%s\n管理命令：suim\n' "$APP_DIR" "$ENV_FILE"
  separator
  printf '请立即保存管理员密码。\n'
  if [ "$BIND_ADDRESS" = "0.0.0.0" ]; then
    printf '如公网无法访问，请在 VPS 云防火墙/安全组放行 TCP %s。\n' "$HTTP_PORT"
  fi
}

perform_install() {
  validate_app_dir "$APP_DIR" || fail "安装路径无效或风险过高：$APP_DIR"
  validate_port "$HTTP_PORT" || fail "端口必须是 1-65535 之间的数字"
  validate_bind_address "$BIND_ADDRESS" || fail "监听地址无效"
  validate_username "$ADMIN_USERNAME_VALUE" || fail "管理员用户名格式无效"
  validate_password "$ADMIN_PASSWORD_VALUE" || fail "管理员密码至少 12 位，且包含了不支持的字符"
  install_system_dependencies
  if port_is_used "$HTTP_PORT"; then
    fail "端口 $HTTP_PORT 已被其他程序占用，请使用自定义安装选择其他端口"
  fi
  prepare_source_tree
  if [ -n "$INSTALL_REF" ]; then checkout_version "$INSTALL_REF"; fi
  source_tree_complete "$APP_DIR" || fail "未找到完整源码：$APP_DIR"
  build_frontend_if_needed
  create_runtime_user
  install_python_dependencies
  create_environment_file
  configure_runtime
  start_installed_services
  show_install_result
}

read_custom_password() {
  local first="" second=""
  while true; do
    printf '请输入管理员密码（12-128 位，可用字母、数字及 @%%+=:,._!?-）: '
    read -r -s first || return 1
    printf '\n请再次输入管理员密码: '
    read -r -s second || return 1
    printf '\n'
    if [ "$first" != "$second" ]; then warn "两次密码不一致"; continue; fi
    if ! validate_password "$first"; then warn "密码长度或字符格式不符合要求"; continue; fi
    ADMIN_PASSWORD_VALUE="$first"
    return
  done
}

collect_auto_settings() {
  if [ ! -r "$INSTALL_CONFIG" ]; then
    APP_DIR="$(default_app_dir)"
    HTTP_PORT="8080"
    BIND_ADDRESS="0.0.0.0"
  fi
  APP_DIR="${SUI_MANAGER_DIR:-$APP_DIR}"
  HTTP_PORT="${SUI_HTTP_PORT:-$HTTP_PORT}"
  BIND_ADDRESS="${SUI_BIND_ADDRESS:-$BIND_ADDRESS}"
  ADMIN_USERNAME_VALUE="${SUI_ADMIN_USERNAME:-admin}"
  ADMIN_PASSWORD_VALUE="${SUI_ADMIN_PASSWORD:-$(generate_password)}"
  ENABLE_AUTOSTART="1"
  INSTALL_REF=""
}

collect_custom_settings() {
  local answer="" password_mode="" bind_mode="" autostart_mode="" default_directory default_port default_bind_mode
  if [ -r "$INSTALL_CONFIG" ]; then
    default_directory="$APP_DIR"
    default_port="$HTTP_PORT"
  else
    default_directory="$(default_app_dir)"
    default_port="8080"
  fi
  printf '安装目录 [%s]: ' "$default_directory"
  read -r answer || return 1
  APP_DIR="${answer:-$default_directory}"
  validate_app_dir "$APP_DIR" || fail "安装目录无效"
  while true; do
    printf '登录端口 [%s]: ' "$default_port"
    read -r answer || return 1
    HTTP_PORT="${answer:-$default_port}"
    validate_port "$HTTP_PORT" && break
    warn "端口必须是 1-65535 之间的数字"
  done
  if [ "$BIND_ADDRESS" = "127.0.0.1" ]; then default_bind_mode="2"; else default_bind_mode="1"; fi
  printf '监听方式：1) 公网 0.0.0.0  2) 仅本机 127.0.0.1 [%s]: ' "$default_bind_mode"
  read -r bind_mode || return 1
  case "${bind_mode:-$default_bind_mode}" in 1) BIND_ADDRESS="0.0.0.0" ;; 2) BIND_ADDRESS="127.0.0.1" ;; *) fail "监听方式选择无效" ;; esac
  while true; do
    printf '管理员用户名 [admin]: '
    read -r answer || return 1
    ADMIN_USERNAME_VALUE="${answer:-admin}"
    validate_username "$ADMIN_USERNAME_VALUE" && break
    warn "用户名仅允许字母、数字、点、下划线和短横线"
  done
  printf '密码方式：1) 自动生成强密码  2) 手动设置 [1]: '
  read -r password_mode || return 1
  case "${password_mode:-1}" in 1) ADMIN_PASSWORD_VALUE="$(generate_password)" ;; 2) read_custom_password ;; *) fail "密码方式选择无效" ;; esac
  printf '是否开启开机启动？[Y/n]: '
  read -r autostart_mode || return 1
  case "$autostart_mode" in n|N) ENABLE_AUTOSTART="0" ;; *) ENABLE_AUTOSTART="1" ;; esac
}

install_auto() {
  collect_auto_settings
  printf '\n将使用推荐配置安装：\n目录：%s\n端口：%s\n监听：%s\n管理员：%s\n' \
    "$APP_DIR" "$HTTP_PORT" "$BIND_ADDRESS" "$ADMIN_USERNAME_VALUE"
  confirm "开始全自动安装？" || return
  perform_install
}

install_custom() { collect_custom_settings; INSTALL_REF=""; confirm "确认使用以上自定义配置安装？" || return; perform_install; }

install_specific_version() {
  collect_custom_settings
  printf '请输入分支、标签或提交版本: '
  read -r INSTALL_REF || return 1
  validate_ref "$INSTALL_REF" || fail "版本格式无效"
  confirm "确认安装版本 $INSTALL_REF？" || return
  perform_install
}

show_system_check() {
  local os_name="未知" memory="未知" disk="未知"
  if [ -r /etc/os-release ]; then os_name="$(awk -F= '$1 == "PRETTY_NAME" { gsub(/^"|"$/, "", $2); print $2 }' /etc/os-release)"; fi
  if command -v free >/dev/null 2>&1; then memory="$(free -h | awk '$1 == "Mem:" {print $2}')"; fi
  disk="$(df -h / | awk 'NR == 2 {print $4}')"
  printf '\n系统环境检查\n'; separator
  printf '操作系统：%s\nCPU 架构：%s\n物理内存：%s\n根目录可用空间：%s\n' "$os_name" "$(uname -m)" "$memory" "$disk"
  printf 'Python 3：%s\n' "$(command -v python3 >/dev/null 2>&1 && printf '已安装' || printf '安装时自动处理')"
  printf 'Nginx：%s\n' "$(command -v nginx >/dev/null 2>&1 && printf '已安装' || printf '安装时自动处理')"
  printf 'Git：%s\n' "$(command -v git >/dev/null 2>&1 && printf '已安装' || printf '安装时自动处理')"
  separator
}

create_backup() {
  install -d -m 0700 "$BACKUP_DIR"
  LAST_BACKUP_FILE="$(mktemp --suffix=.tar.gz "$BACKUP_DIR/s-ui-manager-$(date +%F-%H%M%S)-XXXXXX")"
  [ -d "$APP_DIR/data" ] || fail "未找到数据目录：$APP_DIR/data"
  [ -r "$ENV_FILE" ] || fail "未找到环境配置：$ENV_FILE"
  tar -czf "$LAST_BACKUP_FILE" -C "$APP_DIR" data -C "$CONFIG_DIR" s-ui-manager.env
  chmod 0600 "$LAST_BACKUP_FILE"
  log "备份完成：$LAST_BACKUP_FILE"
}

apply_updated_runtime() {
  local backup_file="${1:-}"
  load_install_config
  source_tree_complete "$APP_DIR" || fail "更新后的源码不完整"
  build_frontend_if_needed
  install_python_dependencies
  configure_runtime
  systemctl restart "$SERVICE_NAME"
  systemctl reload nginx
  wait_for_health 15 || fail "更新后健康检查失败。备份位于：$backup_file"
  printf '\n更新完成，当前版本：%s\n' "$(current_version)"
  [ -n "$backup_file" ] && printf '更新前备份：%s\n' "$backup_file"
}

update_latest() {
  is_installed || fail "尚未安装 S-UI Manager"
  ensure_clean_repository
  create_backup
  log "更新到 main 分支最新版本"
  git -C "$APP_DIR" fetch --prune origin main
  ensure_unified_manager_ref origin/main
  if git -C "$APP_DIR" show-ref --verify --quiet refs/heads/main; then git -C "$APP_DIR" checkout main
  else git -C "$APP_DIR" checkout -b main --track origin/main; fi
  git -C "$APP_DIR" pull --ff-only origin main
  exec bash "$APP_DIR/suim.sh" __finish_update "$LAST_BACKUP_FILE"
}

switch_installed_version() {
  local ref=""
  is_installed || fail "尚未安装 S-UI Manager"
  printf '请输入分支、标签或提交版本: '
  read -r ref || return 1
  validate_ref "$ref" || fail "版本格式无效"
  confirm "确认切换到版本 $ref？" || return
  create_backup
  checkout_version "$ref"
  exec bash "$APP_DIR/suim.sh" __finish_update "$LAST_BACKUP_FILE"
}

restart_after_credential_change() { systemctl restart "$SERVICE_NAME"; wait_for_health 15; }

change_username() {
  local username="" env_backup="${ENV_FILE}.bak.$$"
  printf '新管理员用户名: '
  read -r username || return 1
  validate_username "$username" || fail "用户名格式无效"
  cp -a "$ENV_FILE" "$env_backup"
  set_env_value ADMIN_USERNAME "$username"
  if restart_after_credential_change; then rm -f "$env_backup"; printf '管理员用户名已修改为：%s\n' "$username"
  else mv -f "$env_backup" "$ENV_FILE"; systemctl restart "$SERVICE_NAME" || true; fail "服务重启失败，已恢复原用户名"; fi
}

change_password() {
  local env_backup="${ENV_FILE}.bak.$$"
  ADMIN_PASSWORD_VALUE=""
  read_custom_password
  cp -a "$ENV_FILE" "$env_backup"
  set_env_value ADMIN_PASSWORD "$ADMIN_PASSWORD_VALUE"
  if restart_after_credential_change; then rm -f "$env_backup"; printf '管理员密码修改成功，请妥善保存。\n'
  else mv -f "$env_backup" "$ENV_FILE"; systemctl restart "$SERVICE_NAME" || true; fail "服务重启失败，已恢复原密码"; fi
}

reset_credentials() {
  local env_backup="${ENV_FILE}.bak.$$" password
  password="$(generate_password)"
  confirm "用户名将重置为 admin，密码将重新随机生成，确认继续？" || return
  cp -a "$ENV_FILE" "$env_backup"
  set_env_value ADMIN_USERNAME admin
  set_env_value ADMIN_PASSWORD "$password"
  if restart_after_credential_change; then rm -f "$env_backup"; printf '管理员用户名：admin\n管理员密码：%s\n' "$password"
  else mv -f "$env_backup" "$ENV_FILE"; systemctl restart "$SERVICE_NAME" || true; fail "服务重启失败，已恢复原凭据"; fi
}

view_credentials() {
  warn "管理员密码将以明文显示，请确认终端环境安全"
  confirm "显示管理员凭据？" || return
  printf '管理员用户名：%s\n管理员密码：%s\n登录地址：%s\n' \
    "$(get_env_value ADMIN_USERNAME)" "$(get_env_value ADMIN_PASSWORD)" "$(login_address)"
}

port_is_used() {
  local port="$1"
  command -v ss >/dev/null 2>&1 || return 1
  ss -ltnH | awk -v suffix=":$port" '$4 ~ suffix "$" { found = 1 } END { exit !found }'
}

apply_panel_network_change() {
  local old_port="$HTTP_PORT" old_bind="$BIND_ADDRESS"
  local nginx_backup="${NGINX_FILE}.bak.$$" config_backup="${INSTALL_CONFIG}.bak.$$"
  cp -a "$NGINX_FILE" "$nginx_backup"
  cp -a "$INSTALL_CONFIG" "$config_backup"
  render_nginx_file
  if ! nginx -t; then
    mv -f "$nginx_backup" "$NGINX_FILE"; mv -f "$config_backup" "$INSTALL_CONFIG"
    HTTP_PORT="$old_port"; BIND_ADDRESS="$old_bind"
    fail "Nginx 配置检查失败，已恢复原配置"
  fi
  write_install_config
  if ! systemctl reload nginx; then
    mv -f "$nginx_backup" "$NGINX_FILE"; mv -f "$config_backup" "$INSTALL_CONFIG"
    HTTP_PORT="$old_port"; BIND_ADDRESS="$old_bind"; systemctl reload nginx || true
    fail "Nginx 重新加载失败，已恢复原配置"
  fi
  rm -f "$nginx_backup" "$config_backup"
}

change_port() {
  local new_port=""
  printf '当前端口：%s\n新端口: ' "$HTTP_PORT"
  read -r new_port || return 1
  validate_port "$new_port" || fail "端口必须是 1-65535 之间的数字"
  [ "$new_port" != "$HTTP_PORT" ] || { printf '端口没有变化。\n'; return; }
  if port_is_used "$new_port"; then fail "端口 $new_port 已被其他程序占用"; fi
  confirm "确认把登录端口修改为 $new_port？" || return
  HTTP_PORT="$new_port"
  apply_panel_network_change
  printf '登录端口修改成功。新地址：%s\n' "$(login_address)"
  printf '请同步修改 VPS 云防火墙/安全组放行规则。\n'
}

change_bind_address() {
  local choice=""
  printf '当前监听地址：%s\n1. 公网监听 0.0.0.0\n2. 仅本机 127.0.0.1\n请选择 [1-2]: ' "$BIND_ADDRESS"
  read -r choice || return 1
  case "$choice" in 1) BIND_ADDRESS="0.0.0.0" ;; 2) BIND_ADDRESS="127.0.0.1" ;; *) fail "选择无效" ;; esac
  apply_panel_network_change
  printf '监听地址修改成功。登录地址：%s\n' "$(login_address)"
}

view_panel_config() {
  printf '安装方式：非 Docker（Systemd + Nginx）\n当前版本：%s\n安装目录：%s\n登录地址：%s\n' \
    "$(current_version)" "$APP_DIR" "$(login_address)"
  printf '登录端口：%s\n监听地址：%s\n管理员用户名：%s\n' "$HTTP_PORT" "$BIND_ADDRESS" "$(get_env_value ADMIN_USERNAME)"
  printf '环境配置：%s\n数据库：%s/data/sui_manager.db\n' "$ENV_FILE" "$APP_DIR"
}

show_status_detail() {
  systemctl status "$SERVICE_NAME" --no-pager -l || true
  printf '\n后端健康检查：%s\nNginx 状态：%s\n' "$(health_state)" "$(nginx_state)"
  nginx -t || true
}

show_logs() {
  local choice=""
  printf '1. 查看最近 100 行\n2. 实时日志（Ctrl+C 退出）\n请选择 [1-2]: '
  read -r choice || return 1
  case "$choice" in 1) journalctl -u "$SERVICE_NAME" -n 100 --no-pager -l ;; 2) journalctl -u "$SERVICE_NAME" -f -l || true ;; *) warn "选择无效" ;; esac
}

list_backups() {
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 's-ui-manager-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null |
    sort -nr | cut -d' ' -f2-
}

restore_backup() {
  local backups=() selection="" selected="" index=1
  mapfile -t backups < <(list_backups)
  [ "${#backups[@]}" -gt 0 ] || fail "没有找到可恢复的备份"
  printf '可用备份：\n'
  for selected in "${backups[@]}"; do printf '  %s. %s\n' "$index" "$(basename "$selected")"; index=$((index + 1)); done
  printf '请选择备份 [1-%s]: ' "${#backups[@]}"
  read -r selection || return 1
  [[ "$selection" =~ ^[0-9]+$ ]] || fail "选择无效"
  [ "$selection" -ge 1 ] && [ "$selection" -le "${#backups[@]}" ] || fail "选择无效"
  selected="${backups[$((selection - 1))]}"
  confirm "恢复 $(basename "$selected")？当前数据会先自动备份" || return
  create_backup
  systemctl stop "$SERVICE_NAME"
  tar -xzf "$selected" -C "$APP_DIR" data
  tar -xzf "$selected" -C "$CONFIG_DIR" s-ui-manager.env
  apply_file_permissions
  systemctl start "$SERVICE_NAME"
  wait_for_health 15 || fail "恢复后健康检查失败，恢复前备份为：$LAST_BACKUP_FILE"
  printf '备份恢复成功。\n'
}

repair_installation() {
  confirm "将重新安装依赖、修复权限并重建服务配置，继续？" || return
  install_system_dependencies
  source_tree_complete "$APP_DIR" || fail "源码不完整"
  build_frontend_if_needed
  create_runtime_user
  install_python_dependencies
  configure_runtime
  systemctl enable --now nginx
  systemctl restart "$SERVICE_NAME"
  systemctl reload nginx
  wait_for_health 15 || fail "修复后健康检查失败，请执行 suim logs"
  printf '安装修复完成。\n'
}

uninstall_manager() {
  local choice="" confirmation=""
  printf '1. 移除服务，保留源码、数据和配置\n2. 完整卸载并删除源码、数据和配置\n0. 取消\n请选择 [0-2]: '
  read -r choice || return 1
  case "$choice" in
    0) return ;;
    1)
      confirm "确认移除 S-UI Manager 服务？" || return
      create_backup
      systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
      rm -f "$SERVICE_FILE" "$NGINX_FILE" "$COMMAND_LINK"
      systemctl daemon-reload; systemctl reload nginx || true
      printf '服务已移除，源码、数据和配置仍保留。\n重新安装：bash %s/suim.sh\n' "$APP_DIR"
      exit 0 ;;
    2)
      printf '此操作会永久删除 %s 和 %s。\n请输入 DELETE 确认完整卸载: ' "$APP_DIR" "$CONFIG_DIR"
      read -r confirmation || return 1
      [ "$confirmation" = "DELETE" ] || { printf '已取消。\n'; return; }
      validate_app_dir "$APP_DIR" || fail "拒绝删除不安全的安装路径"
      create_backup
      systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
      rm -f "$SERVICE_FILE" "$NGINX_FILE" "$COMMAND_LINK"
      systemctl daemon-reload; systemctl reload nginx || true
      userdel "$SERVICE_USER" >/dev/null 2>&1 || true; groupdel "$SERVICE_GROUP" >/dev/null 2>&1 || true
      rm -rf --one-file-system "$APP_DIR"; rm -rf --one-file-system "$CONFIG_DIR"
      printf 'S-UI Manager 已完整卸载。备份保留在：%s\n' "$LAST_BACKUP_FILE"
      exit 0 ;;
    *) warn "选择无效" ;;
  esac
}

show_installed_header() {
  local username
  username="$(get_env_value ADMIN_USERNAME || printf 'unknown')"
  printf '%s 管理脚本 v%s\n' "$PROGRAM_NAME" "$(current_version)"; separator
  printf '面板状态：%s\n后端健康：%s\nNginx 状态：%s\n开机启动：%s\n' \
    "$(service_state)" "$(health_state)" "$(nginx_state)" "$(autostart_state)"
  printf '当前版本：%s\n登录地址：%s\n' "$(current_version)" "$(login_address)"
  printf '登录端口：%s\n管理员：%s\n' "$HTTP_PORT" "$username"; separator
}

installed_menu() {
  local selection=""
  while true; do
    load_install_config; clear_screen; show_installed_header
    printf '  0. 退出\n'; separator
    printf '  1. 更新到最新版本\n  2. 切换指定版本\n  3. 卸载 S-UI Manager\n'; separator
    printf '  4. 查看管理员凭据\n  5. 修改管理员用户名\n  6. 修改管理员密码\n  7. 重置管理员凭据\n'; separator
    printf '  8. 修改登录端口\n  9. 修改监听地址\n  10. 查看面板配置\n'; separator
    printf '  11. 启动面板\n  12. 停止面板\n  13. 重启面板\n  14. 检查运行状态\n'
    printf '  15. 查看运行日志\n  16. 开启开机启动\n  17. 关闭开机启动\n'; separator
    printf '  18. 备份数据与配置\n  19. 恢复备份\n  20. 修复安装\n'; separator
    printf '\n请输入选择 [0-20]: '
    read -r selection || exit 0
    printf '\n'
    case "$selection" in
      0) exit 0 ;; 1) update_latest ;; 2) switch_installed_version ;; 3) uninstall_manager ;;
      4) view_credentials ;; 5) change_username ;; 6) change_password ;; 7) reset_credentials ;;
      8) change_port ;; 9) change_bind_address ;; 10) view_panel_config ;;
      11) systemctl start "$SERVICE_NAME"; wait_for_health 15 || warn "健康检查失败" ;;
      12) systemctl stop "$SERVICE_NAME" ;;
      13) systemctl restart "$SERVICE_NAME"; wait_for_health 15 || warn "健康检查失败" ;;
      14) show_status_detail ;; 15) show_logs ;;
      16) systemctl enable "$SERVICE_NAME"; printf '已开启开机启动。\n' ;;
      17) systemctl disable "$SERVICE_NAME"; printf '已关闭开机启动。\n' ;;
      18) create_backup ;; 19) restore_backup ;; 20) repair_installation ;; *) warn "选择无效" ;;
    esac
    pause_screen
  done
}

uninstalled_menu() {
  local selection=""
  while true; do
    clear_screen
    printf '%s 安装脚本\n' "$PROGRAM_NAME"; separator
    printf '  0. 退出\n'; separator
    printf '  1. 全自动安装（推荐）\n  2. 自定义安装\n  3. 安装指定版本\n  4. 检查系统环境\n'; separator
    printf '\n当前状态：尚未安装\n\n请输入选择 [0-4]: '
    read -r selection || exit 0
    printf '\n'
    case "$selection" in 0) exit 0 ;; 1) install_auto ;; 2) install_custom ;; 3) install_specific_version ;; 4) show_system_check ;; *) warn "选择无效" ;; esac
    if is_installed; then pause_screen; installed_menu; fi
    pause_screen
  done
}

show_help() {
  printf '%s 统一安装与管理脚本\n\n' "$PROGRAM_NAME"
  printf '用法：\n  suim                 打开交互菜单\n  suim install         使用推荐配置安装\n'
  printf '  suim update          更新到最新版本\n  suim status          查看运行状态\n'
  printf '  suim logs            查看最近 100 行日志\n  suim start|stop|restart\n  suim backup          备份数据和配置\n'
}

dispatch_command() {
  local command="${1:-menu}"
  case "$command" in
    menu|'') if is_installed; then installed_menu; else uninstalled_menu; fi ;;
    install)
      if is_installed; then fail "S-UI Manager 已安装"; fi
      collect_auto_settings
      perform_install
      ;;
    update) update_latest ;; status) show_status_detail ;;
    logs) journalctl -u "$SERVICE_NAME" -n 100 --no-pager -l ;;
    start) systemctl start "$SERVICE_NAME" ;; stop) systemctl stop "$SERVICE_NAME" ;; restart) systemctl restart "$SERVICE_NAME" ;;
    backup) create_backup ;; --help|-h|help) show_help ;; __finish_update) apply_updated_runtime "${2:-}" ;;
    *) fail "未知命令：$command。执行 suim --help 查看帮助" ;;
  esac
}

main() {
  require_root
  load_install_config
  if is_installed && source_tree_complete "$APP_DIR"; then install_management_command; fi
  dispatch_command "$@"
}

main "$@"
