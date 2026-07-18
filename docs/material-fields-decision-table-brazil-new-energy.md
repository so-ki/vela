# 字段决策表 · 巴西 · 新能源制造 · 绿地设厂

> 唯一正式 Capability Pack：`brazil_new_energy_greenfield`
> 绑定规则制品：`brazil_new_energy.json` v2.9
> 国家 / 行业 / 动作：巴西 / 新能源制造 / 绿地设厂
> 不覆盖：并购、矿产、研发机构、既有工厂扩建及其他国家或行业
> 对齐：企业境外投资材料中**业务侧应确认的项目事实**

---

## 规则包级策略

| 项 | 决策 |
|----|------|
| 产品定位 | C 混合：固定 intake + 法务维度动态必填 |
| 业务动作 | 上传方案 → AI 抽取 → 核对事实 → 查看 Capability Pack → 知情确认 → 提交 |
| 业务责任 | 确认方案事实真实、完整，并知晓当前受控试点工程边界；不判断法律适用性 |
| 提交必填 | `project_name`、`investment_structure`、`description`（3 项） |
| 建议核对字段 | `description`、`investment_structure`、`funding_source`、`known_risks` |
| 提交结果 | 仅创建 `pending_scope` 与 proposed scope；法务确认前不生成 |
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
- Capability Pack 路由字段不由业务静默提交：页面公开当前支持边界，后端提出 country/industry/action，法务确认后写入 snapshot；州/城市仍按材料作为项目事实核对

---

## 配置文件

- 规则：`backend/app/rules/brazil_new_energy.json`
- 抽取：`backend/app/services/document_extractor.py`
- Gate A：`backend/app/services/material_review_service.py`
