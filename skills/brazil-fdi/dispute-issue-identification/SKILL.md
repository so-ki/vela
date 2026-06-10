---
name: dispute-issue-identification
description: 基于材料从规则库已有核查项中建议追加议题（B1）；LLM 可选，严格 grounding
compatibility: Vela D1 · B1 · Gate A 预览 · issue_identification agent_step
---

# 争议议题识别（B1 · Dispute Issue Identification）

## 用途

在法务**确认协查范围之前**，根据项目材料提示可能需要纳入清单的**额外核查项**。仅能从规则包 `checklist_items` 已有 `code` 中选择，**禁止发明新核查项或新法条**。

## 步骤

1. **材料汇总**：合并场景字段与 A1 `document_extract` 文本（上限约 8000 字）。
2. **前置检查**：
   - 材料少于 30 字 → 跳过，返回空建议；
   - LLM 未启用 → `agent_step.status = skipped`，原因「LLM 未配置」。
3. **LLM 推理**（任务 `issue_id`）：
   - 输入 `allowed_codes`、已有清单 code、行业/动作类型、材料摘要；
   - 输出 JSON：`suggestions[{ code, title, confidence, fact_anchor, rationale }]`。
4. **Harness 过滤**：
   - `code` 须在允许列表且不在现有清单中；
   - `fact_anchor` 须通过 `verify_snippet_in_source`（阈值 0.45）；
   - `confidence` 仅 `high` / `medium` / `low`。
5. **默认勾选**：`high`、`medium` 置信度建议默认勾选，法务可在复核页取消。
6. **记录 agent_step**：`issue_identification`，状态 `ok` / `empty` / `skipped` / `error`。

## 输入

| 名称 | 类型 | 说明 |
|------|------|------|
| `scenario` | InvestigationScenario | 含 industry、action_type、rules_pack_id |
| `payload` | dict | 含 document_extract、sections（若有） |
| `user_id` | int | LLM 任务模型 `issue_id` |

## 输出

| 名称 | 类型 | 说明 |
|------|------|------|
| `issue_suggestions` | array | 最多 12 条 grounded 建议 |
| `agent_step` | object | `{ step: "issue_identification", status, count? }` |

单条建议字段：`code`、`title`、`confidence`、`fact_anchor`、`rationale`、`grounded`、`selected_default`。

## 前端交互

- 展示于 **LegalMaterialGatePanel**「LLM 建议增加的核查项」面板；
- 法务勾选后随 `generateInvestigationPack` 传入 `selected_issue_codes`；
- **未勾选不影响**默认清单生成。

## 硬性约束

- 不得输出法条名称、条文号、LexML URL 或法律结论。
- 无可靠建议时返回空数组，不强行填充。
- 本技能**不触发 RAG**，不绑定法条。

## 法律免责声明

议题建议仅为协查范围讨论辅助，**最终是否纳入核查须由法务确认**。系统不对未选议题的遗漏承担法律责任。
