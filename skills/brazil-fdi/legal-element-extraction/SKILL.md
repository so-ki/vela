---
name: legal-element-extraction
description: 从投资方案材料抽取协查核对表事实字段（A1）；可选 LLM，带 fact grounding
compatibility: Vela D1 · A1 · document_extractor · 支持 txt/md/docx/pdf
---

# 法律要素抽取（A1 · Legal Element Extraction）

## 用途

业务上传方案或填写表单后，将非结构化文本映射到 **协查材料核对表** 字段，供 Gate A 与清单生成使用。抽取的是**项目事实**，不是法律结论。

## 步骤

1. **文件解析**：支持 `.txt`、`.md`、`.docx`、`.pdf`；合并多文件文本（单文件上限 200MB）。
2. **规则预筛（始终执行）**：
   - 按关键词启发式识别 `compliance_dimensions` 建议；
   - 从标签行（如「项目名称：」）提取结构化片段。
3. **LLM 抽取（可选）**：
   - 任务键 `extract`；未配置 LLM 时跳过，保留表单与规则结果。
   - 模型须输出 JSON，包含核对表各字段及 `facts[]`（field / value / source_snippet）。
4. **Grounding 校验**：每条 `source_snippet`（≤40 字）须在源文档中可匹配，否则丢弃该 fact。
5. **写入 payload**：结果存于 `document_extract`（含 `merged`、归档文件列表、建议维度）。

## 核对表字段

| 字段 | 说明 |
|------|------|
| `project_name` | 正式项目名称 |
| `investment_destination` | 国家/州/城市 |
| `investment_structure` | 投资主体与股权结构 |
| `funding_source` | 资金来源 |
| `project_content_scale` | 建设内容一句话 |
| `facility_notes` | 面积、产能或投资规模 |
| `capacity_notes` | 产能说明 |
| `employee_count` | 雇员人数（整数） |
| `description` | 3–6 句业务描述 |
| `known_risks` | 文档明示的风险关注 |
| `board_date` / `start_date` / `production_date` | 日期（YYYY-MM-DD） |
| `compliance_dimensions` | 五维度子集 |

## 输入

| 名称 | 类型 | 必填 |
|------|------|------|
| 场景表单字段 | string / number | 至少描述或上传文件 |
| `uploads` | 文件列表 | 可选 |
| `user_id` | int | 用于读取 LLM 设置（任务 `extract`） |

## 输出

| 名称 | 类型 | 说明 |
|------|------|------|
| `document_extract.merged` | object | 各字段最终值 |
| `document_extract.facts` | array | 带来源锚点的事实列表 |
| `document_extract.compliance_dimensions` | string[] | AI 建议维度（仅供参考） |
| `document_extract.archived_files` | array | 归档文件名与存储路径 |

## 硬性约束

- **不得编造**法条、监管结论或未在文档出现的数字。
- 多案例文档只抽取**一个**案例正文，禁止拼接「案例一/二/三」标题。
- `compliance_dimensions` 只能从五维枚举中选取。
- API Key 保存在用户偏好或服务端环境变量，**不得写入本 Skill 文件**。

## 法律免责声明

抽取结果仅供协查材料核对与范围讨论，**不构成对投资方案合规性的判断**。字段遗漏或误读须由业务与法务人工核实。
