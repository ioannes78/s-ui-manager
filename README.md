# S-UI Manager V1.0

一个轻量的多节点 S-UI 中央控制台。目标是保留每台 VPS 上现有的 S-UI，仅通过官方 `/apiv2` Token API 做集中管理。

## V1.0 功能

- 管理多台 S-UI VPS
- API Token 加密存储
- 节点连通性测试
- 统一 Dashboard
- 读取 `/status`、`/clients`、`/inbounds`、`/onlines`
- 批量重启 sing-box Core
- 高级批量 `/apiv2/save` 写入
- 操作审计日志
- 单管理员 JWT 登录
- Docker Compose 一键部署
- 非 Docker 一键安装（Systemd + Nginx）

> V1.0 的“批量写入”故意采用兼容模式：透传 S-UI 原生 `object/action/data`，不假定某一个特定 S-UI 版本的 Client 数据结构，降低错误覆盖风险。

## 1. S-UI 节点准备

在每台 S-UI：

1. Admin -> API Token
2. 新建 Token
3. 记录 Token
4. 确保中央服务器能访问 S-UI 面板/API 地址

节点地址填写示例：

- `https://hk.example.com/app`
- `https://jp.example.com/app`

系统会自动补 `/apiv2/`。

## 2. Docker Compose 部署

以下教程适用于 Debian 12、Ubuntu 22.04/24.04，默认使用 `root` 用户执行。项目使用 Docker Compose 部署，默认从 VPS 的 `8080` 端口提供服务。

### 2.1 安装基础工具与 Docker

```bash
apt update
apt install -y ca-certificates curl git openssl

install -m 0755 -d /etc/apt/keyrings

. /etc/os-release
DOCKER_DISTRO="$ID"
DOCKER_CODENAME="$VERSION_CODENAME"
DOCKER_ARCH="$(dpkg --print-architecture)"

curl -fsSL "https://download.docker.com/linux/${DOCKER_DISTRO}/gpg" \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/${DOCKER_DISTRO}
Suites: ${DOCKER_CODENAME}
Components: stable
Architectures: ${DOCKER_ARCH}
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt update
apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker
docker version
docker compose version
```

