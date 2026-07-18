# Vela Evidence Ledger

每项证据字段:Evidence ID、claim、文件与精确行号、命令、原始结果摘要、提交 SHA、是否已复现、限制和不确定性。
无证据不得断言;`blocked_external` 不得描述为已完成。

---

## EV-0001

- **claim**: 远端目标分支 `origin/codex/vela-release-hardening` 精确指向基线 `65f0b398f94af72680f8c1139aa59f7df6b88d71`。
- **文件与精确行号**: N/A(Git 元数据)
- **命令**: `git fetch origin && git rev-parse origin/codex/vela-release-hardening`
- **原始结果摘要**: `65f0b398f94af72680f8c1139aa59f7df6b88d71`
- **提交 SHA**: 65f0b398f94af72680f8c1139aa59f7df6b88d71
- **是否已复现**: 是(单次会话内 fetch 后核验)
- **限制和不确定性**: 快照时间 2026-07-18;远端后续可能移动,再次开工前需重新核验。

## EV-0002

- **claim**: 网页端自动分支 `claude/gracious-brahmagupta-bbg2dw` 初始位于 `origin/main`(`36074bad`),为基线祖先,无独有提交;重置到基线不丢失内容。
- **文件与精确行号**: N/A(Git 元数据)
- **命令**: `git merge-base --is-ancestor HEAD 65f0b398... ; git log --oneline 65f0b398...HEAD ; git status --short`
- **原始结果摘要**: is-ancestor=yes;`65f0b398..HEAD` 日志为空;工作树干净。`HEAD..65f0b398` 含 20 个提交、287 文件、+42468/-2764 行。
- **提交 SHA**: 36074bad → 65f0b398
- **是否已复现**: 是
- **限制和不确定性**: 无。

## EV-0003

- **claim**: 基线上 `AGENTS.md`、`CLAUDE.md`、`docs/ai-review/ACTIVE_HANDOFF.md`、`DECISION_LOG.md`、`EVIDENCE_LEDGER.md` 均不存在;`docs/ai-review/` 仅含 `CLAUDE_CODE_ARGUE_PROMPT.md`、`README.md`、`TARGET_PRODUCT_STATE.md`。
- **文件与精确行号**: 仓库根目录与 `docs/ai-review/`
- **命令**: `ls docs/ai-review; ls -la AGENTS.md CLAUDE.md`
- **原始结果摘要**: `ls` 对 AGENTS.md/CLAUDE.md 返回 No such file or directory;目录列表见命令输出。
- **提交 SHA**: 65f0b398
- **是否已复现**: 是
- **限制和不确定性**: 无。

## EV-0004

- **claim**: 平台核心的交付认证门硬编码巴西法域:非 brazil jurisdiction 无法完成法律内容认证/release。
- **文件与精确行号**: backend/app/services/delivery_assurance_service.py:536-541(OAB 官方域名限制)、:586、:618-619(非巴西法域 raise)、:1028、:1101-1102
- **命令**: 子代理只读检索(grep + Read)
- **原始结果摘要**: `_jurisdiction_matches("brazil", …)` 与 `_require_brazil_official_registry_url` 为平台服务内字面量;:619 提示"巴西法律内容认证必须由巴西法域律师完成"。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认;未运行代码。
- **限制和不确定性**: 行号以基线为准;未验证运行时行为。

## EV-0005

- **claim**: 机制层模型与 Pack 契约国家无关:scenario 国家字段为纯字符串无默认,manifest 携带 country/state/industry/action/routing/retrieval/output 并做 SHA-256 完整性校验;registry 无默认 Pack 回退。
- **文件与精确行号**: backend/app/models/scenario.py:29-40;backend/app/models/mechanism.py(FactRecord/ClaimRecord/CoverageTask/CoverageProof 等);backend/app/capability_packs/schemas.py:132-232;loader.py:119-156;registry.py:35,88-92
- **命令**: 子代理只读检索
- **原始结果摘要**: 模型层无国家枚举/默认;loader 重算 semantic_hash 并校验 rules/corpus 内容哈希;get_default_pack_id 要求恰好一个 active pack。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认。
- **限制和不确定性**: 单 active pack 假设意味着激活第二个 Pack 会改变默认解析行为。

