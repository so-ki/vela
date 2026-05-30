# Vela API 集成说明

Base URL（本地）：`http://127.0.0.1:8000/api/v1`

交互式文档：

- Swagger UI：http://127.0.0.1:8000/docs
- ReDoc：http://127.0.0.1:8000/redoc

认证：除 `/health`、`/auth/login`、`/auth/register` 外，请求头需携带：

```http
Authorization: Bearer <JWT>
```

## 核心流程 API

| 顺序 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 1 | POST | `/scenarios` | 提交场景并生成核查清单（含 LLM 意图解析，可选） |
| 2 | POST | `/scenarios/{id}/retrieve` | 法源 RAG 绑定 |
| 3 | POST | `/scenarios/{id}/brief?polish=true` | 生成双语简报 |
| 4 | POST | `/scenarios/{id}/review/init` | 初始化复核 |
| 5 | PATCH | `/scenarios/{id}/review/items/{code}` | 更新复核项 |
| 6 | POST | `/scenarios/{id}/review/finalize` | 定稿 |
| 7 | GET | `/scenarios/{id}/export/docx` | 导出 Word |
| 7b | GET | `/scenarios/{id}/export/pdf` | 导出 PDF |

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

## 演示模板

| 方法 | 路径 |
|------|------|
| GET | `/rules/demo-template` | BYD 新能源设厂 |
| GET | `/rules/demo-template/mining` | 矿产投资（行业模板 MVP） |

## 嵌入 OA / 合规系统

1. 服务端调用 `POST /auth/login` 获取 JWT（或使用 SSO 网关签发）
2. 按上表顺序调用 REST API
3. 导出底稿使用 `export/docx` 或 `export/pdf` 二进制响应

CORS 默认允许 `http://localhost:5173`；生产环境在 `backend/.env` 配置 `CORS_ORIGINS`。
