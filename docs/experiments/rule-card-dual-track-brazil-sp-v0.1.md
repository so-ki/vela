# 实验②：圣保罗州环境许可规则卡双轨抽取 v0.1

## 结论

已形成 **exactly 10 张**、可机器校验的历史 provisional 规则卡。2026-07-17 的后续时点核验确认：其中引用 Decreto nº 8.468/1976 arts. 57–58 的法条轨没有整合 Decreto 47.397/2002、62.973/2017、63.119/2017 与 69.120/2024 的改写、增补和废止，因此整批卡片**仅保留作抽取方法审计，已作废为现行法证据，不得进入检索或生产规则**。每张卡都分别保留：

- `statute_forward`：从 AL-SP 官方法规条文向前拆解许可触发、阶段和所需事实；
- `form_reverse`：从 CETESB 官方申请指引与服务入口反推在线流程实际暴露的身份、既有许可、企业和物业字段。

窄样本显示两条轨道互为补充：法条轨更清楚地描述“为什么进入许可判断”，表单轨额外暴露“提交时必须区分什么”。这只支持继续开展跨州、跨主题实验，**不证明规则抽取方法已经具有巴西全国通用性，也不构成巴西法律意见**。全部卡片保持 `certification_status=provisional`、`production_ready=false`、`runtime_integration=false`，必须由巴西执业律师逐项复核后，才可另行评估是否进入生产规则。

## 冻结证据与验证

- [10 张规则卡数据](../../backend/evals/rule_cards/brazil_sp_environment_dual_track_v0.1.json)
- [JSON Schema Draft 2020-12](../../backend/evals/rule_cards/rule_card_experiment.schema.json)
- [无新增依赖的结构与交叉引用验证器](../../backend/evals/rule_cards/validate_rule_cards.py)
- 正向与篡改反向测试保留在开发树 `backend/tests/test_rule_card_experiment.py`（发布包不携带该开发测试源码；唯一例外是发布自验所需的前端 production smoke spec）

在仓库 `backend` 目录运行：

```bash
python evals/rule_cards/validate_rule_cards.py
pytest -q tests/test_rule_card_experiment.py
```

验证器不仅检查结构，还会拒绝：非官方域名、来源 URL 与登记表不一致、被明确排除的来源、重复/缺号规则、轨道引用未登记事实、伪造工时、非 provisional 状态，以及差异类型汇总与卡片不一致。

## 来源边界

截至 2026-07-17，本实验只把下列可直接核验的官方页面用于规则主张：

1. AL-SP 官方整合文本：[Lei nº 997/1976](https://www.al.sp.gov.br/repositorio/legislacao/lei/1976/compilacao-lei-997-31.05.1976.html)，使用 Art. 5º、§§ 1º–4º 与 Art. 6º。
2. 历史实验输入（现行法证据已作废）：AL-SP 的 [Decreto nº 8.468/1976 原始页面](https://www.al.sp.gov.br/repositorio/legislacao/decreto/1976/decreto-8468-08.09.1976.html)曾用于 Art. 57, II 与 Art. 58, II–IV；后续核验发现未整合 [Decreto 47.397/2002](https://www.al.sp.gov.br/repositorio/legislacao/decreto/2002/decreto-47397-04.12.2002.html)、[62.973/2017](https://www.al.sp.gov.br/repositorio/legislacao/decreto/2017/decreto-62973-28.11.2017.html)、[63.119/2017](https://www.al.sp.gov.br/repositorio/legislacao/decreto/2017/decreto-63119-27.12.2017.html)及 [69.120/2024](https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-69120-09.12.2024.html)，不得再据此作现行结论。
3. CETESB 官方指引：[Dúvidas sobre o Portal de Licenciamento Ambiental — PLA](https://cetesb.sp.gov.br/licenciamentoambiental/duvidas-sobre-o-portal-de-licenciamento-ambiental-pla/)，只采用 FAQ 可直接核验的账号、CNPJ、既有许可证、MCE 校验、CCIR、matrícula/transcrição、占有文件、地址和坐标字段。
4. CETESB 官方服务入口：[e-CETESB Portal de Serviços](https://e.cetesb.sp.gov.br/portal-servicos-frontend/)，只证明在线服务入口存在，不反推页面未公开的字段或许可结论。

没有把搜索摘要当作证据。历史链接 `Industrias_LI.pdf` 在核验日无法稳定直达原文件，因此明确列入 `excluded_sources`，没有据此声称存在一份适用于所有新能源制造项目的通用文件清单。热电联产专项页面也因适用范围过窄被排除。动态门户或 FAQ 没有精确列出的字段一律保留为开放问题，不臆造 URL、文件名或材料要求。

## 10 张卡与双轨差异

| 规则卡 | 主题 | 差异类型 | 双轨新增信息 |
|---|---|---|---|
| RC-001 | 工业活动初步分类 | `scope_to_form_fields` | 法条给出工业活动范围；表单暴露 MCE 及当前校验状态 |
| RC-002 | 新建/重建/改造建筑 | `scope_to_form_fields` | 法条给出工程触发；表单增加物业地址与条件性坐标 |
| RC-003 | 既有建筑内安装污染源 | `scope_to_form_fields` | 法条给出安装行为；表单增加企业与物业绑定 |
| RC-004 | 扩建或变更 | `form_adds_branching_logic` | 表单揭示变化可能改变简化续证路径 |
| RC-005 | 许可阶段选择 | `form_adds_branching_logic` | 表单用历史许可证类型和编号决定在线分支 |
| RC-006 | 提交人身份 | `form_adds_identity_control` | 表单区分实际填报人和 interested party 联系方式 |
| RC-007 | 企业 CNPJ | `form_adds_identity_control` | 表单增加 CNPJ 唯一性和分支机构识别 |
| RC-008 | 城乡属性与 CCIR | `form_adds_property_evidence` | 表单增加农村 CCIR、面积及分类证据 |
| RC-009 | 多份不动产登记 | `form_adds_property_evidence` | 表单要求逐项记录 matrícula/transcrição |
| RC-010 | 无登记时的占有文件 | `form_adds_property_evidence` | 表单出现条件性占有文件分支，但不证明权利有效性 |

汇总计数为 `3 + 2 + 2 + 3 = 10`。差异分类仍是 provisional taxonomy；换一个州、行业或许可主题后可能需要新增、合并或重命名类别。

## 工时记录

本轮整理没有在每张卡、每条轨道开始时启动同期计时器，无法可靠拆分检索、阅读、翻译、核对和录入耗时。为避免用回忆制造精度，实验级与卡片级的所有分钟字段均为 `null`，并附 `effort_unavailable_reason`。因此本实验不能回答哪条轨道更快或成本更低。

后续若比较效率，应先冻结样本和停止条件，再由不同人员独立执行两条轨道并同期计时；返工、律师复核和门户不可用时间应单列，不得回填估算值。

## 进入生产前的必要复核

这批卡片不能直接接入现有 runtime。至少还需巴西执业律师完成：

1. 复核引用文本在目标日期的现行效力、修订关系与精确定位；
2. 确认新能源制造具体活动、项目阶段和地点是否落入各触发条款；
3. 检查条文与 CETESB 当前动态门户之间是否存在遗漏的例外、专项清单或地方要求；
4. 逐项确认事实字段、后果、红旗响应和开放问题，记录签名、日期与证据版本；
5. 通过第二个能力包和至少一个不同州的重复实验后，再判断抽取结构是否可迁移。

在以上条件完成前，产品只能把本文件作为方法实验和人工复核清单展示，不得把卡片输出包装为法律结论、许可保证或“已验证规则”。