## EV-0006

- **claim**: "删除巴西"测试真实存在且禁止读取正式巴西制品,证明 checklist→检索→拒答→brief 切片可由虚构 Pack 跑通;但未覆盖抽取、意图解析、维度门、Claim/Coverage 编译与交付认证门。
- **文件与精确行号**: backend/tests/test_country_independent_fixture_flow.py:35-39,73-98,101-257;backend/app/capability_packs/fixtures/test_fixture_pack/manifest.json
- **命令**: 子代理只读检索
- **原始结果摘要**: monkeypatch Path.read_bytes/open 拦截巴西制品读取;端到端断言含零命中拒答(FIX-MISS-001)。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认;本轮未运行该测试。
- **限制和不确定性**: 测试通过与否需在本基线实际运行后登记。

## EV-0007

- **claim**: 规则适用为对场景自身文本的通用关键词评分,450/1000 从未作为数值门槛;Campinas 为按 city 字段键控的合法城市 overlay;BYD 演示资产隔离于正式链路。
- **文件与精确行号**: backend/app/services/rule_engine.py:166-188,201-216,237-261,295-310,349-366;backend/app/rules/brazil_new_energy.json:552-571;backend/app/api/scenarios.py:647-662(is_demo 隔离,弃用端点);frontend/src/views/DashboardView.vue:790-812
- **命令**: 子代理全库 token 检索(BYD/比亚迪/Campinas/450/1000/demo/seed/fixture)
- **原始结果摘要**: 无 `if capacity >= …` 类分支;触发词为 OR 关键词列表;demo 场景 is_demo=True 不能进入确认/生成链路。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认。
- **限制和不确定性**: 四合成案例为静态推演,未动态执行。

## EV-0008

- **claim**: 存在低危 BYD 污染:抽取提示词 few-shot 含 BYD 精确数字;规则 JSON 触发词含 450/坎皮纳斯/比亚迪/Campinas;legacy 请求 schema 默认 sao_paulo/campinas;前端 placeholder 含 BYD 文案。
- **文件与精确行号**: backend/app/services/document_extractor.py:41-93(:51,:57-58,:92);backend/app/rules/brazil_new_energy.json:152,178,214,280,298,361,370,512,522;backend/app/schemas/scenario.py:86-89;frontend/src/views/ScenarioCreateView.vue:51-58,124,127-128
- **命令**: 子代理全库 token 检索
- **原始结果摘要**: 触发词均为 OR 列表中一项,移除不改变真实输入行为;placeholder 非表单实值;BusinessSubmitRequest 已改 Optional/None。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认。
- **限制和不确定性**: priming 风险未定量评测。

## EV-0009

- **claim**: 角色共三种(business/legal/admin);材料块账本无内容哈希;冲突检测为非阻断占位且无测试;gap_explanation LLM 为死代码;抽取器 VALID_DIMENSIONS 缺 data_compliance。
- **文件与精确行号**: backend/app/core/roles.py:9-11;backend/app/models/mechanism.py:17-46;backend/app/schemas/mechanism.py:101;backend/app/services/conflict_detection_service.py:11-40,57;backend/app/services/scenario_pipeline.py:305;backend/app/services/document_extractor.py:25
- **命令**: 子代理只读检索 + grep 调用方
- **原始结果摘要**: detect_material_conflicts 无任何测试引用;gap_explanation 生成器在 app/ 内无调用方。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认。
- **限制和不确定性**: 无。

## EV-0010

