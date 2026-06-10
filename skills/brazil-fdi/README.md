# 巴西 FDI 协查 · D1 Skills 文档树

本目录为 **Vela 出海法务平台** 巴西直接投资（FDI）协查链路的 **D1 阶段技能说明**，供 Agent、集成方与法务培训使用。内容依据 `vela-platform` 后端服务与前端 Gate A 流程编写，**不替代正式法律意见**。

## 技能一览

| 技能 | 代号 | 触发阶段 | 是否依赖 LLM |
|------|------|----------|--------------|
| [investigation-pack](./investigation-pack/SKILL.md) | 编排 | 法务生成协查包 | 部分步骤可选 |
| [legal-element-extraction](./legal-element-extraction/SKILL.md) | A1 | 业务提交材料 / 上传方案 | 可选（未配置则规则+表单） |
| [material-house-rules](./material-house-rules/SKILL.md) | B2 | Gate A 范围确认前 | 否（结构化规则） |
| [dispute-issue-identification](./dispute-issue-identification/SKILL.md) | B1 | Gate A 范围确认前 | 可选 |
| [legal-article-retrieval](./legal-article-retrieval/SKILL.md) | RAG | 协查包生成 | 否（关键词优先） |
| [grounding-verification](./grounding-verification/SKILL.md) | Grounding | RAG 之后 | 否 |
| [gap-explanation](./gap-explanation/SKILL.md) | B3 | 协查包生成后 · Gate A 聚合 | 可选 |
| [red-team-challenge](./red-team-challenge/SKILL.md) | B4 | 简报生成后 | 可选 |

## 主流程（Golden Path 摘要）

```
业务提交材料 → A1 抽取 → B2 House Rules + B1 议题建议（可选）
    → 法务选定维度 / 阈值 / Top-N → 生成协查包
    → RAG 检索 → Grounding → 匹配度分级（S1/S2/S3）
    → 简报草稿 → B4 Red Team → Gate A 聚合 → B3 缺口说明
    → 法务逐条复核 → 人工定稿 → Word 导出
```

## 设计原则

1. **关键词优先检索**：法条绑定来自精选语料与 LexML/官方法源外链，RAG 不编造条文。
2. **LLM 为可选 Harness**：A1/B1/B3/B4 与简报润色在未配置 API 时自动跳过或回退规则模板；**不得因未配 LLM 而阻断主流程**。
3. **法务定范围、人工定稿**：协查维度、议题勾选、匹配度阈值、逐条复核与 `finalize` 仅法务/授权用户可操作；系统输出均为协查底稿，非正式法律意见。
4. **Gate A 双阶段**：范围确认页展示材料提示（B2/B1）；协查包生成后在同一复核页展示构成要件聚合，未通过则锁定清单复核。

## 代码映射

| 技能 | 主要服务 |
|------|----------|
| investigation-pack | `scenario_pipeline.py`, `legal_agent_service.py` |
| A1 | `document_extractor.py` |
| B1 | `issue_identification_service.py` |
| B2 | `material_scope_review_service.py` |
| RAG | `legal_rag.py`, `brazil_connector_service.py` |
| Grounding | `grounding_verifier_service.py`, `grounding_utils.py` |
| B3 | `gap_explanation_service.py` |
| B4 | `red_team_service.py` |

## 相关文档

- [P1 LLM Harness 说明](../../docs/P1_LLM_HARNESS.md)
- [复赛 Golden Path](../../docs/DEMO_GOLDEN_PATH.md)
- [匹配度与门控](../../docs/match_tier_and_gate.md)

## 法律免责声明

Vela 平台输出为**投资合规协查辅助材料**，基于公开法源与用户提供事实，**不构成律师意见、法律确定性判断或监管批复**。所有法条引用须经持证法务人员核实；定稿与对外交付责任由用户机构自行承担。
