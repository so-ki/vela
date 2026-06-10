---
name: grounding-verification
description: 校验 RAG 摘录是否可在语料原文中定位（Grounding）；grounding agent_step
compatibility: Vela D1 · Lavern-inspired · GROUNDED_THRESHOLD 默认 0.55
---

# 引证校验（Grounding Verification）

## 用途

在法条检索之后，验证每条 **RAG 命中摘录**是否能在语料库对应文档的清洗正文中找到足够重叠的 span。防止「检索到错误文档片段」或「展示与原文不符」的引证进入简报与导出。

## 步骤

1. **加载语料索引**：`load_corpus()`，按 `hit.id` 映射源文档。
2. **逐条命中校验**：
   - 取 `excerpt_pt` / `text_pt` / `excerpt_zh` 作为待验证片段；
   - 源文本优先 `text_pt_clean`，回退 `text_pt` 或 `text_for_retrieval()`。
3. **相似度计算**：`verify_snippet_in_source()` 归一化后计算 grounding_score。
4. **阈值判定**：
   - 普通优先级：`GROUNDED_THRESHOLD`（0.55）；
   - 高优先级核查项：`GROUNDED_THRESHOLD_HIGH`（更严）。
5. **标注 citation_status**：
   - `grounded` — 通过；
   - `partial` / `ungrounded` — 需法务关注。
6. **汇总 grounding_report**：
   - `requires_legal_check`：存在未 grounded 命中时为 true；
   - `agent_step: grounding`，`status: ok` 或 `review`。
7. **写回条目**：每条 hit 附加 `grounding_score`、`grounded`、`citation_status`、`grounding_note`。

## 输入

| 名称 | 类型 | 说明 |
|------|------|------|
| `sections` | array | 含 `legal_hits[]` 的检索结果 |
| 语料 `sources[]` | corpus | 本地 JSON 语料 |

## 输出

| 名称 | 类型 | 说明 |
|------|------|------|
| `sections` | array | 附加 grounding 字段后的清单 |
| `grounding_report` | object | 汇总统计与 `requires_legal_check` |
| `agent_steps[grounding]` | object | ok / review |

### grounding_report 关键字段

| 字段 | 说明 |
|------|------|
| `total_hits` | 校验命中总数 |
| `grounded_hits` | 通过数 |
| `ungrounded_hits` | 未通过数 |
| `item_results[]` | 按核查项 code 细分 |

## 与其他 Harness 的关系

| 场景 | 复用 grounding_utils |
|------|---------------------|
| A1 fact 锚点 | `verify_snippet_in_source(anchor, document_text)` |
| B1 fact_anchor | 阈值 0.45 |
| B2 House Rules | 材料 span grounding |
| RAG hit | 阈值 0.55 / 高优更严 |

## 硬性约束

- Grounding **不修复**错误命中，仅标注状态；法务须在复核页确认或驳回。
- 语料条目不存在时直接标记 `ungrounded`，理由「语料条目不存在」。
- 不得用 LLM 生成替代摘录来「通过」 grounding。

## 法律免责声明

Grounding 为文本一致性自动化检查，**不保证法律解释正确性**。Citation 通过仍须律师核对条文语境与效力。
