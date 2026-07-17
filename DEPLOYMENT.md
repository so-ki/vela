# Vela 生产部署指南

## 架构

```
浏览器 → Nginx (frontend:8080，非 root/只读) → /api/* 反代 → FastAPI (Uvicorn，单 worker)
                              → /*       静态 SPA
PostgreSQL ← SQLAlchemy
关键词检索 / 法源语料 ← 版本化能力包制品
```

## 快速部署（Docker Compose）

```bash
cd vela-platform
# 从密钥管理系统或安全终端创建权限为 600 的 .env.prod。
# 至少填写 SECRET_KEY、POSTGRES_PASSWORD、INSTANCE_ORGANIZATION、PUBLIC_URL；不要提交或打包该文件。

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

本 RC 支持两类数据库：全新空库，或已经由本仓库 Alembic 管理且含 `alembic_version` 的库。历史版本若曾用 `create_all` 直接建表、已有业务表但没有 `alembic_version`，不得直接 `stamp head` 或覆盖启动；先停机备份，在隔离副本中制定并演练数据迁移/核对方案，通过后再切换。迁移服务会对不兼容旧库失败关闭，不提供未经验证的自动猜测升级。

`SECRET_KEY` 和 `POSTGRES_PASSWORD` 都没有生产默认值。生产入口会拒绝少于 32 字符的 `SECRET_KEY`、少于 16 字符或常见默认值的 `POSTGRES_PASSWORD`；数据库密码会先进行 URL 编码，因此可安全使用 `@`、`%`、`:`、`/` 等特殊字符。正式 Compose 与生产入口不提供演示账号开关，不能因环境变量误配创建固定口令账号。

本机访问：`http://localhost:8080`。Compose 固定只监听 `127.0.0.1`，不能通过环境变量改成全网卡监听。

若供其他试点成员访问，必须在同一主机前置 TLS 反向代理，只向外开放 `443`，并把 `PUBLIC_URL` 设为 `https://...`。应用会拒绝任何非回环地址的 HTTP `PUBLIC_URL` / CORS 配置。最外层代理还必须按真实客户端 IP 对登录入口限流；容器内限流是第二道保护，经过外层代理时可能把多个用户聚合到同一桶。示例 Nginx 终止层：

```nginx
# 放在 http {} 中：
limit_req_zone $binary_remote_addr zone=vela_login:10m rate=10r/m;

server {
    listen 443 ssl http2;
    server_name vela.example.com;
    ssl_certificate     /etc/ssl/vela/fullchain.pem;
    ssl_certificate_key /etc/ssl/vela/privkey.pem;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location = /api/v1/auth/login {
        limit_req zone=vela_login burst=5 nodelay;
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

证书私钥不得进入仓库、镜像或发布 ZIP。浏览器令牌仅保存在当前标签页会话，关闭会话后须重新登录。

## 关键环境变量

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥，生产必改；至少 32 字符且应由密码学随机数生成器产生 |
| `POSTGRES_PASSWORD` | PostgreSQL 密码，至少 16 字符并由随机数生成器产生；入口会安全 URL 编码 |
| `INSTANCE_ORGANIZATION` | 此实例唯一允许的客户组织全称；生产必填，开通账户时必须完全一致 |
| `PUBLIC_URL` | 本机可用 `http://localhost...`；非回环地址必须为 `https://...` |
| `ALLOW_OPEN_REGISTRATION` | 本发布生产环境必须为 `false` |
| `RATE_LIMIT_ENABLED` | 本发布生产环境必须为 `true`；限制登录与注册请求频率 |
| `SSO_ENABLED` | 本发布生产环境必须为 `false`；OIDC 流程尚未进入审计边界 |
| `LLM_POLISH_ENABLED` | 本发布生产环境必须为 `false`；材料与提示词不外发 |
| `EXPORT_TEMPLATE` | `law_school`（法学院意见书）或 `legacy` |
| `EXPORT_ORG_*` | Word 意见书抬头、致/自 等 |

## 受控试点边界与账户开通

本发布只允许**单客户、单部署、私有网络或本机回环地址**的受控试点。每个实例必须设置唯一的 `INSTANCE_ORGANIZATION`，生产启动会拒绝空值，也会扫描数据库并拒绝任何空组织或不同组织的历史账号；每次认证与交互式开通同样复核组织。第二家客户必须使用另一套数据库、卷和部署，恢复备份时也必须保持同一组织全称。生产启动还会硬性拒绝开放注册、SSO、后台语料自动改写和第三方 LLM 外发；这些能力不能通过环境变量绕开。真正启用 OIDC 前，必须补齐 PKCE、nonce、ID Token 校验和安全会话交付并重新验收。

