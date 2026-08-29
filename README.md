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

## 2. 部署

```bash
cp .env.example .env
nano .env
```

至少修改：

```env
ADMIN_PASSWORD=一个强密码
SECRET_KEY=至少32位随机字符串
```

生成 SECRET_KEY：

```bash
openssl rand -hex 32
```

启动：

```bash
docker compose up -d --build
```

访问：

```text
http://服务器IP:8080
```

## 3. 推荐生产架构

建议在本机只监听内网/反代入口，再由 Caddy/Nginx/Cloudflare Tunnel 提供 HTTPS。

更安全的节点管理方式：

```text
Manager
  |
  +-- WireGuard 管理网 --> HK S-UI
  +-- WireGuard 管理网 --> JP S-UI
  +-- WireGuard 管理网 --> US S-UI
```

这样每台 S-UI 的管理端口不需要直接暴露公网。

## 4. 关于 TLS

生产环境应保持 `verify_tls=true`。

只有在使用自签名证书、且你确认链路安全时才临时关闭。更推荐给 S-UI 使用有效证书，而不是长期关闭验证。

## 5. 高级批量写入

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

## 6. 当前 V1.0 边界

暂未加入：

- 中央用户 Source of Truth
- 自动字段级客户端编辑器
- 配置漂移检测
- 统一订阅服务
- 多管理员/RBAC
- PostgreSQL
- 自动流量限额/到期停用

这些适合 V1.1 / V2.0。

## 7. API

FastAPI OpenAPI 默认地址：

```text
http://服务器IP:8080/api/...
```

由于 Nginx 目前只代理 `/api/`，如需开放 Swagger，可给 Nginx 增加 `/docs` 与 `/openapi.json` 代理规则；生产环境通常建议不公开 Swagger。

## 8. 安全注意事项

- 不要把 `.env` 提交 Git
- 不要在日志中记录 API Token
- Manager 应启用 HTTPS
- S-UI API 最好走 WireGuard/Tailscale 等管理网络
- Token 设置有效期并定期轮换
- 批量 save 前先备份
