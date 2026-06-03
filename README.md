# Vela 出海法务平台

拉美涉外投资合规协查与法律风险简报助手 — 面向企业法务部的 Web SaaS。

**主流程：** 中文场景输入 → 专项核查清单 → 多源 RAG（LexML / STF / STJ）→ 70 分门控 → 中葡双语简报 → 法务复核 → Word 导出

**演示场景：** BYD 坎皮纳斯新能源工厂（巴西 · 圣保罗州）

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.9+ · FastAPI · SQLAlchemy · JWT |
| 前端 | Vue 3 · Vite · Pinia · Vue Router |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 向量库 | Chroma（法源索引，关键词 + 向量检索） |
| LLM | 通义千问 DashScope / DeepSeek（简报润色，可选） |

---

## 快速启动

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

或分别启动：

```bash
# 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/seed_demo_user.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

- 前端：http://127.0.0.1:5173
- 后端 API：http://127.0.0.1:8000
- 演示账户：`legal@demo.vela` / `biz@demo.vela`（密码均为 `Demo1234!`）

### LLM 润色（可选）

在 `backend/.env` 中配置任选其一：

```env
# 通义千问（推荐）
QWEN_API_KEY=sk-...
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus

# 或 DeepSeek
# DEEPSEEK_API_KEY=sk-...
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# DEEPSEEK_MODEL=deepseek-chat

LLM_POLISH_ENABLED=true
```

重启后端后，访问 `GET /api/v1/llm/status` 或简报页查看是否启用。未配置 Key 时自动回退为规则模板模式。

---

## 演示路径

### 一键完整样本（推荐）

1. 登录工作台
2. 点击 **「一键生成完整样本」**
3. 进入法务复核页 → **全部确认** → **提交复核定稿**
4. **导出 Word 底稿**

对应 API：`POST /api/v1/scenarios/demo/sample`（含法源绑定、简报生成、LLM 润色、复核初始化）

### 分步演示

| 步骤 | 页面 | 说明 |
|------|------|------|
| 1 | 提交场景 | BYD 模板或自定义中文描述 |
| 2 | 核查清单 | 按子赛道动态生成（BYD 演示约 **24 条**）/ 4 维度，自动法源检索 |
| 3 | 双语简报 | 70 分门控，可选 LLM 润色（约 1–2 分钟） |
| 4 | 法务复核 | 逐条确认 / 驳回 / 批注 |
| 5 | 导出 | Word 协查底稿 |

---

## Docker

```bash
docker compose up --build
```

---

## 目录结构

```
vela-platform/
├── backend/
│   ├── app/
│   │   ├── api/          # REST 路由
│   │   ├── core/         # 配置、数据库、认证、Chroma
│   │   ├── data/         # 巴西法源语料 brazil_legal_corpus.json
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── rules/        # 场景规则库 brazil_new_energy.json
│   │   ├── schemas/      # Pydantic 模式
│   │   └── services/     # 业务逻辑（RAG、简报、复核、导出、LLM）
│   └── scripts/          # 种子数据等
├── frontend/
│   └── src/
│       ├── api/          # API 客户端
│       ├── components/   # 通用组件
│       ├── layouts/      # 页面布局
│       ├── stores/       # Pinia 状态
│       └── views/        # 页面视图
├── docker/               # Dockerfile
└── scripts/              # 启动脚本
```

---

## 交付清单（Step 1–8）

### Step 1 — 项目骨架与认证

- [x] FastAPI 后端骨架与健康检查
- [x] 用户注册 / 登录（JWT）
- [x] 免责声明强制确认（注册勾选 + 弹窗复核）
- [x] SQLite 用户表 + 审计日志表
- [x] Chroma 向量库客户端
- [x] Vue 3 前端：登录、注册、工作台、路线图
- [x] 本地一键启动脚本 + Docker Compose

### Step 2 — 规则库与核查清单

- [x] 巴西新能源行业规则库（JSON 配置）
- [x] 场景 → 4 大审查维度映射（劳工 / 外资 / 税制 / 行业准入）
- [x] BYD 坎皮纳斯演示场景模板
- [x] 提交场景 + 自动生成《专项核查清单》（新能源专包 · 子赛道识别）

### Step 3 — 法源 RAG（增强）

- [x] 精选法源库 **32 条**（LexML / STF / STJ / **Jusbrasil**）
- [x] 清单条目自动检索 Top-3 法条片段 + LexML 溯源链接
- [x] 匹配度评分，低于 70 分标记「需法务复核」
- [x] 中英葡关键词联合打分（跨语种检索增强）
- [x] 法规动态监测 MVP（手动扫描 + 提醒列表）

### Step 4 — 清单生成（规则 + LLM 意图）

- [x] 中文场景字段 + 关键词映射生成清单
- [x] 可选 LLM 意图解析（通义千问 / DeepSeek，补充审查维度与关键词）

### Step 5 — 双语法律风险简报

- [x] 条目级 70 分门控
- [x] 中葡双语执行摘要 + 分维度风险说明
- [x] 法条引用与溯源链接

### Step 6 — 法务复核工作台

- [x] 逐条确认 / 驳回 / 批注
- [x] 全部确认、提交复核定稿
- [x] 状态流转与审计日志

### Step 7 — Word / PDF 导出

- [x] 导出协查底稿 Word（.docx）
- [x] 导出协查底稿 PDF（.pdf）

### Step 8 — LLM 增强

- [x] 通义千问 / DeepSeek 双语简报润色
- [x] LLM 中文场景意图解析（清单维度补充）

---

## API 端点

### 系统与认证

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查（无需登录） |
| GET | `/api/v1/status` | 系统状态（数据库、Chroma） |
| GET | `/api/v1/llm/status` | LLM 润色服务状态 |
| GET | `/api/v1/auth/disclaimer` | 获取免责声明 |
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录 |
| GET | `/api/v1/auth/me` | 当前用户 |
| POST | `/api/v1/auth/accept-disclaimer` | 确认免责条款 |

### 规则与场景

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/rules/catalog` | 规则库元数据 |
| GET | `/api/v1/rules/demo-template` | BYD 演示模板 |
| POST | `/api/v1/scenarios` | 提交场景并生成清单 |
| POST | `/api/v1/scenarios/demo/byd-campinas` | 一键生成演示清单 |
| POST | `/api/v1/scenarios/demo/sample` | 一键生成完整样本（清单+法源+简报+复核） |
| GET | `/api/v1/scenarios` | 场景列表 |
| GET | `/api/v1/scenarios/{id}` | 场景详情 + 清单 |

