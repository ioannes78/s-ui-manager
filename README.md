# S-UI Manager V2.0（本地开发版）

一个轻量的多节点 S-UI 中央控制台。目标是保留每台 VPS 上现有的 S-UI，仅通过官方 `/apiv2` Token API 做集中管理。

> 当前 V2.0 源码仅保存在本地开发目录，尚未提交或发布到 GitHub。GitHub `main` 分支仍为 V1.1.0。

## V2.0 已实现功能

- 全新响应式多页面控制台
- Dashboard 节点、用户、任务和告警汇总
- 节点添加、编辑、删除、分组、地区、标签和备注
- API Token 加密存储、TLS 校验与节点延迟测试
- 定时健康监控、节点离线告警和恢复自动关闭
- 节点详情统一读取 `/status`、`/clients`、`/inbounds`、`/onlines`
- 中央用户数据库、流量限额、到期时间、IP限制和启停状态
- 中央用户同步预演及多节点执行
- 批量重启 sing-box Core 和高级 `/apiv2/save` 写入
- 所有批量操作生成任务及单节点执行结果
- 配置快照、快照详情、差异 API 和受控恢复 API
- 告警确认、解决、重开及完整操作审计
- 单管理员 JWT 登录，敏感凭据加密且默认脱敏
- Docker Compose 一键部署
- 非 Docker 一键安装（Systemd + Nginx）
- 统一的 `suim` 安装、更新与运维菜单

> V2.0 的用户同步和高级批量写入继续采用兼容模式。首次用户同步必须先生成预演，不同 S-UI 版本的 Client 字段仍需在测试节点验证。

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
2.0.0
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

请保存管理员密码。当前 V2.0 没有在线找回密码功能，也不要把 `.env` 提交到 Git 仓库。

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

## 3. 非 Docker 一键安装与管理

非 Docker 模式由 Nginx 托管预编译前端，Systemd 守护 FastAPI/Uvicorn 后端，Python venv 隔离依赖，SQLite 数据保存在安装目录的 `data/` 中。VPS 运行时不需要 Node.js，也不会安装 Docker。

`suim.sh` 是原生部署的唯一入口，负责安装、更新、凭据、端口、服务、备份和卸载。安装完成后可在任意目录执行 `suim` 打开管理菜单。

### 3.1 首次安装

适用于 Debian 12、Ubuntu 22.04/24.04。使用 `root` 用户执行：

```bash
apt update
apt install -y git
git clone https://github.com/ioannes78/s-ui-manager.git /opt/s-ui-manager
cd /opt/s-ui-manager
chmod +x suim.sh
bash suim.sh
```

首次运行显示：

```text
S-UI Manager 安装脚本
————————————————————————————————
  0. 退出
————————————————————————————————
  1. 全自动安装（推荐）
  2. 自定义安装
  3. 安装指定版本
  4. 检查系统环境
————————————————————————————————

当前状态：尚未安装
```

全自动安装采用以下安全默认值：

- 当前项目目录作为安装目录，推荐 `/opt/s-ui-manager`
- 登录端口 `8080`
- 监听地址 `0.0.0.0`
- 管理员用户名 `admin`
- 自动生成 36 位随机管理员密码和独立系统密钥
- 自动启动并开启开机启动

自定义安装可交互设置安装目录、端口、监听地址、用户名、密码和开机启动。手动密码必须为 12-128 位，脚本会隐藏输入并要求输入两次。

安装完成后会显示运行状态、健康检查、登录地址、端口、管理员用户名和密码。请立即保存密码，并在 VPS 云防火墙或安全组中放行所选 TCP 端口。

### 3.2 `suim` 管理菜单

安装完成后执行：

```bash
suim
```

主界面会先显示面板、后端、Nginx、开机启动、版本、地址、端口和管理员状态，然后提供以下操作：

