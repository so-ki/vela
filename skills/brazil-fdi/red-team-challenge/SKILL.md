---
name: red-team-challenge
description: 对 S2 及需复核条目生成对抗性质询（B4）；LLM 可选，不修改 gate 结论
compatibility: Vela D1 · B4 · red_team agent_step · 简报生成后
---

# Red Team 质询（B4 · Red Team Challenge）

## 用途

在简报草稿生成后，对 **S2（需法务复核）** 或匹配度边缘条目发起「对抗性提问」，促使法务在定稿前主动质疑假设与材料缺口。Red Team **不改变** gate_status、匹配度分数或法条绑定。

## 步骤

1. **筛选目标条目**：从 `sections_with_legal` 中选取 tier 为 S2 或 `requires_review` 的核查项。
2. **前置检查**：无 S2 条目或 LLM 未启用 → `agent_step.status = skipped`。
3. **LLM 质询**（任务 `red_team`）：
   - 输入条目 code、title、risk 摘要、材料摘要；
   - 输出 JSON：`items[{ code, challenges[{ question, severity }], red_team_note }]`。
4. **Harness 过滤**：
   - 每条最多 5 个 challenge，`severity` 限 high/medium/low；
   - 截断 question 与 red_team_note 长度；
   - 丢弃含新法条或新结论的表述。
5. **写入 payload**：`red_team[]`，追加 `agent_step: red_team`。

## 输入

| 名称 | 类型 | 说明 |
|------|------|------|
| `sections` | array | 带法条与 tier 的核查清单 |
| `material_summary` | string | 项目材料摘要（≤2000 字） |
| `user_id` | int | LLM 任务模型 `red_team` |

## 输出

| 名称 | 类型 | 说明 |
|------|------|------|
| `red_team` | array | 按 code 分组的质询列表 |
| `agent_step` | object | `{ step: "red_team", status, s2_count, count }` |

## 与 B3 的区别

| | B3 Gap | B4 Red Team |
|---|--------|-------------|
| 侧重点 | 缺什么材料、问业务什么 | 质疑结论假设、复核严谨性 |
| 触发 | Gate A 缺项 + blocked 条目 |  primarily S2 条目 |
| 阶段 | Gate A 聚合之后 | 简报生成后、与 B3 并行写入 |

## 硬性约束

- 不得新增核查项 code、法条引用或改变 tier 分级。
- 质询须可被法务忽略；无 S2 时不强行生成内容。
- 合同审查模块有独立 Red Team 路径，本技能仅服务 **FDI 协查包**。

## 法律免责声明

Red Team 输出为内部复核辅助提问，**不代表对方立场或监管观点**。定稿结论仍须法务人工确认。
