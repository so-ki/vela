# 测试者指南

本文档面向被邀请克隆仓库的测试人员。

## 获取代码

受控试点仓库在推送本 RC 前必须确认为 **Private（私有）**。不要仅凭本文档假定远端已经私有；请先在 GitHub 设置页核验可见性，并确认账号已被添加为 Collaborator，然后：

```bash
git clone https://github.com/<你的组织或用户名>/vela-platform.git
cd vela-platform
```

## 环境要求

- macOS / Linux / Windows（WSL 推荐）
- Python 3.12+
- Node.js 24 LTS（CI 使用 24）
- 可选：通义千问 API Key（启用 LLM 润色）

## 快速启动

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

浏览器打开 http://127.0.0.1:5173

| 项目 | 值 |
|------|-----|
| 本地演示账号 | `legal@demo.vela`（法务）/ `biz@demo.vela`（业务）；由 `scripts/start.sh` 创建，生产默认不存在 |
| 演示密码 | `Demo1234!` |

business demo 应直接进入业务工作台且不显示 Legal Playbook；legal demo 已预置 `demo-legal-playbook-v1.0.0`，应直接进入法务工作台。真实新 legal 用户仍须完成 onboarding。

## 首次配置

```bash
cd backend
# 发布包不包含任何 .env*；如需 LLM，使用本地环境变量注入 QWEN_API_KEY 或 DEEPSEEK_API_KEY
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.lock
python scripts/seed_demo_user.py
```

## 推荐测试路径

### 业务 / 法务分角色流程

当前唯一受控试点能力包是 `brazil_new_energy_greenfield`（巴西 · 圣保罗州 · 新能源制造 · 绿地设厂；法律内容 provisional）；测试 fixture 不代表法律能力，也不应出现在生产 Registry 或发布包。

测试生成物只验证协查流程与可溯源底稿；AI 输出须经法务逐条复核，不构成正式法律意见。

1. **业务**（`biz@demo.vela`）登录 → 上传 allowlist 演示材料 `scripts/fixtures/sample_storage_project.txt` → 查看当前 Capability Pack → 勾选知情 → 提交材料，状态应为 `pending_scope`，且尚无清单/简报。
2. **法务**（`legal@demo.vela`）登录 → 查看场景卡、适配结论与材料缺口 → 选择维度 → 点击 **确认范围并生成**。
3. 确认快照已冻结，随后查看已经持久化的清单、RAG 与双语简报；刷新页面不得重新生成。
4. 法务初始化复核 → 逐条确认/驳回 → 定稿 → 导出。

旧 `/scenarios` 直接生成、`generate-and-submit` 和 `demo/sample` 必须返回 `410 Gone`；POST retrieve/brief 不得启动生成。

### 通用

### 自动化验收（推荐）

GitHub CI 会额外构建生产前后端镜像，并用一次性 PostgreSQL 16、Alembic migration gate 和回环地址执行完整 Compose 冒烟；这一步覆盖本地无 Docker 时无法证明的正式部署路径。

服务启动后运行：

```bash
chmod +x scripts/verify_e2e.sh
./scripts/verify_e2e.sh
```

覆盖：业务知情、法务原子确认、快照/attempt 幂等、Capability Pack 制品绑定、RAG/brief 只读、法务驳回→业务可见及旧入口 410。

语料变更后可调用 `curl -X POST http://127.0.0.1:8000/api/v1/legal/index?force=true`（需法务登录 token）重建确定性关键词索引标记。

## 演示与门控文档

- [复赛 Golden Path](docs/DEMO_GOLDEN_PATH.md)
- [匹配度与 S1/S2/S3 门控](docs/match_tier_and_gate.md)
- [合规与安全边界](docs/compliance_and_security.md)

## 样本文件

发布 ZIP 不携带预生成 Word 样本，避免把未经本轮复核的静态输出误当成当前结果。请按黄金路径完成法务定稿后，从运行中的系统导出 Word/PDF；没有完成定稿时不得用历史样本替代验收证据。

## 常见问题

**端口被占用**

```bash
lsof -ti:8000 | xargs kill -9
lsof -ti:5173 | xargs kill -9
./scripts/start.sh
```

**LLM 润色超时**

简报润色约需 60–120 秒，请耐心等待；未配置 Key 时自动使用模板模式。

**法源索引**

首次运行会自动构建确定性关键词索引；本发布不下载或运行 Chroma 向量模型。

## 反馈

测试问题请通过 Issue 或团队约定渠道反馈，勿在 Issue 中粘贴 API Key。
