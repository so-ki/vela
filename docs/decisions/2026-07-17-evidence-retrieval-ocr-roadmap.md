# Evidence、跨语检索与 OCR 技术路线决定

日期：2026-07-17
状态：`accepted-for-experiment`（不是生产选型完成）

## 决定

保留现有“冻结能力包制品 → 确定性检索 → grounding → 人工复核”主链，不引入新的通用 Agent 框架。新增能力按以下顺序验证：

1. 先把 Claim、Evidence、Coverage 与 Answerability 做成可审计数据对象和 fail-closed 门禁。
2. 再用同一份中葡西人工小样本对多语种 embedding 做 A/B，不凭公开榜单直接替换正式检索。
3. 扫描件进入独立 OCR 路径，保留页码、bbox、置信度、抽取器版本和原图/文本哈希；低置信字段必须人工确认。
4. 法规监测只创建候选版本和差异，不得自动覆盖 active corpus。

## Claim/Evidence 评测

- 参考 [RAGChecker](https://github.com/amazon-science/RAGChecker) 的 claim-level entailment、retriever claim recall 和 faithfulness 指标；只用于离线诊断/CI，不能充当法律真值裁判。项目许可证为 Apache-2.0。
- 参考 [RefChecker](https://github.com/amazon-science/RefChecker) 的 claim extractor → checker → aggregation 分层，但 Vela 的正式 verdict 必须由确定性证据条件和人工复核决定。项目许可证为 Apache-2.0。
- 三案例内部回归集采用 [LegalBench-RAG](https://arxiv.org/abs/2408.10343) 强调的“最小、精确、可定位法律片段”方法，记录 Recall@5、nDCG@10、MRR、零命中率和定位完整率。

## 多语种检索候选

第一轮只做本地离线 A/B：

| 候选 | 角色 | 采用条件 |
|---|---|---|
| [BGE-M3 / FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | dense/sparse/multi-vector 候选；MIT | 在中→葡、中→西、葡/西→中 gold query 上超过当前关键词基线，且延迟/内存满足私有部署预算 |
| [Qwen3-Embedding 0.6B](https://github.com/QwenLM/Qwen3-Embedding) | embedding/reranker 对照；官方列明中文、葡语、西语等 100+ 语言 | 单独核对模型卡许可证与交付条款；达到相同评测门槛后再决定 |
| [pgvector](https://github.com/pgvector/pgvector) | PostgreSQL 内向量存储、HNSW 与全文检索混合 | 只在 A/B 证明语义检索有增益后启用；先用 RRF 融合，不能把 cosine 相似度宣传为法律置信度 |

不把葡语/西语官方原文先翻译成中文再索引；翻译只能作为查询扩展，正式引用始终回到原文、页码/条款和快照哈希。

## PDF/OCR 候选

| 路径 | 决定 |
|---|---|
| 原生文字 PDF | 保留原字符层与当前安全检查，同时增加页码/charspan provenance |
| 扫描 PDF/图片 | 以 [Docling](https://github.com/docling-project/docling)（MIT，支持本地/隔离运行、版面与 OCR）配合 [Tesseract](https://github.com/tesseract-ocr/tesseract)（Apache-2.0，可输出 hOCR/TSV/ALTO）做隔离实验 |
| 质量门 | 统计 CER、条文号/日期/金额/否定词关键锚点遗漏率、页码/bbox 回溯率；不能再用“成功抽到文本”作为通过 |

每个 OCR block 至少保存：原文件 SHA-256、页码、bbox、charspan、抽取器及版本、OCR 语言、置信度、原图裁片哈希、文本哈希和人工确认状态。

## 明确排除

- 不抓取 Jusbrasil 网页，也不以第三方索引替代官方来源；需要时走正式授权/API 合同。
- 不让 LLM 或相似度分数把来源升级为 `expert_verified`。
- 不引入无法保留页码/条款/哈希定位的摘要型 OCR/RAG 结果。
- 不因某开源库“可安装”就默认可闭源商用；每个模型、库及其转依赖在锁定版本时重新完成许可证和安全审查。

## 实验退出条件

只有同时满足以下条件，候选才能进入生产设计：

1. 在冻结、人工复核的中葡西测试集上超过当前关键词基线；
2. 零命中和错误高置信命中均有单独报告；
3. 每个命中可回溯到不可变源版本、精确定位和哈希；
4. 私有部署资源、许可证、SBOM 和漏洞门通过；
5. 法律专家确认评测问题和 gold evidence，而不是只确认模型分数。