- **claim**: Scope 冻结、Pack 精确加载、事实确认、Claim Compiler、CoverageProof、复核定稿、Answerability Gate、交付证据链(OAB/双律师/UAT/部署/独立 release/撤回)均已实现、fail-closed、有测试;三个正式导出端点统一经过交付门,未发现 env/debug 绕过。
- **文件与精确行号**: backend/app/services/scenario_scope_service.py:301,360-377,474-483,591-657;capability_packs/loader.py:119-156;mechanism_service.py:154,213,249,372-465,541-613;review_service.py:289-331;answerability_gate_service.py:102,193,266,309-370;delivery_assurance_service.py:1016-2782(:1154,:2168,:2388,:2419,:2518,:2731);api/scenarios.py:123-182,1577,1625,1675
- **命令**: 子代理只读检索 + grep(DEMO/bypass/skip/ALLOW_)
- **原始结果摘要**: 见 tests/test_scenario_scope_service.py、test_mechanism_layer.py、test_review_safety.py、test_delivery_assurance*.py、test_release_safety.py;grep 未发现禁用交付链的旗标。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认;测试未在本轮运行。
- **限制和不确定性**: "无绕过"为静态检索结论,动态渗透属 WS-5。

## EV-0011

- **claim**: 法规版本链 candidate→reviewed→active/rejected 为终态状态机,无 rollback/supersede 转换、无唯一 current 指针、无调度器;activate 不改动语料(source_registry_only);registry 与语料 validity 双源不同步,废止在生成侧靠语料 validity 过滤、在交付侧靠 _active_legal_changes_after 阻断。
- **文件与精确行号**: backend/app/services/legal_source_version_service.py:33-38,127,224,246-248;backend/app/models/legal_source_version.py:17-23;backend/app/services/legal_rag.py:196,284;delivery_assurance_service.py:872-884,2234,2585
- **命令**: 子代理只读检索
- **原始结果摘要**: `_ALLOWED_TRANSITIONS` 中 active/rejected 无出边;rollback 无实现无测试。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认。
- **限制和不确定性**: 无。

## EV-0012

- **claim**: 精确制品 bytes 依赖一次冻结+逐 bytes 重算(非确定性重渲染);交付时 gold/eval 仅验证据哈希与人工断言的 regression_status,分数重算仅在 CI;浏览器 E2E 仅覆盖 business 角色。
- **文件与精确行号**: backend/app/services/export_service.py:92,220(datetime.now);delivery_assurance_service.py:1154,1173,2518;backend/app/services/legal_quality_eval.py:135,268,286;backend/scripts/run_legal_quality_gate.py;.github/workflows/ci.yml:40-43;frontend/e2e/production-smoke.spec.ts;models/delivery_assurance.py:300,353
- **命令**: 子代理只读检索
- **原始结果摘要**: 见上;GA 门要求 ≥10 expert_verified 源,当前语料 provisional 不可达。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核已确认。
- **限制和不确定性**: CI 绿色与否需以远端 Actions 具体 run 为准,本轮未查询。

## EV-0013

- **claim**: 【修正 EV-0007/0008 的定性】规则触发词具有真实行为影响,不是"纯装饰/从不门控":(1) 每个 trigger 命中 +2 分(rule_engine.py:172-175);(2) 非 always_include 条目 score=0 时返回 None 被丢弃(:180-181),全部 30 项中仅 5 项 always_include(FOR-001/002/003、TAX-001/002),其余 25 项完全依赖触发词决定是否进入 checklist;(3) 子行业不匹配条目在 generate_checklist:334 直接跳过(8 项带 sub_sectors);(4) relevance_score 是排序第三键(:387-394),触发命中改变同维度同优先级内的排序。因此 "450"(LAB-001/LAB-005 触发词)、"1000"(IND-005/IND-006 触发词,且是 electric_bus 子行业关键词)、"比亚迪"(FOR-004 触发词)、"坎皮纳斯"(LAB-003/TAX-003 触发词)都能改变 checklist 组成与排序。
- **文件与精确行号**: backend/app/services/rule_engine.py:166-188,306,334,387-394;backend/app/rules/brazil_new_energy.json(LAB-001/LAB-003/LAB-005/IND-005/IND-006/FOR-004/TAX-003 triggers;industries.new_energy.sub_sector_defs)
- **命令**: 本会话直接 Read + python json 解析(计数脚本输出:total=30、always_include=5、sub_sectors 条目=8)
- **原始结果摘要**: 见命令输出;另注意 corpus 包含 str(employee_count)(:306),子串匹配意味着 "1450" 含 "450"、"1000" 会把任意含该数字的文本误判为 electric_bus 子行业。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态代码复核(本会话亲自验证);动态执行待 experiment_required。
- **限制和不确定性**: 未运行 generate_checklist 实测;排序影响幅度未量化。

