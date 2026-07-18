# 实验①：圣保罗州法规元数据覆盖率 v1

## 结论

预注册阈值为 `legislationChanges` 覆盖率不低于 70%。2026-07-17 对 30 条冻结样本的实测结果为：LexML URN 可解析 `30/30`，`legislationChanges` 字段可见 `0/30`，LexML 页面可识别的整合/多时点文本入口 `0/30`。因此 **Citator v1 不宣称支持圣保罗州修订沿革自动追踪**；州级内容必须从 AL-SP 官方关系页人工核对修订记录，并由巴西律师复核。该决定不是事后选择，阈值与分支动作已在抓取前写入目标清单。

## 样本与方法

- 分母：Decreto 8.468/1976 本身，加其 AL-SP 官方关系页按页面顺序出现的前 29 条不重复州级法规，共 30 条。
- 对每条法规按 LexML URN 规范构造 `urn:lex:br;sao.paulo:estadual:<type>:<date>;<number>`，请求 LexML 官方解析器。
- “有修订关系元数据”只在响应中出现 `legislationChanges` 时记为 1；“有整合文本”只在响应中出现 Texto Atualizado、Multivigente、Texto Consolidado 或 `legislationConsolidates` 时记为 1。
- HTTP 失败、空正文、超限正文均记为实验未完成并阻止出结论，不按 0 计入。
- 每条响应只保存 HTTP 状态、判定和 SHA-256，不把远端页面全文复制进仓库。

LexML 的官方规范说明解析服务从 URN 列出文档出现位置；其元数据采集架构使用 OAI-PMH，而 XML Schema 的生命周期/事件区可以表达文档变化。这些能力说明字段“可表达”，不等于本样本中字段“实际可得”。参考：[URN 解析服务规范](https://projeto.lexml.gov.br/documentacao/Parte-5-Servico-de-Resolucao-de-URN.pdf)、[元数据采集规范](https://projeto.lexml.gov.br/documentacao/Parte-4-Coleta-de-Metadados.pdf)、[LexML XML Schema](https://projeto.lexml.gov.br/documentacao/Parte-3-XML-Schema.pdf)。

## 冻结证据

- [预注册目标清单](../../backend/evals/state_metadata_targets_v1.json)，SHA-256 `78f0d405f8639e454d6aa19b1cc4237b0b4bd592f4098e3bcfaf310a1823ab3e`
- [逐条结果](../../backend/evals/state_metadata_coverage_v1.json)，SHA-256 `3361bd0e6bd716e0e988e53fecd5d10e63d85e2d6c7af42afba2e2270d19dd35`
- [可复现实验脚本](../../backend/scripts/run_state_metadata_coverage.py)
- AL-SP 官方分母页：[Decreto 8.468/1976 关系页](https://www.al.sp.gov.br/norma/62153)

## 不可外推的内容

本实验不证明 AL-SP 没有修订数据，也不证明任何法规当前有效；它只证明 2026-07-17 时，预注册的 30 条样本在 LexML URN 解析页面中没有暴露本实验寻找的两个结构化信号。AL-SP 关系页本身列有变更信息，因此运行时保留官方页面人工核对路径。重新抓取、改变分母或改变检测标记都必须生成新实验版本，不能覆盖 v1。
