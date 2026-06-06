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
| 1 | POST | `/scenarios/extract-document` | 上传方案 `.txt/.md/.docx/.pdf`，抽取事实预填表单 |
| 1 | POST | `/scenarios` | 提交场景并生成核查清单（含 LLM 意图解析，可选） |
| 2 | POST | `/scenarios/{id}/retrieve` | 法源 RAG 绑定 |
| 3 | POST | `/scenarios/{id}/brief?polish=true` | 生成双语简报 |
| 3b | POST | `/scenarios/{id}/submit` | **业务角色**：提交法务复核 |
| 4 | POST | `/scenarios/{id}/review/init` | **法务角色**：初始化复核 |
| 5 | PATCH | `/scenarios/{id}/review/items/{code}` | 更新复核项 |
| 5b | POST | `/scenarios/{id}/review/return-to-business` | **法务**：退回业务在同一项目补充 |
| 6 | POST | `/scenarios/{id}/review/finalize` | **法务角色**：定稿 |
| 6b | POST | `/scenarios/{id}/revise-and-resubmit` | **业务**：补充材料后重新提交（同一项目） |
| 7 | GET | `/scenarios/{id}/export/docx` | **法务角色**：导出 Word（默认法学院《法律研究意见书》） |
| 7b | GET | `/scenarios/{id}/export/pdf` | **法务角色**：导出 PDF（legacy 协查底稿格式） |

## 角色

| role | 说明 |
|------|------|
| `business` | 提交场景、生成清单/简报、提交法务复核 |
| `legal` | 查看全部场景、复核、定稿、导出；可一键样本 |

演示账号：`biz@demo.vela` / `legal@demo.vela`，密码 `Demo1234!`

## SSO（OpenID Connect）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/sso/config` | 是否启用 SSO、是否允许密码登录/开放注册 |
| GET | `/auth/sso/login` | 302 跳转 IdP 授权页 |
| GET | `/auth/sso/callback` | IdP 回调；交换 token 后 302 至前端 `/login/sso/callback` |

生产环境变量见 `.env.production.example` 与 **[DEPLOYMENT.md](./DEPLOYMENT.md)**。

## Word 导出模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/export/config` | 当前模板（`law_school` / `legacy`）与文档标签 |

环境变量：

- `EXPORT_TEMPLATE=law_school` — 法学院标准《涉外投资合规法律研究意见书》
- `EXPORT_ORG_NAME` / `EXPORT_ORG_DEPARTMENT` / `EXPORT_RECIPIENT_LABEL` — 抬头与致/自/关于表

定稿后 `export/docx` 响应头 `Content-Disposition` 含 UTF-8 文件名，如 `{项目}_法律研究意见书.docx`。

## 一键样本

```http
POST /scenarios/demo/sample
```

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
| GET | `/rules/classification` | 区域 → 国家 → 默认规则包分类树 |
| GET | `/rules/packs` | 已注册规则包列表 |
| GET | `/rules/catalog` | 当前规则包表单/清单配置（可选 `?pack_id=`） |
| GET | `/rules/demo-template` | BYD 坎皮纳斯投资协查演示 |
| GET | `/rules/demo-template/mining` | **501** — 矿产协查规则包尚未建设 |

## 嵌入 OA / 合规系统

1. 服务端调用 `POST /auth/login` 获取 JWT，或浏览器走 `/auth/sso/login` 企业 SSO
2. 按上表顺序调用 REST API
3. 定稿后导出：`export/docx`（法学院意见书）或 `export/pdf`（legacy 底稿）

CORS 默认允许 `http://localhost:5173`；生产环境在 `backend/.env` 配置 `CORS_ORIGINS`。
