---
name: investigation-pack
description: 编排巴西 FDI 协查包生成全流程；agent_steps 顺序与 legal_agent_service 及 scenario_pipeline 一致
compatibility: Vela D1 · brazil_new_energy v2.9+ · pending_scope → pending_legal_review
---

# 协查包编排（Investigation Pack）

## 用途

法务在 **待确认协查范围**（`pending_scope`）阶段勾选合规维度后，一次性生成：**核查清单 · 多源 RAG · 匹配度门控 · 简报草稿 · Gate A 聚合 · 辅助 Harness 输出**，并进入 `pending_legal_review`。

## 编排顺序

### 阶段 A — 业务提交后（Gate A 预览，不生成清单）

| 序号 | 步骤 | 技能 | agent_step |
|------|------|------|------------|
| A1 | 材料事实抽取 | legal-element-extraction | — |
| A2 | 材料 House Rules | material-house-rules | — |
| A3 | 议题识别建议 | dispute-issue-identification | `issue_identification` |

实现入口：`enrich_pending_scope_payload()`。

### 阶段 B — 法务确认范围并生成协查包

| 序号 | 步骤 | 技能 | agent_step |
|------|------|------|------------|
| B0 | 按维度 + 已选议题重建清单 | 规则引擎 | — |
| B1 | **retrieve** — 法条检索 | legal-article-retrieval | `retrieve` |
| B2 | **grounding** — 引证校验 | grounding-verification | `grounding` |
| B3 | **tier_classify** — S1/S2/S3 分级 | 匹配度门控 | `tier_classify` |
| B4 | 双语简报生成 | brief_generator | — |
| B5 | Red Team 质询 | red-team-challenge | `red_team` |
| B6 | Gate A 构成要件聚合 | investigation_adequacy | — |
| B7 | 缺口说明 | gap-explanation | `gap_explanation` |

**B1–B3 与 `legal_agent_service.run_investigation_agent()` 中 `agent_steps` 数组顺序一致**：`retrieve` → `grounding` → `tier_classify`。后续步骤由 `scenario_pipeline._attach_legal_and_brief()` 与 `run_generate_investigation_pack()` 追加。

### agent_steps 终态示例

```json
[
  {"step": "retrieve", "status": "ok", "connector": true},
  {"step": "grounding", "status": "ok"},
  {"step": "tier_classify", "status": "ok", "S1": 12, "S2": 3, "S3": 0},
  {"step": "red_team", "status": "ok", "count": 2},
  {"step": "gap_explanation", "status": "ok", "count": 4}
]
```

`grounding.status` 为 `review` 时表示存在需法务关注的未 grounded 命中；`tier_classify.status` 为 `blocked` 时表示存在 S3 硬阻断条目。

## 步骤说明

1. **读取用户偏好**：匹配度阈值（默认 70）、Top-K（默认 3）、Playbook 冷启动画像。
2. **调用 Brazil Connector**（默认开启）：对每条核查项执行关键词优先 RAG，附带 LexML URN/URL。
3. **Grounding 校验**：检索片段须能在语料原文中找到对应 span，否则标记 citation 状态。
4. **分级门控**：S3 高优先级且无可靠法条支撑时硬阻断进入「通过态」。
5. **简报**：规则模板生成中葡双语摘要；可选 LLM 润色（不新增法条）。
6. **Red Team / Gap**：仅对 S2 或未过门控条目生成辅助提问；LLM 未启用则跳过。

## 输入

| 字段 | 来源 | 说明 |
|------|------|------|
| `scenario` | 数据库 | 项目材料、法域、行业 |
| `compliance_dimensions` | 法务勾选 | labor / foreign_investment / tax / environment / industry_access |
| `match_threshold` | 复核页滑块 | 50–95，默认 70 |
| `retrieval_top_k` | 复核页滑块 | 1–10，默认 3 |
| `selected_issue_codes` | B1 勾选结果 | 并入清单的额外核查项 code |
| `polish` | 请求参数 | 是否 LLM 润色简报 |

## 输出

| 字段 | 说明 |
|------|------|
| `sections_with_legal` | 带法条绑定的核查清单 |
| `brief` | 双语简报（含 gate_status、blocked_count） |
| `investigation_adequacy` | Gate A 聚合（缺项 / 待核实 / S2 / S3） |
| `gap_explanations` | B3 向业务提问清单 |
| `red_team` | B4 质询条目 |
| `agent_steps` | 可审计的步骤轨迹 |
| `investigation_settings` | 实际生效的阈值与 Top-K |

## 失败与安全

- 状态非 `pending_scope` 时拒绝生成。
- S3 硬阻断时简报可能为 `brief_blocked`，仍可在 Gate A 查看全量结果。
- 增量更新模式（材料打回后）：仅重算变更字段关联条目，其余沿用上一版草稿。

## 法律免责声明

协查包为系统辅助生成的工作底稿，**须经法务逐条复核并人工定稿**后方可导出。Agent 编排不替代律师专业判断；对外法律意见须由持证律师出具。
