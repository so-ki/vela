# 字段决策表 · 巴西 · 投资协查

> 规则包：`brazil_new_energy.json` v2.4  
> 协查法域：巴西（拉美首发）· 新能源及相关投资  
> 动作类型：直接投资与新建项目（含 FDI、绿地、研发、制造扩建）  
> 对齐：企业境外投资材料中**业务侧应确认的项目事实**

---

## 规则包级策略

| 项 | 决策 |
|----|------|
| 产品定位 | C 混合：固定 intake + 法务维度动态必填 |
| 业务动作 | **只上传方案** → AI 抽取 → 材料核对页确认 → 提交 |
| 业务责任 | 确认方案事实真实、完整 |
| 提交必填 | `project_name`、`investment_structure`、`description`（3 项） |
| 建议核对字段 | `description`、`investment_structure`、`funding_source`、`known_risks` |
| Gate A | 法务选定维度后，按 `dimension_field_requirements` 检查缺项 |

---

## 字段级决策表（10 项）

| 字段 | UI 分组 | 提交必填 | AI 抽取 | 建议人工核对 | Gate A（维度） |
|------|---------|----------|---------|--------------|----------------|
| `project_name` | 项目信息 | **是** | try | 否 | — |
| `investment_destination` | 项目信息 | 否 | try | 否 | 外资准入、行业准入 |
| `investment_structure` | 项目信息 | **是** | try | **是** | 外资准入 |
| `funding_source` | 项目信息 | 否 | try | **是** | 外资准入、税制 |
| `project_content_scale` | 项目信息 | 否 | try | 否 | 行业准入、税制 |
| `description` | 业务描述与风险 | **是** | try | **是** | 全部维度 |
| `known_risks` | 业务描述与风险 | 否 | try | **是** | — |
| `board_date` | 关键时间线 | 否 | try | 否 | — |
| `start_date` | 关键时间线 | 否 | try | 否 | — |
| `production_date` | 关键时间线 | 否 | try | 否 | — |

---

## 明确仍不属于 intake 表的内容

- 完整股权结构图、审计报告、合同附件包（原文件已归档，法务可下载）
- 法务风险结论、匹配度评分
- 场景路由字段（国家/州/城市/行业/动作类型，系统默认）

---

## 配置文件

- 规则：`backend/app/rules/brazil_new_energy.json`
- 抽取：`backend/app/services/document_extractor.py`
- Gate A：`backend/app/services/material_review_service.py`
