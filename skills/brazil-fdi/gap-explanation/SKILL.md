---
name: gap-explanation
description: 针对 Gate A 缺项与未过门控核查项生成向业务提问与材料缺口说明（B3）；LLM 可选
compatibility: Vela D1 · B3 · gap_explanation agent_step · 协查包生成后
---

# 缺口说明（B3 · Gap Explanation）

## 用途

协查包生成且 **Gate A 聚合**完成后，对「构成要件缺失」或「匹配度未过线」的条目，生成**面向业务的待办问题**与建议补充材料清单。帮助法务打回材料时有结构化话术，**不输出法律结论**。

## 步骤

1. **收集目标 code**（上限 20 条）：
   - 简报中 `gate_status != passed` 的条目；
   - `investigation_adequacy.dimensions[].elements` 中 `status` 为 `missing` / `at_risk` 的关联 code。
2. **前置检查**：无目标或 LLM 未启用 → `agent_step.status = skipped`。
3. **LLM 生成**（任务 `gap`）：
   - 输入各 code 的 title、block_reason、element 状态；
   - 输出 JSON：`items[{ code, questions_zh, questions_pt, material_gaps, suggested_documents }]`。
4. **Harness 过滤**：
   - 丢弃含法条号、法令名、LexML URL 的字段；
   - 丢弃 `legal_conclusion` 类表述；
   - 截断过长字符串。
5. **写入 payload**：`gap_explanations[]`，追加 `agent_step: gap_explanation`。

## 输入

| 名称 | 类型 | 说明 |
|------|------|------|
| `scenario` | InvestigationScenario | 项目上下文 |
| `payload` | dict | 含 brief、sections_with_legal |
| `adequacy` | dict | Gate A 聚合结果 |
| `user_id` | int | LLM 任务模型 `gap` |

## 输出

| 名称 | 类型 | 说明 |
|------|------|------|
| `gap_explanations` | array | 按 code 分组的缺口说明 |
| `agent_step` | object | `{ step: "gap_explanation", status, count }` |

## 前端展示

- **InvestigationAdequacyPanel**「协查缺口摘要（Gate A）」下方；
- 标注为**非阻断提示**，供 Gate A 与清单复核参考；
- 构成要件仍不完整时，法务应**打回业务**而非仅依赖 B3 文案。

## 硬性约束

- **禁止**出现具体法条号、法令名称、LexML URL。
- **禁止**输出法律定性或监管结论。
- 仅生成中/葡提问与材料清单，不修改核查项定义或 RAG 结果。

## 法律免责声明

缺口说明为协查过程沟通辅助，**不构成对合规义务的最终解释**。业务答复与材料真实性由提交方负责。
