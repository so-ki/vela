# Vela 生产部署指南

## 架构

```
浏览器 → Nginx (frontend:80) → /api/* 反代 → FastAPI (gunicorn)
                              → /*       静态 SPA
PostgreSQL ← SQLAlchemy
Chroma / 法源语料 ← 持久卷 backend_data
```

## 快速部署（Docker Compose）

```bash
cd vela-platform
cp .env.production.example .env.prod
# 编辑 .env.prod：SECRET_KEY、POSTGRES_PASSWORD、PUBLIC_URL、SSO 等

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

访问：`http://localhost:8080`（或 `PUBLIC_URL` 配置的域名）

## 关键环境变量

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥，生产必改 |
| `PUBLIC_URL` | 对外 URL，用于 CORS / SSO 回调 / 前端跳转 |
| `ALLOW_OPEN_REGISTRATION` | 生产建议 `false` |
| `SSO_ENABLED` + OIDC 四元组 | 企业单点登录 |
| `EXPORT_TEMPLATE` | `law_school`（法学院意见书）或 `legacy` |
| `EXPORT_ORG_*` | Word 意见书抬头、致/自 等 |

## SSO 配置（OpenID Connect）

1. 在 IdP（Keycloak / Azure AD / Okta）创建 OAuth 客户端  
2. 回调地址：`{PUBLIC_URL}/api/v1/auth/sso/callback`  
3. 在 `.env.prod` 设置：

```env
SSO_ENABLED=true
SSO_ISSUER_URL=https://your-idp/realms/vela
SSO_CLIENT_ID=vela-platform
SSO_CLIENT_SECRET=...
SSO_REDIRECT_URI=https://vela.example.com/api/v1/auth/sso/callback
ALLOW_PASSWORD_LOGIN=false   # 可选：仅 SSO 登录
```

4. 用户首次 SSO 登录会 JIT 建号（`SSO_JIT_PROVISION=true`），默认角色 `SSO_DEFAULT_ROLE`

**前端流程：** 登录页「企业 SSO 登录」→ IdP → `/login/sso/callback` 写入 JWT

### 本地 Keycloak 联调（可选）

用于在无企业 IdP 时验证 SSO 完整链路：

```bash
# 1. 启动 Keycloak（开发模式，admin/admin）
docker run -d --name vela-keycloak -p 8081:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.0 start-dev

# 2. 打开 http://localhost:8081 → 创建 Realm「vela」、Client「vela-platform」
#    - Client type: OpenID Connect
#    - Valid redirect URIs: http://127.0.0.1:8080/api/v1/auth/sso/callback
#    - Web origins: http://127.0.0.1:8080
#    - 复制 Client secret

# 3. 在 .env.prod 或 backend/.env 设置：
# SSO_ENABLED=true
# SSO_ISSUER_URL=http://127.0.0.1:8081/realms/vela
# SSO_CLIENT_ID=vela-platform
# SSO_CLIENT_SECRET=<上一步 secret>
# SSO_REDIRECT_URI=http://127.0.0.1:8080/api/v1/auth/sso/callback
# FRONTEND_URL=http://127.0.0.1:8080
# PUBLIC_URL=http://127.0.0.1:8080

# 4. 重启服务后执行
chmod +x scripts/verify_sso_config.sh
./scripts/verify_sso_config.sh
```

浏览器访问登录页 → **企业 SSO 登录** → Keycloak 账号 → 应回到平台工作台。

校验脚本（SSO 关闭时也会检查 `/auth/sso/config`）：

```bash
./scripts/verify_sso_config.sh
```

生产 Compose 冒烟（需 Docker）：

```bash
chmod +x scripts/prod_smoke.sh
./scripts/prod_smoke.sh
```

## Word 导出 · 法学院模板

默认 `EXPORT_TEMPLATE=law_school`，定稿后导出文件名：

`{项目名称}_法律研究意见书.docx`

结构：

- 抬头（可配置机构名）
- 文号 `VELA-YYYY-#####`
- 致/自/关于 信息表
- 一、项目事实概要
- 二、分维度法律核查意见（含法源与风险说明）
- 三、综合结论
- 四、法务复核意见
- 附录 · 免责声明
- 经办 / 复核签章栏

切换旧版：`EXPORT_TEMPLATE=legacy`

## 运维检查

```bash
curl -s http://localhost:8080/api/v1/health | jq
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/status | jq
```

数据备份：

- PostgreSQL 卷 `pgdata`
- 后端卷 `backend_data`（SQLite 不用；含 Chroma 与法源 JSON 若挂载）

## 本地开发 vs 生产

| 项 | 开发 `./scripts/start.sh` | 生产 compose |
|----|---------------------------|--------------|
| 数据库 | SQLite | PostgreSQL |
| 前端 | Vite dev | Nginx 静态 |
| 注册 | 开放 | 可关闭 |
| 导出模板 | law_school | law_school |