```text
  0. 退出
————————————————————————————————
  1. 更新到最新版本
  2. 切换指定版本
  3. 卸载 S-UI Manager
————————————————————————————————
  4. 查看管理员凭据
  5. 修改管理员用户名
  6. 修改管理员密码
  7. 重置管理员凭据
————————————————————————————————
  8. 修改登录端口
  9. 修改监听地址
  10. 查看面板配置
————————————————————————————————
  11. 启动面板
  12. 停止面板
  13. 重启面板
  14. 检查运行状态
  15. 查看运行日志
  16. 开启开机启动
  17. 关闭开机启动
————————————————————————————————
  18. 备份数据与配置
  19. 恢复备份
  20. 修复安装
```

常用操作也支持直接命令：

```bash
suim update
suim status
suim logs
suim start
suim stop
suim restart
suim backup
```

### 3.3 更新与版本切换

选择菜单 `1` 或执行：

```bash
suim update
```

更新过程会自动：

1. 备份数据库和环境配置到 `/var/backups/s-ui-manager/`
2. 检查源码目录是否存在未提交修改
3. 执行 `git pull --ff-only`
4. 更新 Python 依赖并修复虚拟环境权限
5. 刷新 Systemd 和 Nginx 配置
6. 重启服务并执行后端健康检查

菜单 `2` 可以切换到指定分支、Git 标签或提交版本，切换前同样会自动备份。为了保留统一管理命令，只允许切换到包含新版 `suim` 管理菜单的 V1.1.0 或更高版本。

### 3.4 从早期原生安装迁移

早期版本使用独立的 `update-native.sh`。升级到 V1.1 后只需执行一次：

```bash
cd /opt/s-ui-manager
git pull --ff-only
bash suim.sh
```

新版脚本会识别并保留现有数据库、管理员密码、系统密钥、端口和监听设置，同时注册 `/usr/local/bin/suim` 命令入口。以后统一使用 `suim` 管理，不再需要 `update-native.sh`。

如果旧安装曾出现 `.venv/bin/uvicorn: Permission denied` 或 `status=203/EXEC`，在管理菜单选择 `20. 修复安装`。

### 3.5 配置与数据位置

| 内容 | 路径 |
|---|---|
| 程序目录 | `/opt/s-ui-manager` |
| 管理命令 | `/usr/local/bin/suim` |
| 管理员密码及系统密钥 | `/etc/s-ui-manager/s-ui-manager.env` |
| 安装参数 | `/etc/s-ui-manager/install.conf` |
| SQLite 数据库 | `/opt/s-ui-manager/data/sui_manager.db` |
| Systemd 服务 | `/etc/systemd/system/s-ui-manager.service` |
| Nginx 配置 | `/etc/nginx/conf.d/s-ui-manager.conf` |
| 更新与手动备份 | `/var/backups/s-ui-manager/` |

配置文件权限为 `0600`。主菜单不会直接显示管理员密码，只有选择“查看管理员凭据”并再次确认后才会显示。

### 3.6 卸载和数据保护

卸载提供两种方式：

- 仅移除服务，保留源码、数据库和配置，方便重新安装
- 完整卸载源码、数据库和配置

两种方式都会先自动备份。完整卸载必须输入 `DELETE` 二次确认，备份文件仍保留在 `/var/backups/s-ui-manager/`。

### 3.7 Docker 与非 Docker 模式对比

| 对比项 | Docker Compose | 非 Docker |
|---|---|---|
| 隔离性 | 更强 | 使用 Python venv 隔离 |
| 运行内存 | 略高 | 略低 |
| 安装方式 | `docker compose up` | `bash suim.sh` 菜单 |
| 进程管理 | Docker | Systemd |
| 前端服务 | Nginx 容器 | 系统 Nginx |
| 更新方式 | `git pull` 后重建容器 | `suim update` |
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

非 Docker 模式在管理菜单中选择 `9. 修改监听地址`，然后选择 `127.0.0.1`：

```bash
suim
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

## 7. 当前 V2.0 开发版边界

暂未加入：

- 自动识别所有 S-UI 版本的客户端字段
- 图形化入站字段编辑器
- 自动配置漂移检测和定时快照
- 统一订阅生成服务
- 多管理员/RBAC和TOTP
- PostgreSQL专项部署验证
- 远程流量回采及到期自动停用

这些功能计划在 V2.0 后续迭代或 V2.1 中完成。

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