## EV-0014

- **claim**: 【confirmed bug】detect_sub_sectors 为纯子串匹配、无否定处理(rule_engine.py:250-253:`kw.lower() in normalized or kw in corpus`)。静态推演四个否定/不确定表述:"不生产电池"、"不涉及任何电池生产或包装活动"、"设备供应给电池厂,但本项目本身不生产电池"、"未说明是否生产电池"——全部含子串"电池",全部误判 battery_pack 子行业,连带使 IND-005/ENV-003/FOR-004/LAB-005/IND-008 等电池条目进入评分。另 sub_sector_defs 含泛化关键词:"系统"(energy_storage)、"1000"(electric_bus)、"回收/防火"(battery_pack),误判面不限于电池。
- **文件与精确行号**: backend/app/services/rule_engine.py:237-261;backend/app/rules/brazil_new_energy.json industries.new_energy.sub_sector_defs
- **命令**: 本会话 Read + json 解析
- **原始结果摘要**: sub_sector_defs.battery_pack.keywords=['电池','磷酸铁锂','铁锂','battery','pack','lithium','回收','防火'];energy_storage 含 '系统';electric_bus 含 '1000'。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态确认(匹配逻辑为无上下文子串包含,结论不依赖运行)。
- **限制和不确定性**: 动态复现与误判率量化待 WS-1B 实验。

## EV-0015

- **claim**: 【P0/P1】"30 项稳定研究分母"在线不成立。完整链路追踪:(1) 规则文件恰有 30 条定义;(2) 仅 5 条 always_include,25 条依赖触发词、其中 8 条再受子行业门控、且全部受法务选维过滤——真实项目生成数随文本措辞浮动,test_demo_onboarding.py:570 仅断言 >=15,无任何测试断言真实场景生成 30;(3) score=0 条目消失(rule_engine.py:180-181);(4) 未识别子行业条目消失(:334);(5) Claim 分母 = 生成后 payload sections 的去重子集(mechanism_service.py:202-211,381,464),被丢弃条目永不进入 Claim/CoverageProof 记账;(6) A-02 "30 项稳定生成" 与在线代码不一致——稳定 30 分母仅存在于离线 CI 评测(legal_quality_eval.py:228-244 直接遍历规则文件 30 项,test_legal_quality_eval.py:24 断言 30)。后果:措辞不同但法律上等价的项目获得不同的研究分母与覆盖分母,且缩减不可见。
- **文件与精确行号**: 见 claim 内逐条;另 backend/app/services/mechanism_service.py:568-607(CoverageProof denominator = claims 集合)
- **命令**: 本会话 Read + json 解析 + grep 测试断言
- **原始结果摘要**: grep 结果:唯一 "==30" 断言在 eval/ingestion(离线);在线断言为 >=15。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态确认;动态浮动幅度待四合成案例动态回归。
- **限制和不确定性**: "稳定"的产品语义(30 全量研究分母 vs 生成子集为适用子集)需产品决定,见 Unresolved。

## EV-0016

- **claim**: 无 draft 的 checklist 条目会以占位文案 `待核验事项:{title}` 存为 ClaimRecord.statement(mechanism_service.py:442-446),数据模型无 research_item/legal_claim 类型区分;缓解:此类记录因无 fact/evidence refs 必然 status=refused(:438,447),confirm_claim 仅接受 awaiting_human_confirmation(:552 附近 CAS),故不可能被确认为 supported,也无法通过 Answerability 的正向结论绑定;风险为语义混淆——研究占位以 "refused claim" 形态进入 CoverageProof.uncovered 与审计视图,把"尚未研究"与"法务拒答"混在同一状态。
- **文件与精确行号**: backend/app/services/mechanism_service.py:422-453,541-560,568-607
- **命令**: grep "待核验" + Read
- **原始结果摘要**: 全库仅 mechanism_service.py:445 一处生成该文案。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态确认。
- **限制和不确定性**: 前端如何呈现 refused 占位与真实拒答的区别未复核(属 WS-2/WS-10)。

