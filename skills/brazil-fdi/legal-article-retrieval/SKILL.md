---
name: legal-article-retrieval
description: 核查项级法条检索（关键词优先 + 可选 Chroma）；LexML 溯源，禁止编造
compatibility: Vela D1 · RAG · retrieve agent_step · brazil_legal_corpus 70+ 条
---

# 法条检索（Legal Article Retrieval）

## 用途

为每条核查项绑定 **Top-K 法条片段**，附 LexML URN、官方法源 URL 与匹配度分数。检索结果来自平台精选语料与 Brazil Connector，**严禁 LLM 编造条文**。

## 步骤

1. **构建查询**：核查项 `code`、维度、`title`、`description` 及用户扩展上下文（场景描述等，≤1200 字）。
2. **关键词打分（主路径）**：
   - 维度匹配 +20；checklist_codes 精确绑定 +45；
   - 标签 / 标题 / 正文 token 重叠 ×8；
   - 过滤已废止（`revogado`）文档；低于 `min_keyword_score`（默认 25）不返回。
3. **Chroma 向量检索（可选增强）**：
   - 仅当 Chroma 可用且关键词命中不足时补充；
   - 结果与关键词分融合，**仍以语料条目为唯一来源**。
4. **Brazil Connector**（默认 `use_brazil_connector=true`）：
   - 按州/法域过滤；记录 `connector_runs` 供审计。
5. **格式化命中**：
   - `excerpt_pt` / `excerpt_zh`、`match_score`（0–100）、`requires_review`（< 阈值）；
   - `url`、`urn`、`source_label`（LexML / STF / STJ / gov.br 等）。
6. **零命中处理**：记入 `zero_hit_items`，条目标记「需法务复核」，**不合成占位法条**。
7. **agent_step**：`retrieve`，`status: ok`，`connector: true/false`。

## 输入

| 名称 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `sections[].items[]` | array | — | 核查清单条目 |
| `match_threshold` | int | 70 | 低于此分标记需复核 |
| `retrieval_top_k` | int | 3 | 每题绑定法条数 |
| `expansion_context` | string | — | 场景扩展检索词 |
| `state` | string | — | 巴西州（如 SP） |
| `use_brazil_connector` | bool | true | 是否走 Connector |

## 输出

| 名称 | 类型 | 说明 |
|------|------|------|
| `sections_with_legal` | array | 条目附 `legal_hits[]` |
| `retrieval.total_hits` | int | 总命中数 |
| `retrieval.zero_hit_items` | array | 零命中 code 列表 |
| `retrieval.disclaimer` | string | 协查辅助声明 |
| `agent_steps[retrieve]` | object | 检索步骤状态 |

## 法源与外链

| 来源 | 说明 |
|------|------|
| LexML Brasil | 立法 URN 与链接 |
| Planalto / gov.br | 联邦与部门规范 |
| STF / STJ | 判例索引 |
| Jusbrasil | 案例索引（非全文替代） |

语料维护：`brazil_legal_corpus.json` + 人工审核队列 `corpus_pending_review.json`。

## 硬性约束

- **禁止 fabrication**：无命中则如实报告零命中，不用 LLM 补写法条。
- 匹配度低于阈值不得自动视为「已通过」。
- 扩库须走 propose → 人工审核，Agent 不得私增语料。

## 法律免责声明

展示片段摘自公开法源，**可能非全文且存在滞后**。正式引用须核对 LexML 原文与现行效力；平台不对法条废止或判例变更承担监测义务（法规监测为辅助 MVP）。
