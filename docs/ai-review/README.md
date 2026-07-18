# Vela 多模型争议审查包

本目录把产品目标、当前事实、工程证据和未完成项固定成一套可复核输入，供 Claude Code、Codex 或其他代码审查模型独立质询。聊天记录不是验收证据；代码、迁移、测试、冻结制品和具名外部签核才是。

## 一句话目标

Vela 是“薄平台机制层 + 场景化 Capability Pack”的跨境法律协查系统。当前唯一承诺范围是**巴西圣保罗州新能源制造绿地设厂的单客户私有化受控试点 RC**；它不是全拉美 GA 产品，也不构成正式法律意见。

建设顺序是：先把第一个垂直做对，再由第二、第三个真实能力包验证抽象。对外可以讲平台愿景；工程上不得把巴西特有的法源、行政结构或规则伪装成通用能力。

## 审查前按顺序阅读

1. [`TARGET_PRODUCT_STATE.md`](./TARGET_PRODUCT_STATE.md)：目标、非目标、不可妥协约束和当前差距。
2. [`../REQUIREMENTS_TRACEABILITY.md`](../REQUIREMENTS_TRACEABILITY.md)：逐项需求、完成判据、证据和外部阻塞。
3. [`../../API.md`](../../API.md)：正式工作流和机制层 API。
4. [`../RELEASE_CANDIDATE.md`](../RELEASE_CANDIDATE.md)：上一冻结 RC 的适用边界；审查新分支时不得把其中旧基线测试数当成新分支证据。
5. [`../decisions/2026-07-17-evidence-retrieval-ocr-roadmap.md`](../decisions/2026-07-17-evidence-retrieval-ocr-roadmap.md)：GitHub/论文技术候选、采用门槛与排除项。
6. [`../CUSTOMER_DELIVERY_ASSURANCE.md`](../CUSTOMER_DELIVERY_ASSURANCE.md)：真实客户发布门、签名边界与外部证据清单。
7. [`CLAUDE_CODE_ARGUE_PROMPT.md`](./CLAUDE_CODE_ARGUE_PROMPT.md)：可直接复制给 Claude Code 的独立质询任务。
8. [`../SELF_RED_TEAM_2026-07-18.md`](../SELF_RED_TEAM_2026-07-18.md)：本轮内部最强反对意见、复现、裁决和仍不可由代码解决的边界。

## 当前新分支已经实现的工程增量

- 法源披露按冻结命中动态生成，不再声称未实际返回的 LexML/STF/STJ 来源。
- Word/PDF 导出携带标识、定位、效力时点、审核状态、核验范围和 HTTPS 官方链接；非 HTTPS 关系不会写入 DOCX。
- 六状态材料账本、持久事实记录、Claim Compiler、人工确认和 CoverageProof 已形成受审计的后端机制层。
- 法规候选版本和结构化差异已经独立持久化；只有法务可推进 `candidate → reviewed → active/rejected`，且 `active` 只表示 registry-approved snapshot，不自动改 Capability Pack。
- “删除巴西”测试在隔离目录只加载非真实 fixture，可跑生成、确定性命中、零命中拒答和简报流程；核心数据库模型不再默认填入 Brazil。
- GitHub/论文技术路线已形成 ADR，但 BGE-M3、Qwen3-Embedding、pgvector、Docling、Tesseract、RAGChecker 和 RefChecker **尚未被宣称为生产实现**。
- Answerability Gate 已在所有最终下载前重算 Claim/Coverage；`/brief` 保持草稿预览。
- OAB 凭证、两律师 rules/corpus/gold 认证、精确 bytes 冻结、ITI 签名核验、客户 UAT、production provenance 与限时 release 已形成统一代码门；没有真实外部证据时始终不可交付。
- 场景签署已绑定 `review.finalized_by_id`；最终 release admin 与全部证据核验 actor 强制四眼分离；签名批准/发布前重验 exact bytes；schema 1.1 checkpoint 覆盖全部关键证据。
- 机制层业务/法务 Vue 工作台已实现，真实角色 UAT 尚未执行。

以上内容以当前分支代码和测试为准。远端 Draft PR 的 CI 未绿色前，不得写成“新 RC 已放行”。

## 当前必须被攻击的缺口

1. 内部红队已修复非主审签署、同 admin 自核验后放行、签名批准前 bytes 替换和弱 release hash；仍需第二个独立模型从零复现，并继续攻击并发 partial unique 与撤回传播。
2. 机制层界面工程测试已通过，业务/法务/律师/管理员/客户的真实 UAT 仍未验收。
3. 法规版本模块没有官方源调度器、唯一 current 指针、自动 corpus 发布或回滚；这是一条有意隔离的候选登记链。
4. 巴西法律内容仍是 `provisional`，`expert_verified=0`；工程测试不能替代巴西执业律师核验。
5. OCR、多语 embedding 和 RAG 评测目前是实验路线，不是已上线能力。
6. 第二法域、第二行业、多租户、计费、OA 连接器、生产 SSO、WORM 和企业 AV/CDR 均未完成或依赖外部条件。

审查者若没有主动检查这些缺口，审查即不合格。

## 争议流程

1. **只读红队：** 审查者先不改代码，输出带文件/行号、复现命令和严重度的反对意见。
2. **逐条答辩：** 维护者只能用代码、测试、制品哈希、官方文档或论文回应；“设计上应该可以”不算证据。
3. **裁决：** 标记为 `accept`、`reject_with_evidence`、`experiment_required` 或 `blocked_external`。
4. **再修改：** 只有已接受问题、实验结果或赛事硬要求触发代码变更。
5. **重新验收：** 后端全量、前端组件/构建、Alembic 升降级与 drift、发布边界和远端 CI 全部重新执行。

不同模型的意见不能按票数决定；可复现证据优先。
