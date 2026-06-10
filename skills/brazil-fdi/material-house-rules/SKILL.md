---
name: material-house-rules
description: 结构化材料范围规则检查（B2）；无 LLM，基于 material_house_rules.json
compatibility: Vela D1 · B2 · Gate A 预览 · 与 Playbook 结构化规则共用引擎
---

# 材料 House Rules（B2 · Material House Rules）

## 用途

在法务选定协查维度前，对项目材料执行 **确定性规则扫描**，发现矛盾、缺漏或与投资协查模板不一致的线索。结果展示于 Gate A 范围确认页右侧，**不阻断**协查包生成，供法务决策是否打回业务。

## 步骤

1. **构建材料语料**：拼接项目名称、描述、投资结构、规模、雇员数及 A1 抽取字段。
2. **语料长度检查**：有效文本少于 20 字则返回空 findings。
3. **逐条评估规则**：读取 `backend/app/data/material_house_rules.json` 中 `rules[]`。
4. **结构化匹配**：调用 `evaluate_structured_rule()`（must_have / must_not / pattern 等）。
5. **Grounding**：规则触发的证据 span 须能在材料语料中匹配（阈值 0.45）。
6. **合并去重**：`merge_rule_findings()` 输出最终列表。

## 规则输出字段

| 字段 | 说明 |
|------|------|
| `rule_id` | 规则标识 |
| `label` | 简短标题 |
| `risk` | RED / YELLOW 等级 |
| `guidance` | 给法务的处理建议 |
| `feeds_checklist` | 建议对照的核查项 code |
| `grounded` | 证据是否锚定材料原文 |
| `grounding_span` | 引用的材料片段 |

## 输入

| 名称 | 类型 | 说明 |
|------|------|------|
| `scenario` | InvestigationScenario | 材料字段 |
| `payload` | dict | 含 `document_extract` |

## 输出

| 名称 | 类型 | 说明 |
|------|------|------|
| `material_scope_findings` | array | 命中规则列表，可为空 |

写入时机：`run_business_submit_materials()` → `enrich_pending_scope_payload()`。

## 与 Gate A 的关系

- **B2 在生成协查包之前**运行，属于「范围确认」侧的**材料提示**；
- **Gate A 聚合**（构成要件齐否）在协查包生成后由 `investigation_adequacy_service` 计算，二者互补：B2 看材料自洽，Gate A 看材料 + RAG 是否支撑开查/复核。

## 硬性约束

- 纯规则引擎，**不调用 LLM**。
- 不输出法律定性结论，仅提示「建议核对 / 建议打回」。
- 规则变更须更新 JSON 并走版本管理，不在运行时硬编码。

## 法律免责声明

House Rules 命中仅表示材料与模板规则可能存在不一致，**不代表违法或合规结论**。是否打回补充材料由法务专业判断。
