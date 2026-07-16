# Vela 出海法务平台

拉美涉外投资合规协查与法律风险简报助手 — 面向企业法务部的 Web SaaS。

**唯一正式主流程：** 业务上传项目材料并确认知情 → 后端提出 Capability Pack → 法务确认场景与维度并冻结快照 → 系统生成清单、RAG 与双语简报 → 法务复核 → Word/PDF 导出

**演示场景：** BYD 坎皮纳斯类新能源制造绿地设厂（巴西 · 圣保罗州）

**能力边界：** 当前 Registry 只有一个正式包 `brazil_new_energy_greenfield`（巴西 · 新能源制造 · 绿地设厂）。`test_fixture_pack` 仅用于自动化测试，不是真实国家、行业或法律能力，也不会进入生产 Registry 或发布制品。

**法律责任边界：** AI 输出仅是可溯源的协查底稿，必须经过法务逐条复核和定稿，不构成正式法律意见。

**复赛演示：** 只走 [`docs/DEMO_GOLDEN_PATH.md`](docs/DEMO_GOLDEN_PATH.md) 一条线；门控说明见 [`docs/match_tier_and_gate.md`](docs/match_tier_and_gate.md)。

### P1 LLM + Harness（复赛）

| 能力 | 说明 |
|------|------|
| **Gate A 缺口优先** | 协查缺口摘要、材料 House Rules、法条默认折叠 |
| **B1 议题识别** | LLM 建议核查项 + grounding 护栏，法务勾选后并入清单 |
| **B2 材料 Playbook** | `material_house_rules.json` 纯规则预检 |
| **B3/B4** | 缺口说明 / S2 Red Team（不改 tier） |
| **AI 设置栏** | 工作台 → **AI 设置**：Provider、Base URL、Model、API Key、测试连接 |
| **Golden Path** | 无 LLM Key 时规则回退，E2E `15/15` |

详见 [`docs/P1_LLM_HARNESS.md`](docs/P1_LLM_HARNESS.md)。

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
# .env 可选；发布包不包含任何 .env*。如需 LLM，请通过本地环境变量安全注入。
python scripts/seed_demo_user.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

- 前端：http://127.0.0.1:5173
- 后端 API：http://127.0.0.1:8000
- 本地开发演示账户：`legal@demo.vela` / `biz@demo.vela`（密码均为 `Demo1234!`，仅由 `scripts/start.sh` 或手工 seed 创建；生产默认不创建）
- 演示 business 可直接进入业务工作台，不填写 Legal Playbook；演示 legal 已预置 `demo-legal-playbook-v1.0.0`。真实 business 同样不做 Legal onboarding，真实新 legal 用户仍须完成 onboarding。

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

### Scope Confirmation Golden Path（推荐）

| 步骤 | 页面 | 说明 |
|------|------|------|
| 1 | 业务上传材料 | 明确展示「巴西 · 新能源制造 · 绿地设厂」，业务勾选知情后提交，进入 `pending_scope` |
| 2 | 法务范围确认 | 查看 Capability Pack、材料缺口和适配结论，选择维度后点击 **确认范围并生成** |
| 3 | 原子生成 | 冻结 Capability Pack、规则、语料和检索配置快照，再生成清单、法源绑定和双语简报 |
| 4 | 法务复核 | 70 分门控；逐条确认 / 驳回 / 批注并定稿 |
| 5 | 导出 | Word/PDF 协查底稿 |

旧的 `/scenarios` 直接生成、`generate-and-submit` 和 `demo/sample` 一键绕过接口均已关闭并返回 `410 Gone`。`POST /retrieve` 与 `POST /brief` 仅是读取历史结果的兼容别名，不会启动生成。

---

## Docker

```bash
docker compose up --build
# 仅本地开发需要演示账号时显式执行
docker compose exec backend python scripts/seed_demo_user.py
```

生产部署不会默认创建演示账号，见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。构建前可运行 `./scripts/check_release_boundaries.sh` 检查 Docker COPY 候选；提交包使用 `./scripts/build_submission_package.sh /tmp/vela-capability-pack-mvp.zip`，禁止直接压缩工作区。

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

### Step 2 — Capability Pack 与范围确认

- [x] 唯一正式 Capability Pack `brazil_new_energy_greenfield`，绑定巴西新能源规则制品 **v2.9** 与正式语料制品
- [x] 业务上传材料并确认知情，只创建 `pending_scope` 与后端 `proposed` scope
- [x] 法务确认适配、维度和议题后原子冻结 snapshot，再启动唯一 generation attempt
- [x] BYD 坎皮纳斯演示场景模板
- [x] 无有效 snapshot 时，清单、RAG、简报和复核初始化全部 fail closed

### Step 3 — 法源 RAG（增强）

- [x] 精选法源库 **70+ 条**（LexML / Planalto / STF / gov.br / 案例索引；扩库走人工审核队列）
- [x] 法务确认后，同一 generation attempt 为清单条目检索冻结 Top-K 法条片段 + LexML 溯源链接
- [x] 匹配度评分，低于 70 分标记「需法务复核」
- [x] 中英葡关键词联合打分（跨语种检索增强）
- [x] 法规动态监测 MVP（手动扫描 + 提醒列表）

