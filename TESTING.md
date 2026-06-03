# 测试者指南

本文档面向被邀请克隆仓库的测试人员。

## 获取代码

仓库为 **Private（私有）**。请确认账号已被添加为 Collaborator，然后：

```bash
git clone https://github.com/<你的组织或用户名>/vela-platform.git
cd vela-platform
```

## 环境要求

- macOS / Linux / Windows（WSL 推荐）
- Python 3.9+
- Node.js 18+
- 可选：通义千问 API Key（启用 LLM 润色）

## 快速启动

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

浏览器打开 http://127.0.0.1:5173

| 项目 | 值 |
|------|-----|
| 演示账号 | `legal@demo.vela`（法务）/ `biz@demo.vela`（业务） |
| 演示密码 | `Demo1234!` |

## 首次配置

```bash
cd backend
cp .env.example .env
# 如需 LLM 润色，编辑 .env 填入 QWEN_API_KEY 或 DEEPSEEK_API_KEY
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_demo_user.py
```

## 推荐测试路径

### 法务角色（legal@demo.vela）

1. 登录 → 工作台 **「一键生成完整样本」**
2. 法务复核 → 全部确认 → 定稿 → **导出 Word / PDF**

### 业务 / 法务分角色流程

1. **业务**（`biz@demo.vela`）登录 → 提交协查场景 → 清单 → 双语简报 → **提交法务复核**
2. **法务**（`legal@demo.vela`）登录 → 工作台「待处理任务」→ 复核 → 定稿 → 导出

### 通用

### 自动化验收（推荐）

服务启动后运行：

```bash
chmod +x scripts/verify_e2e.sh
./scripts/verify_e2e.sh
```

覆盖：行业专包 v2、BYD 24 条清单、子赛道差异化、法务驳回→业务可见、方案上传抽取、矿产 501。

## 样本文件

仓库根目录含预生成 Word 样本（无需 API Key 也可查看效果）：

- `BYD坎皮纳斯_协查底稿_样本.docx`
- `BYD坎皮纳斯_协查底稿_LLM润色.docx`

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

首次运行会自动构建索引；若 Chroma 向量下载失败，系统会回退关键词检索，不影响演示。

## 反馈

测试问题请通过 Issue 或团队约定渠道反馈，勿在 Issue 中粘贴 API Key。