## EV-0017

- **claim**: 外部证据核验完成:21 项候选技术/产品/模型能力全部于 2026-07-18 经实际网络访问原始来源核验(原始论文 arXiv 摘要页、官方 GitHub/LICENSE 原文、OASIS 官方标准页、lexml.gov.br 官方 URN 规范 PDF、各厂商官方文档);采用结论:生产采用 4 项(LexML URN、citator 数据模型思想、LegalRuleML 概念核对表、Tesseract),实验→生产候选 4 项(in-toto+cosign、Promptfoo、Docling、strict 结构化输出),受控实验 7 项(BGE-M3、Qwen3-Embedding、pgvector、LegalBench、LegalBench-RAG、lexml-linker、br-eli-mcp、RAGChecker 仅诊断),拒绝采用 6 项(LangGraph、GraphRAG 自动图构建、RefChecker 已归档、STARA 闭源、CoCounsel/Lexis/Vincent 产品与数据)。
- **文件与精确行号**: N/A(外部来源);关键来源:arxiv.org/abs/2402.03216、2308.11462、2408.10343、2408.08067、2405.14486;github.com 的 FlagOpen/FlagEmbedding、pgvector/pgvector(LICENSE 原文)、docling-project/docling、tesseract-ocr/tesseract、langchain-ai/langgraph、promptfoo/promptfoo、microsoft/graphrag(RAI_TRANSPARENCY.md 原文)、in-toto/in-toto、sigstore/cosign、HazyResearch/legalbench、zeroentropy-ai/legalbenchrag、amazon-science/RAGChecker、amazon-science/RefChecker(已归档)、lexml/lexml-linker、matematicsolutions/br-eli-mcp;docs.oasis-open.org LegalRuleML v1.0 OS;projeto.lexml.gov.br/documentacao/Parte-2-LexML-URN.pdf;reglab.github.io/stara;legal.thomsonreuters.com/en/products/cocounsel-legal;lexisnexis.com Shepard's 与 Lexis+ AI 页;vlex.com/vincent-ai;platform.claude.com、developers.openai.com、ai.google.dev、api-docs.deepseek.com、alibabacloud.com 官方文档
- **命令**: 三个子代理 WebFetch/WebSearch(访问日期均 2026-07-18)
- **原始结果摘要**: 要点:RefChecker 2026-04-08 归档;LangGraph 官方文档不承诺确定性重放;GraphRAG RAI 文档自证输出需领域专家逐条人工验证;lexml-linker 为 GPL-2.0(须进程隔离);br-eli-mcp 存在(v0.7.1,2026-07-18 发布,0 star 单人维护);Vincent 官方列明覆盖巴西(州/市级深度未披露);Claude/GPT/Gemini/DeepSeek 官方文档均已 GA schema 保证型结构化输出;DeepSeek 旧模型名 2026-07-24 弃用。
- **提交 SHA**: 65f0b398(仓库状态);外部来源以访问日期为准
- **是否已复现**: 单轮访问,未二次复现;完整逐项字段(已核验事实/可借鉴/不能解决/采用状态/gold set/进入退出条件/URL)见本轮 Phase 0.5 会话报告。
- **限制和不确定性**: 未核验残留:Qwen3.7-Max 1M 上下文与 strict schema 官方文档、BGE-M3 葡语逐项列名、in-toto↔SLSA 官方关系表述、CoCounsel 巴西覆盖、Vincent 州/市级深度、LegalBench 与 lexml-linker 最后提交日期、projeto.lexml.gov.br 根页(503)、各厂商营销数字(登记为主张)。这些不得当作事实使用。