如果系统不是 Debian 或 Ubuntu，请按照 [Docker Engine 官方安装文档](https://docs.docker.com/engine/install/) 安装 Docker Engine 与 Compose Plugin。

### 2.2 下载 S-UI Manager

```bash
git clone https://github.com/ioannes78/s-ui-manager.git /opt/s-ui-manager
cd /opt/s-ui-manager
cat VERSION
```

当前版本应显示：

```text
1.0.0
```

### 2.3 设置管理员密码

复制环境变量模板：

```bash
cd /opt/s-ui-manager
cp .env.example .env
```

分别生成管理员密码和系统密钥：

```bash
openssl rand -base64 24
openssl rand -hex 32
```

编辑配置：

```bash
nano .env
```

按实际生成的内容填写：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=第一条命令生成的随机密码
SECRET_KEY=第二条命令生成的64位字符串
TOKEN_ENCRYPTION_KEY=
HTTP_PORT=8080
NODE_TIMEOUT_SECONDS=8
```

请保存管理员密码。当前 V1.0 没有在线找回密码功能，也不要把 `.env` 提交到 Git 仓库。

### 2.4 启动服务

```bash
cd /opt/s-ui-manager
chmod +x install.sh
./install.sh
```

也可以直接使用 Docker Compose：

```bash
docker compose up -d --build
```

### 2.5 检查运行状态

```bash
docker compose ps
docker compose logs --tail=100
curl -I http://127.0.0.1:8080
```

当 `backend` 和 `frontend` 均显示为运行状态后，访问：

```text
http://VPS公网IP:8080
```

使用 `.env` 中的 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 登录。

测试阶段需要在 VPS 服务商的云防火墙/安全组中放行 TCP `8080`，建议只允许管理员的固定公网 IP。Docker 发布的容器端口可能绕过 UFW 规则，生产环境不要依赖 UFW 单独保护该端口。

### 2.6 更新版本

更新前先备份数据库与环境配置：

```bash
cd /opt/s-ui-manager
tar -czf "/root/s-ui-manager-backup-$(date +%F-%H%M).tar.gz" data .env

git pull
docker compose up -d --build
docker compose ps
```

数据库默认位于：

```text
/opt/s-ui-manager/data/sui_manager.db
```

### 2.7 常用维护命令

```bash
cd /opt/s-ui-manager

# 查看状态
docker compose ps

# 查看最近日志
docker compose logs --tail=200

# 实时查看日志
docker compose logs -f

# 重启
docker compose restart

# 停止并保留数据
docker compose down

# 重新构建并启动
docker compose up -d --build
```

## 3. 非 Docker 一键安装

非 Docker 模式使用以下结构：

- Nginx：托管已经编译好的前端，并把 `/api/` 转发到后端
- Systemd：运行并守护 FastAPI/Uvicorn 后端
- Python venv：隔离后端依赖
- SQLite：数据保存在 `/opt/s-ui-manager/data/sui_manager.db`

仓库已包含预编译前端，因此 VPS 运行时不需要 Node.js，也不会安装 Docker。

### 3.1 一键安装

适用于 Debian 12、Ubuntu 22.04/24.04。使用 `root` 用户执行：

```bash
apt update
apt install -y git

git clone https://github.com/ioannes78/s-ui-manager.git /opt/s-ui-manager
cd /opt/s-ui-manager
chmod +x install-native.sh update-native.sh
bash install-native.sh
```

安装脚本会自动完成：

1. 安装 Python、Nginx、OpenSSL 等系统依赖
2. 创建低权限系统用户 `sui-manager`
3. 创建 Python 虚拟环境并安装后端依赖
4. 自动生成管理员密码和 `SECRET_KEY`
5. 安装并启动 `s-ui-manager.service`
6. 安装 Nginx 配置并监听 `8080`
7. 执行后端健康检查

安装成功后，终端会显示随机生成的管理员密码，请立即保存。访问：

```text
http://VPS公网IP:8080
```

### 3.2 自定义安装参数

默认管理员用户名为 `admin`，默认端口为 `8080`。可以在首次安装时覆盖：

```bash
SUI_ADMIN_USERNAME=myadmin \
SUI_ADMIN_PASSWORD='你设置的强密码' \
SUI_HTTP_PORT=18080 \
bash install-native.sh
```

默认监听所有 IPv4 地址。若前面另有 HTTPS 反向代理，可只监听本机：

```bash
SUI_BIND_ADDRESS=127.0.0.1 bash install-native.sh
```

`SUI_BIND_ADDRESS` 仅接受 `0.0.0.0` 或 `127.0.0.1`，该设置会保存到安装参数中，并在一键更新后继续生效。

也可以指定其他安装路径，但不要放在 `/root` 下：

```bash
SUI_MANAGER_DIR=/srv/s-ui-manager bash install-native.sh
```

### 3.3 配置与数据位置

| 内容 | 路径 |
|---|---|
| 程序目录 | `/opt/s-ui-manager` |
| 管理员密码及系统密钥 | `/etc/s-ui-manager/s-ui-manager.env` |
| 安装参数 | `/etc/s-ui-manager/install.conf` |
| SQLite 数据库 | `/opt/s-ui-manager/data/sui_manager.db` |
| Systemd 服务 | `/etc/systemd/system/s-ui-manager.service` |
| Nginx 配置 | `/etc/nginx/conf.d/s-ui-manager.conf` |
| 自动更新备份 | `/var/backups/s-ui-manager/` |

配置文件权限为 `0600`。如需修改管理员密码：

```bash
nano /etc/s-ui-manager/s-ui-manager.env
systemctl restart s-ui-manager
```

### 3.4 状态与日志

```bash
# 服务状态
systemctl status s-ui-manager --no-pager

# 实时日志
journalctl -u s-ui-manager -f

# 最近 100 行日志
journalctl -u s-ui-manager -n 100 --no-pager

# 后端健康检查
curl http://127.0.0.1:8000/api/health

# 检查 Nginx
nginx -t
systemctl status nginx --no-pager
```

### 3.5 一键更新

```bash
cd /opt/s-ui-manager
bash update-native.sh
```

更新脚本会先把数据库和环境配置备份到 `/var/backups/s-ui-manager/`，然后执行 `git pull --ff-only`、更新 Python 依赖、刷新 Systemd/Nginx 配置、重启服务并进行健康检查。

### 3.6 Docker 与非 Docker 模式对比

| 对比项 | Docker Compose | 非 Docker |
|---|---|---|
| 隔离性 | 更强 | 使用 Python venv 隔离 |
| 运行内存 | 略高 | 略低 |
| 安装方式 | `docker compose up` | `bash install-native.sh` |
| 进程管理 | Docker | Systemd |
| 前端服务 | Nginx 容器 | 系统 Nginx |
| 更新方式 | `git pull` 后重建容器 | `bash update-native.sh` |
| 推荐场景 | 希望环境一致、迁移方便 | 小内存 VPS、习惯系统服务管理 |

两种模式使用相同源码和 SQLite 数据结构，但不要让它们同时操作同一个数据库文件。

## 4. 生产环境 HTTPS 部署

正式使用时，不建议把 `8080` 端口直接暴露到公网。

Docker 模式编辑 `.env`：

```env
HTTP_PORT=127.0.0.1:8080
```

重新创建容器：

```bash
cd /opt/s-ui-manager
docker compose up -d --build
```

非 Docker 模式重新执行安装脚本，把监听地址限制为本机；已有管理员密码和系统密钥会原样保留：

```bash
cd /opt/s-ui-manager
SUI_BIND_ADDRESS=127.0.0.1 bash install-native.sh
```

### 4.1 Nginx 反向代理示例

先把管理域名，例如 `manager.example.com`，解析到 Manager VPS 的公网 IP，然后安装 Nginx 与 Certbot：

```bash
apt update
apt install -y nginx certbot python3-certbot-nginx
```

新建配置：

```bash
nano /etc/nginx/sites-available/s-ui-manager
```

写入以下内容，并替换域名：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name manager.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置并申请 HTTPS 证书：

```bash
ln -s /etc/nginx/sites-available/s-ui-manager \
  /etc/nginx/sites-enabled/s-ui-manager

nginx -t
systemctl reload nginx
certbot --nginx -d manager.example.com
```

完成后访问：

```text
https://manager.example.com
```

确认 HTTPS 正常后，在 VPS 服务商的云防火墙/安全组中关闭公网 TCP `8080`，只保留 `22`、`80` 和 `443`；SSH 的 `22` 端口也应尽量限制来源 IP。

### 4.2 推荐网络架构

建议 Manager 只通过 WireGuard、Tailscale 或其他可信管理网络访问每台 S-UI，再由 Nginx/Caddy/Cloudflare Tunnel 为 Manager 提供 HTTPS。

更安全的节点管理方式：

```text
Manager
  |
  +-- WireGuard 管理网 --> HK S-UI
  +-- WireGuard 管理网 --> JP S-UI
  +-- WireGuard 管理网 --> US S-UI
```

这样每台 S-UI 的管理端口不需要直接暴露公网。

## 5. 关于 TLS

生产环境应保持 `verify_tls=true`。

只有在使用自签名证书、且你确认链路安全时才临时关闭。更推荐给 S-UI 使用有效证书，而不是长期关闭验证。

## 6. 高级批量写入

界面里的“高级批量写入”会调用：

```text
POST /apiv2/save
```

请求模型：

```json
{
  "object": "clients",
  "action": "edit",
  "data": {},
  "initUsers": null
}
```

不同 S-UI 版本的 `data` 字段结构可能变化。正确做法：

1. 先 GET `/apiv2/clients` 或 `/apiv2/inbounds`
2. 观察当前节点返回结构
3. 在单台测试节点执行
4. 确认无误后再批量执行
5. 重要操作前备份 S-UI 数据库

## 7. 当前 V1.0 边界

暂未加入：

- 中央用户 Source of Truth
- 自动字段级客户端编辑器
- 配置漂移检测
- 统一订阅服务
- 多管理员/RBAC
- PostgreSQL
- 自动流量限额/到期停用

这些适合 V1.1 / V2.0。

## 8. API

FastAPI OpenAPI 默认地址：

```text
http://服务器IP:8080/api/...
```

由于 Nginx 目前只代理 `/api/`，如需开放 Swagger，可给 Nginx 增加 `/docs` 与 `/openapi.json` 代理规则；生产环境通常建议不公开 Swagger。

## 9. 安全注意事项

- 不要把 `.env` 提交 Git
- 不要在日志中记录 API Token
- Manager 应启用 HTTPS
- S-UI API 最好走 WireGuard/Tailscale 等管理网络
- Token 设置有效期并定期轮换
- 批量 save 前先备份
