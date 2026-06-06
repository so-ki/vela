# Vela 协查材料字段定义方法论

> 适用对象：产品、法务、规则库维护者  
> 版本：v1.1 · 对齐业务「只上传方案」、法务按维度定需求；协查法域 **巴西（拉美首发）**

---

## 1. 核心原则

| 角色 | 职责 |
|------|------|
| **业务端** | 上传巴西投资方案文件；在材料核对页确认 AI 抽取结果（尤其业务描述） |
| **法务端** | 选定协查维度；按维度定义「提交表缺哪些字段应退回」；确认范围并生成清单 |
| **系统** | 按**协查法域规则包**固定抽取 schema；AI 只抽文档中有的内容；原文件归档 |

**定位**：协查材料表 = **场景 intake（C 混合模式）**

- **固定层**：该协查法域下，系统会尝试从方案中抽取的一组结构化事实
- **动态层**：法务勾选维度后，Gate A 按 `dimension_field_requirements` 检查缺项

**不属于本表**：完整 DD 附件、证照扫描、法务结论、场景路由字段（国家/行业等，后台默认）。

---

## 2. 何时需要新建/调整一套字段模板

每增加一个 **协查法域或场景类型**（例如「巴西 · 投资协查 · 新能源」→「巴西 · 矿业 · 并购」），应新建或复制一个 **规则包 JSON**，而不是在一个大表单里堆字段。

场景类型 = `国家 × 行业 × 动作类型`（可再细分子行业规则）。

---

## 3. 字段定义六步流程

### Step 1 — 锁定协查法域与规则包边界

- 写清 `pack.id / pack.name / pack.focus / pack.region / pack.primary_country`
- 明确 jurisdiction、默认 `industry`、`action_type`
- 列出本场景**不会**覆盖的情况（如并购、特许经营）

### Step 2 — 法务按协查维度列「需要哪些事实」

对每一个合规维度（劳工 / 外资 / 税制 / 行业准入 …）问：

> 要生成可靠核查清单、并在 Gate A 判断材料是否够用，**必须能从提交表上读到哪些事实？**

产出：`dimension_field_requirements`（维度 → 字段 key 列表）。

**这是硬要求（Gate C）**：法务选维度后，缺项必须能退回业务。

### Step 3 — 确定「提交时永远必填」字段

与维度无关、但任何提交都不能空的字段，写入 `always_required: true`。

典型：`project_name`、`investment_structure`、`description`（本规则包当前策略）。

### Step 4 — 确定 AI 抽取 schema

在 `material_fields` 中列出系统会尝试从文档抽取的 key：

| 策略 | 含义 | 示例 |
|------|------|------|
| `extract: try` | 文档有则抽，无则留空 | 雇员、厂房、产能、时间线 |
| `extract: try` + 建议核对 | 可 AI 预填，提交前建议人工核对 | 业务描述、投资结构 |
| `submit_required` | 抽不到也必须手填后才能提交 | 项目名称、投资结构、业务描述 |
| `gate_a: dimension` | 仅法务选相关维度后必填 | 雇员、厂房、产能 |
| `gate_a: none` | 暂不参与 Gate A | 时间线、备注 |

**禁止**：AI 编造文档未出现的数字或结构。

### Step 5 — 对照核查清单做「加分项」校验（非 Gate 硬门槛）

- **A 触发清单**：字段/描述中的词是否触发 `checklist_items.triggers`？缺字段是否导致清单漏项？
- **B 填充上下文**：字段是否让 AI/法务理解场景更充分？

无定量标准时，用 **BYD 类投资方案 + 法务经验** 试跑：清单是否覆盖主风险、无关项是否过多。

### Step 6 — 写入规则库并同步三处

| 位置 | 内容 |
|------|------|
| `{pack}.json` | `ui_groups`、`material_fields`、`dimension_field_requirements`、`material_intake_policy` |
| 抽取 prompt | `document_extractor.py` 中 schema 与 `material_fields` 一致 |
| 前端 | 从 catalog 读字段；业务端以**上传 + 材料核对页** 为主 |

---

## 4. 决策检查清单（发布前）

- [ ] 业务是否只需上传方案即可走通（不需理解「该填哪些字段」）？
- [ ] 提交时必填是否仅限 `submit_always_required`，不过度要求雇员/厂房等？
- [ ] 法务每个维度是否都有对应的 `dimension_field_requirements`？
- [ ] Gate A 缺项能否精确到字段并退回？
- [ ] 原方案文件是否归档并可下载回看？
- [ ] 换协查法域时是否用**新规则包**而非改一个全局大表？

---

## 5. 新协查法域规则包模板（文件结构）

```json
{
  "pack": {
    "id": "...",
    "name": "...",
    "version": "1.0",
    "region": "latin_america",
    "primary_country": "brazil",
    "focus": "..."
  },
  "material_intake_policy": {
    "philosophy": "upload_first",
    "archive_source_files": true,
    "submit_always_required": ["project_name", "investment_structure", "description"],
    "user_confirm_fields": ["description"],
    "gate_a_by": "dimension_field_requirements"
  },
  "ui_groups": [ ... ],
  "material_fields": [ { "key": "...", "policies": { ... } } ],
  "dimension_field_requirements": { "labor": [...], ... },
  "checklist_items": [ ... ]
}
```

---

## 6. 与「业务不用想上传什么」的关系

业务上传的是 **「巴西投资方案类文档」**（txt/md/docx/pdf），不是按字段分类上传。

**「应该有哪些结构化内容」由法务在规则包中预先定义**；系统从文档中尽量抽取；抽不到的：

- 提交阶段：仅 `always_required` / 用户确认项阻塞
- Gate A 阶段：法务选维度后，按维度要求补全

因此：**页面字段列表 = 法务定义的 intake schema 的展示**，不是业务事先要决定的清单。