### Step 4 — 清单生成（规则 + 核查项定位）

- [x] 只从冻结 snapshot 与绑定规则制品构造 ScenarioInput 并生成清单
- [x] 可选 LLM 核查项定位不得扩展 snapshot 之外的维度或议题

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
- [x] LLM 中文场景核查项定位（清单条目触发辅助）

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
| GET | `/api/v1/capability-packs` | 当前正式启用的 Capability Pack |
| GET | `/api/v1/capability-packs/catalog` | 当前正式包的规则与维度元数据 |
| GET | `/api/v1/rules/demo-template` | BYD 演示模板 |
| POST | `/api/v1/scenarios/submit-materials` | 业务提交材料与知情确认，创建 `pending_scope` 记录；不生成 |
| POST | `/api/v1/scenarios/{id}/confirm-scope` | 法务原子确认范围、冻结快照并启动唯一生成任务 |
| POST | `/api/v1/scenarios/{id}/retry-generation` | 失败后沿用原快照创建新 attempt |
| GET | `/api/v1/scenarios` | 场景列表 |
| GET | `/api/v1/scenarios/{id}` | 场景详情 + 清单 |

### 法源检索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/legal/status` | 法源索引状态 |
| POST | `/api/v1/legal/index` | 构建法源索引 |
| POST | `/api/v1/scenarios/{id}/retrieve` | **废弃的只读兼容别名**：返回确认阶段已生成的法源结果，不启动 RAG |

### 简报

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/scenarios/{id}/brief` | 获取已生成简报 |
| POST | `/api/v1/scenarios/{id}/brief` | **废弃的只读兼容别名**：忽略 `polish`，不生成或润色 |

### 已关闭的绕过入口

以下接口仅返回 `410 Gone`：`POST /api/v1/scenarios`、`POST /api/v1/scenarios/generate-and-submit`、`POST /api/v1/scenarios/demo/generate-and-submit`、`POST /api/v1/scenarios/demo/sample`。

### 法务复核

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/scenarios/{id}/review` | 获取复核状态 |
| POST | `/api/v1/scenarios/{id}/review/init` | 仅基于已生成结果初始化复核；不得隐式生成 |
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
| GET | `/api/v1/rules/demo-template` | BYD 坎皮纳斯投资协查演示 |
| GET | `/api/v1/rules/demo-template/mining` | ~~矿产模板~~ **501 未上线**（先深耕巴西投资协查） |

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

仓库中的预生成静态排版样本（仅作展示备份，不代表当前运行实时生成）：

- `BYD坎皮纳斯_协查底稿_样本.docx` — 规则模板版
- `BYD坎皮纳斯_协查底稿_LLM润色.docx` — 通义千问润色版

---

## 已知限制与后续规划

**产品策略：** 当前只对 `brazil_new_energy_greenfield` 提供完整支持，即 **巴西 · 新能源制造 · 绿地设厂**。规则与语料围绕 BYD 坎皮纳斯类项目验证；并购、研发机构、既有工厂扩建、矿产、跨境电商及其他国家/行业均不属于当前正式能力。

| 项 | 现状 | 规划 |
|----|------|------|
| 正式 Capability Pack | **`brazil_new_energy_greenfield`**：巴西 · 新能源制造 · 绿地设厂；规则制品 v2.9 | 经法律内容审核后再增加独立能力包 |
| 法域与动作 | 巴西单国 · 绿地设厂 | 其他国家、并购或扩建尚未上线 |
| 法源库 | **70+ 条**精选语料（v1.9 已清洗 HTML）+ 可选 Chroma | `backend/scripts/propose_corpus_entry.py` + `data/corpus_pending_review.json` 人工审核 |
| 核查项定位 | 冻结 snapshot + 规则触发 + 可选受限 LLM（不得扩展维度或议题） | 随后续独立 Capability Pack 验证扩展 |
| 法规监测 | 手动扫描 + 提醒列表 | 自动爬虫 + 订阅推送 |
| 导出 | Word 法学院意见书 + PDF legacy 底稿 | 律所 `.docx` 样张加载、PDF 与 Word 统一 |
| 角色 | 业务提交 / 法务复核分权 | ✅ 已实现 |

---

## 许可证

本项目为演示 / 比赛用途。法条原文版权归相应官方机构所有；平台输出不构成正式法律意见。

---

## 上传 GitHub / 邀请测试者

见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**（生产 Docker / SSO / 导出配置）、**[客户操作手册.md](./客户操作手册.md)** / **[客户操作手册.docx](./客户操作手册.docx)**（面向法务/业务用户）、**[操作手册.md](./操作手册.md)** / **[操作手册.docx](./操作手册.docx)**（含部署与演示脚本）、**[GITHUB_SETUP.md](./GITHUB_SETUP.md)**、**[TESTING.md](./TESTING.md)** 与 **[API.md](./API.md)**（REST 集成说明）。