### 法源检索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/legal/status` | 法源索引状态 |
| POST | `/api/v1/legal/index` | 构建法源索引 |
| POST | `/api/v1/scenarios/{id}/retrieve` | 清单条目绑定法条 |

### 简报

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/scenarios/{id}/brief` | 获取已生成简报 |
| POST | `/api/v1/scenarios/{id}/brief?polish=true` | 生成简报（默认启用 LLM 润色） |

### 法务复核

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/scenarios/{id}/submit` | 业务提交人：提交法务复核 |
| GET | `/api/v1/scenarios/{id}/review` | 获取复核状态 |
| POST | `/api/v1/scenarios/{id}/review/init` | 初始化复核 |
| PATCH | `/api/v1/scenarios/{id}/review/items/{code}` | 更新单条复核 |
| POST | `/api/v1/scenarios/{id}/review/approve-all` | 全部确认 |
| POST | `/api/v1/scenarios/{id}/review/finalize` | 提交复核定稿 |

### 导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/scenarios/{id}/export/docx` | 导出 Word 法律研究意见书（法学院模板，需复核定稿） |
| GET | `/api/v1/scenarios/{id}/export/pdf` | 导出 PDF 协查底稿（legacy 格式，需复核定稿） |

### 法源监测

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/legal/monitor` | 法规动态监测状态与提醒 |
| POST | `/api/v1/legal/monitor/scan` | 手动扫描/刷新监测（可选 force_reindex） |

### 演示模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/rules/demo-template` | BYD 新能源设厂 |
| GET | `/api/v1/rules/demo-template/mining` | ~~矿产模板~~ **501 未上线**（先深耕新能源专包） |

---

## 开放法源

| 法源 | 网址 |
|------|------|
| LexML Brasil | https://www.lexml.gov.br/ |
| STF | https://portal.stf.jus.br/jurisprudencia/ |
| STJ | https://scon.stj.jus.br/SCON/ |

---

## 合规设计要点

- 匹配度 **低于 70 分** 或 **未命中法条** → 强制标注「需法务复核」，不自动定稿
- LLM **仅润色措辞**，不新增法律结论、法条名称或溯源链接
- 免责声明贯穿注册、简报与 Word 导出
- 每条风险说明附 **LexML / STF / STJ** 可点击溯源

---

## 样本文件

本地生成的演示样本（需先运行一键样本或导出）：

- `BYD坎皮纳斯_协查底稿_样本.docx` — 规则模板版
- `BYD坎皮纳斯_协查底稿_LLM润色.docx` — 通义千问润色版

---

## 已知限制与后续规划

**产品策略：** 先做好 **一个行业专包**（巴西 · 新能源绿地设厂），再扩展矿产、跨境电商等。当前规则库、法源语料、子赛道识别均围绕 BYD 坎皮纳斯类场景深度建设。

| 项 | 现状 | 规划 |
|----|------|------|
| 行业专包 | **巴西 · 新能源制造 v2.0**（25 条核查项 + 5 子赛道） | 单行业做深后再开新 JSON 规则包 |
| 法域 | 巴西单国 · 圣保罗/坎皮纳斯 | 拉美多法域扩展 |
| 法源库 | 32 条精选语料 + Jusbrasil + Chroma | LexML 增量同步、语料扩容 |
| 意图解析 | 规则引擎 + 子赛道关键词 + 可选 LLM | 全 LLM 解析模式 |
| 法规监测 | 手动扫描 + 提醒列表 | 自动爬虫 + 订阅推送 |
| 导出 | Word 法学院意见书 + PDF legacy 底稿 | 律所 `.docx` 样张加载、PDF 与 Word 统一 |
| 角色 | 业务提交 / 法务复核分权 | ✅ 已实现 |

---

## 许可证

本项目为演示 / 比赛用途。法条原文版权归相应官方机构所有；平台输出不构成正式法律意见。

---

## 上传 GitHub / 邀请测试者

见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**（生产 Docker / SSO / 导出配置）、**[客户操作手册.md](./客户操作手册.md)** / **[客户操作手册.docx](./客户操作手册.docx)**（面向法务/业务用户）、**[操作手册.md](./操作手册.md)** / **[操作手册.docx](./操作手册.docx)**（含部署与演示脚本）、**[GITHUB_SETUP.md](./GITHUB_SETUP.md)**、**[TESTING.md](./TESTING.md)** 与 **[API.md](./API.md)**（REST 集成说明）。
