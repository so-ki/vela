# P1 · LLM Harness 能力摘要

> 一页说明 Vela 平台 **Phase 1** 可选 LLM 增强层：任务划分、模型配置、回退策略与合规边界。  
> 对应实现：`backend/app/services/llm_client.py`、`backend/app/api/llm_settings.py`、前端 `LlmSettingsPanel.vue`。

---

## 定位

P1 Harness 是套在 **规则引擎 + 关键词 RAG** 之上的**可选辅助层**。未配置 API Key 或未启用时，主流程（清单、检索、门控、复核、导出）**照常运行**；仅 A1/B1/B3/B4 与简报润色降级或跳过。

**核心原则：LLM 不做法条检索、不做法务定稿、不新增法律结论。**

---

## 任务矩阵

| 任务键 | 代号 | 用途 | 触发时机 | 未启用时 |
|--------|------|------|----------|----------|
| `extract` | **A1** | 方案材料 → 核对表字段 + fact 锚点 | 业务上传/提交 | 保留表单 + 规则关键词 |
| `issue_id` | **B1** | 建议追加已有核查项 code | Gate A 范围确认前 | 空建议，`skipped` |
| `gap` | **B3** | 缺项/未过线 → 向业务提问 | 协查包 + Gate A 后 | 空缺口说明 |
| `red_team` | **B4** | S2 条目对抗性质询 | 简报生成后 | 空 red_team |
| `polish` | — | 中葡简报措辞润色 | 生成简报 `?polish=true` | 规则模板简报 |

**非 LLM 路径（始终执行）**：B2 材料 House Rules、RAG 检索、Grounding、S1/S2/S3 分级、Gate A 聚合、法务复核与定稿。

---

## 模型与 Provider 设置

### 配置入口

1. **工作台 Dashboard** → 折叠面板 **「AI 设置」**（Provider · API Key · 按任务选模型）
2. **API**：`GET/PATCH /api/v1/llm/settings`，`POST /api/v1/llm/test`

### 支持的 Provider

| Provider | 说明 |
|----------|------|
| `qwen` | 通义千问（DashScope 兼容模式） |
| `deepseek` | DeepSeek API |
| `siliconflow` | SiliconFlow 托管模型 |
| `ollama` | 本地 Ollama |
| `openai_compatible` | 任意 OpenAI 兼容端点 |

### 分层模型

- **default_model**：未单独指定任务时的默认模型
- **task_models**：按任务覆盖 — `extract` / `issue_id` / `gap` / `red_team` / `polish`（留空则继承 default）

### 环境变量回退（服务端）

未保存用户偏好时，可读 `backend/.env` 中的 `QWEN_*` 或 `DEEPSEEK_*`；`LLM_POLISH_ENABLED` 控制润色开关。Key **仅存服务端或用户加密偏好**，不出现在 Skill 文档或前端明文。

---

## Harness 约束（各任务共性）

1. **JSON 结构化输出**，带 system prompt 硬性规则
2. **Grounding 过滤**（A1/B1）：材料锚点须能在源文本匹配
3. **禁止 fabrication**：不得输出语料中不存在的法条号、LexML URL、法律定性
4. **可审计**：`agent_steps` 记录 `skipped` / `ok` / `error` 及原因
5. **人机分工**：B1 建议须法务勾选；B3/B4 仅展示；**定稿仅人工** `review/finalize`

---

## 与检索门控的关系

| 能力 | LLM 参与？ |
|------|------------|
| 法条 Top-K 绑定 | **否** — 关键词 + 可选 Chroma |
| 70 分匹配度门控 | **否** |
| S3 硬阻断 | **否** |
| 简报事实与法条列表 | **否**（润色只改表述） |
| Gate A 构成要件聚合 | **否** |

---

## 快速验收

```bash
# 登录后
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/llm/status

# 连接测试
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/llm/test
```

`available: false` 时演示仍可走 Golden Path 规则模式 + 一键样本。

---

## 法律免责声明

LLM 输出为协查辅助草稿，**不构成正式法律意见**。用户须配置合规的模型服务条款；跨境传输 API Key 与材料内容的责任由用户机构自行评估。

## 延伸阅读

- [D1 Skills 树](../skills/brazil-fdi/README.md)
- [DEMO Golden Path](./DEMO_GOLDEN_PATH.md)
- [匹配度与门控](./match_tier_and_gate.md)
