# Vela API 集成说明

Base URL（本地）：`http://127.0.0.1:8000/api/v1`

交互式文档：

- Swagger UI：http://127.0.0.1:8000/docs
- ReDoc：http://127.0.0.1:8000/redoc

认证：除 `/health`、`/auth/login`、`/auth/register`、`/auth/sso/config`、`/export/config` 外，请求头需携带：

```http
Authorization: Bearer <JWT>
```

## 核心流程 API

| 顺序 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 0 | GET | `/capability-packs` | 读取服务端正式启用的 Capability Pack；前端提示不具有路由权威性 |
| 0b | GET | `/capability-packs/catalog` | 读取正式包的维度、阈值与展示元数据 |
| 1 | POST | `/scenarios/extract-document` | 可选：上传 `.txt/.md/.docx/.pdf` 抽取事实供业务核对 |
| 2 | POST | `/scenarios/submit-materials` | **业务角色**：上传材料并确认已知当前支持边界，创建 `pending_scope`；不生成 |
| 3 | GET | `/scenarios/{id}` | 法务读取 `scenario_scope.proposed`、`fit_assessment`、材料与 `proposal_hash` |
| 4 | POST | `/scenarios/{id}/confirm-scope` | **法务角色**：原子确认场景/维度，冻结 Capability Pack、规则、语料和生成配置快照，并启动唯一 attempt |
| 5 | GET | `/scenarios/{id}` | 读取已持久化的清单、RAG、简报和 attempt 状态；不得通过读接口隐式生成 |
| 6 | POST | `/scenarios/{id}/review/init` | 仅基于已有生成结果初始化复核 |
| 7 | PATCH | `/scenarios/{id}/review/items/{code}` | 更新复核项 |
| 7b | POST | `/scenarios/{id}/review/return-to-business` | **法务**：退回业务在同一项目补充 |
| 8 | POST | `/scenarios/{id}/review/finalize` | **法务角色**：定稿 |
| 8b | POST | `/scenarios/{id}/revise-and-resubmit` | **业务**：补充材料后重新进入 `pending_scope` |
| 9 | GET | `/scenarios/{id}/export/docx` | **法务角色**：导出 Word（默认法学院《法律研究意见书》） |
| 9b | GET | `/scenarios/{id}/export/pdf` | **法务角色**：导出 PDF（legacy 协查底稿格式） |

当前 `/capability-packs` 只返回一个正式包：`brazil_new_energy_greenfield`（巴西 · 新能源制造 · 绿地设厂）。自动化测试 fixture 不是法律能力，不进入生产 Registry 或发布制品。

`confirm-scope` 请求必须携带当前 `expected_proposal_hash`、`fit_decision` 和所选 `compliance_dimensions`。相同请求幂等返回已有快照或结果；不同参数的重复确认返回冲突。失败后仅可调用 `POST /scenarios/{id}/retry-generation`，并严格沿用原快照。

## 角色

| role | 说明 |
|------|------|
| `business` | 上传项目事实与材料、确认知情、补充材料；不决定法律适用范围 |
| `legal` | 确认 Capability Pack 与协查维度、触发原子生成、复核、定稿、导出 |

本地 `./scripts/start.sh` 会创建 `biz@demo.vela` / `legal@demo.vela`（密码 `Demo1234!`）。business demo 不需要 Legal onboarding；legal demo 已绑定 `demo-legal-playbook-v1.0.0`，可直接进入正式主流程。真实新 legal 用户仍须完成 onboarding，demo profile 不与其他用户共享。生产镜像默认 `SEED_DEMO_USERS=false`，不得依赖这些固定账号。

## SSO（OpenID Connect）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/sso/config` | 是否启用 SSO、是否允许密码登录/开放注册 |
| GET | `/auth/sso/login` | 302 跳转 IdP 授权页 |
| GET | `/auth/sso/callback` | IdP 回调；交换 token 后 302 至前端 `/login/sso/callback` |

生产环境变量与安全创建方式见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**；发布 ZIP 不包含任何 `.env*`。

## Word 导出模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/export/config` | 当前模板（`law_school` / `legacy`）与文档标签 |

环境变量：

- `EXPORT_TEMPLATE=law_school` — 法学院标准《涉外投资合规法律研究意见书》
- `EXPORT_ORG_NAME` / `EXPORT_ORG_DEPARTMENT` / `EXPORT_RECIPIENT_LABEL` — 抬头与致/自/关于表

定稿后 `export/docx` 响应头 `Content-Disposition` 含 UTF-8 文件名，如 `{项目}_法律研究意见书.docx`。

模板名称与文件名仅表示导出版式；系统内容仍是须经法务逐条复核的协查底稿，不构成正式法律意见。

## 兼容与已关闭接口

| 方法 | 路径 | 语义 |
|------|------|------|
| POST | `/scenarios/{id}/retrieve` | 废弃的只读兼容别名；只返回已持久化 RAG，不启动检索 |
| POST | `/scenarios/{id}/brief` | 废弃的只读兼容别名；忽略 `polish`，不生成或润色 |
| POST | `/scenarios` | `410 Gone`；旧直接生成入口已关闭 |
| POST | `/scenarios/generate-and-submit` | `410 Gone` |
| POST | `/scenarios/demo/generate-and-submit` | `410 Gone` |
| POST | `/scenarios/demo/sample` | `410 Gone`；不再提供绕过范围确认的一键样本 |

## 法源与监测

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/legal/status` | 索引状态、语料版本、来源分布 |
| POST | `/legal/index?force=true` | 重建索引 |
| GET | `/legal/monitor` | 法规监测状态与提醒列表 |
| POST | `/legal/monitor/scan?force_reindex=false` | 手动扫描/刷新监测 |

## 法源语料维护（法务角色）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/legal/corpus/meta` | 维度、核查项编号、法源类型等元数据 |
| GET | `/legal/corpus?q=&dimension=&source=` | 列表/筛选 |
| GET | `/legal/corpus/{id}` | 单条详情 |
| POST | `/legal/corpus` | 新增法条条目 |
| PUT | `/legal/corpus/{id}` | 更新条目 |
| DELETE | `/legal/corpus/{id}` | 删除条目 |
| POST | `/legal/corpus/reindex?force=true` | 保存后重建索引 |

## 演示模板

| 方法 | 路径 |
|------|------|
| GET | `/rules/classification` | 兼容读取分类树；不表示存在多个正式能力包 |
| GET | `/rules/packs` | 兼容读取已注册规则制品；正式能力以 `/capability-packs` 为准 |
| GET | `/rules/catalog` | 当前规则包表单/清单配置（可选 `?pack_id=`） |
| GET | `/rules/demo-template` | BYD 坎皮纳斯投资协查演示 |
| GET | `/rules/demo-template/mining` | **501** — 矿产协查规则包尚未建设 |

## 嵌入 OA / 合规系统

1. 服务端调用 `POST /auth/login` 获取 JWT，或浏览器走 `/auth/sso/login` 企业 SSO
2. 按上表顺序调用 REST API
3. 定稿后导出：`export/docx`（法学院意见书）或 `export/pdf`（legacy 底稿）

CORS 默认允许 `http://localhost:5173`；生产环境在 `backend/.env` 配置 `CORS_ORIGINS`。