生产栈启动并完成迁移后，由部署管理员在终端交互式开通用户。密码只从隐藏输入读取，不接受命令行参数或环境变量：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend \
  python scripts/create_user.py \
  --email legal@example.com \
  --full-name "试点法务" \
  --organization "试点企业" \
  --role legal

# 按同一方式创建 --role business 的业务账号；需要运维权限时才创建 admin。
```

命令拒绝覆盖既有账号，初次登录后仍须由本人确认免责声明。固定演示账号只允许出现在 `prod_smoke.sh` 创建的临时、可销毁、本机栈中。

生产 Compose 冒烟（需 Docker）：

```bash
chmod +x scripts/prod_smoke.sh
./scripts/prod_smoke.sh
```

该脚本拒绝传入现有 env 文件，自建权限 `600` 的临时配置，并使用唯一 Compose project name；服务健康后才在该一次性回环栈内显式创建测试账号，生产启动路径不存在对应开关。退出时脚本仅删除自己创建的容器、卷与临时配置。不要把 smoke 环境暴露到公网。Docker 不可用时脚本返回非零并报告 `PENDING`，不计为通过。

## 构建与发布边界

构建前先检查四个 Dockerfile 的实际 COPY 候选。检查只报告违规文件路径和检测器名称，不输出任何疑似密钥内容：

```bash
./scripts/check_release_boundaries.sh
```

对外提交 ZIP 必须使用 allowlist 构建器，禁止直接压缩工作区：

```bash
./scripts/build_submission_package.sh /tmp/vela-capability-pack-mvp.zip
./scripts/check_release_boundaries.sh /tmp/vela-capability-pack-mvp.zip
```

构建器在临时 ZIP 上完成路径、manifest hash 与 secret 扫描后才发布最终文件。ZIP 不包含任何 `.env*`、本地数据库/Chroma/用户材料、虚拟环境、`node_modules`、旧 `frontend/dist`、测试 fixture 或 fishbone 原有文件。

## Word 导出 · 法学院模板

默认 `EXPORT_TEMPLATE=law_school`，定稿后导出文件名：

`{项目名称}_法律研究意见书.docx`

该名称是导出模板标签，不改变内容性质：系统生成的是须经法务逐条复核的协查底稿，不构成正式法律意见。

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
- 后端卷 `backend_data`（SQLite 不用；仅保存运行时状态，法源使用镜像内的版本化制品）

应用数据库中的审计记录和导出审计包用于可追溯复核，但本 RC 不把数据库管理员列入防篡改威胁边界，也不内置数字签名、哈希链或 WORM 存储。每次正式定稿后，应把导出的审计包及其 SHA-256 交由客户现有的不可变归档/对象锁存储保管，并由独立备份策略保护 PostgreSQL；需要抗特权管理员篡改时，须先接入签名与外部 WORM 再扩大使用。

## 数据保留与试点退出

受控试点开始前，客户与部署方必须书面确定材料保留期限、备份期限、可访问人员和删除责任人。`pgdata`、`backend_data` 及其备份必须位于主机级或存储级加密介质，备份也须加密并限制恢复权限；Compose 本身不提供静态数据加密。

上传入口会校验扩展名、容器签名、大小/数量、压缩炸弹，并拒绝 PDF JavaScript/启动动作/嵌入文件及 DOCX 宏、ActiveX、OLE、外部模板等常见主动内容，但**不包含完整杀毒或内容净化（CDR）**。本 RC 只接受已由客户受管终端或 DMS 扫描的内部材料；法务下载原件时仍须使用隔离查看器。接收外部不可信上传或扩大账户范围前，必须接入并验收企业 AV/CDR。单项目最多归档 30 个/250MB 原件，整个实例最多 5GB；达到上限后先按批准的保留政策清理或扩容并重新评估。

界面的“归档/删除”是可恢复的业务软删除，不是 LGPD 意义上的物理擦除。当前单租户 RC 不提供在线逐项目硬删除：收到正式删除请求时，应先停止该客户实例、完成获批的必要导出，再由部署管理员销毁该实例的数据库卷、后端卷及到期备份，并留存操作记录。试点退出不得把旧卷复用于另一组织；系统也会因历史账号与 `INSTANCE_ORGANIZATION` 不一致而拒绝启动。

## 本地开发 vs 生产

| 项 | 开发 `./scripts/start.sh` | 生产 compose |
|----|---------------------------|--------------|
| 数据库 | SQLite | PostgreSQL |
| 前端 | Vite dev | Nginx 静态 |
| 注册 | 开放 | 可关闭 |
| 演示账号 | `scripts/start.sh` 本地创建 | 启动路径不支持创建；只能交互式开通正式账号 |
| 导出模板 | law_school | law_school |
