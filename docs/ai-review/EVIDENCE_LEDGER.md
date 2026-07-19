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

## EV-0018

- **claim**: 基线动态验证(首次实测)在本基线全部通过:靶向 6 文件 35 passed;全量后端 295 passed;compileall 通过;前端 29 passed、Vite 构建成功;发布边界检查 OK;git diff --check 干净。
- **文件与精确行号**: N/A(测试运行)
- **命令与结果**(环境:远程受管容器 Linux;Python 3.12.3(uv venv,scratchpad 内,未用系统 3.11);Node v22.22.2;npm 10.9.7;Docker 29.3.1;运行时工作树 = 基线 65f0b398 + 5 个交接文件):
  1. `pytest -q tests/test_capability_pack_api.py tests/test_country_independent_fixture_flow.py tests/test_mechanism_layer.py tests/test_legal_source_versions.py tests/test_delivery_assurance.py tests/test_release_safety.py` → **35 passed, 3 warnings in 32.11s**(real 0m33.75s)
  2. `python -m compileall -q app tests` → 退出 0(real 0m0.14s;pytest 先行已生成 __pycache__)
  3. `python -m pytest tests -q`(全量)→ **295 passed, 3 warnings in 73.70s**(real 1m15.16s)
  4. `npm ci` → 成功(real 0m4.81s);`npm run test:components` → **7 文件 29 passed**(Duration 5.88s);`npm run build` → **✓ built in 3.62s**(158 modules 级输出正常)
  5. `bash scripts/check_release_boundaries.sh` → 全部 OK,exit=0;`git diff --check` → 干净
- **原始结果摘要**: 无失败、无跳过报告;警告为 starlette testclient 弃用、passlib crypt(Py3.13 移除预告)、reportlab ast.NameConstant 弃用,均非本仓库代码。
- **提交 SHA**: 产品代码 65f0b398(工作树含 5 个交接文件,不影响 backend/frontend 测试对象)
- **是否已复现**: 本轮单次运行;未做二次复现。
- **限制和不确定性**: 测试库为 SQLite/测试配置,PostgreSQL 并发/事务结论仍属 experiment_required(WS-4);Alembic 升降级往返未在本轮运行(需一次性 PostgreSQL,后续专项);passlib 的 Py3.13 弃用警告提示未来升级 3.13 需换 bcrypt 直连或升级 passlib。

## EV-0019

- **claim**: WS-1C 设计前提事实(静态复核,两路只读采集):(1) Pack 发现为文件系统 glob `capability_packs/*/manifest.json`,排除 fixtures(registry.py:50-58);`get_exact(pack_id, version, semantic_hash)` 已存在但只校验当前唯一 manifest(registry.py:88-92);active 状态仅存于 manifest.status,无 DB 表。(2) 冻结快照只存 id/version/hash(scenario_scope_service.py:377-419),不嵌入内容;运行时经 require_generation_config→load_frozen_capability_pack→load_capability_pack **每次从单一可变磁盘文件重读并重验 SHA-256**(loader.py:135-140;generation_guard.py:181-214);检索时 load_corpus 直接 json.load(legal_ingest.py:34-37),完整性依赖上游 manifest 重验。(3) 无任何历史版本归档(无 DB 表、无文件归档):磁盘文件被修改后旧场景在 loader.py:137-140 / registry.py:90-91 fail-closed,**不可重现**。(4) 当前版本号:pack 1.3.1、rules_artifact brazil_new_energy 2.9(hash 351c7d6f…62c9c)、corpus 1.13(hash b91783bc…c787f)、semantic_hash dd26e226…808b、manifest_schema_version 1.1(manifest.json:2-61)。(5) 消费方全部为"当前代码重算+stable_hash 相等"式 fail-closed:唯一显式版本分支是 compiler_version=="0.2" 字符串相等(answerability_gate_service.py:111-116)与 resolution evidence schema_version=="1.0"(legal_quality_eval.py:126);proof body "0.1"、release body "1.1"、bundle "1.4"、gate "1.0" 等字面量只被写入哈希体,从不回读分支——**任何格式变更都会使全部历史制品 hash 失配而 fail-closed**。(6) Alembic 线性链 0001→0006,head=20260718_0006;PostgreSQL DDL 仅 Alembic(test_database_initialization 断言 init_db 不 create_all);测试为逐测试 SQLite create_all,无 conftest.py;fixture pack 经构造器旗标+monkeypatch 注入。(7) legal_quality_eval 经硬编码默认磁盘路径加载 rules/corpus,绕过 Pack registry(legal_quality_eval.py:28-30,135-142)。(8) 前端在 sceneClassification.ts:113-118 做 pack id/version/hash 与 snapshot 的相等校验。(9) 现有 superseded/archived/history 概念均非制品版本归档(delivery 状态机、软删除、审计轨迹)。
- **文件与精确行号**: 见 claim 内逐条
- **命令**: 两个只读子代理(Read/Grep/Glob)
- **原始结果摘要**: 见 claim;完整报告存于本会话。
- **提交 SHA**: 65f0b398
- **是否已复现**: 静态复核;关键路径(loader 哈希验证、get_exact)另有本轮实测通过的 test_capability_packs.py 佐证(EV-0018)。
- **限制和不确定性**: rules_registry.py 传统加载路径(无哈希校验)与 material fields 的耦合程度需实施时确认。

## EV-0020

- **claim**: WS-1C/C1(Capability Pack 历史版本索引与精确寻址基础)已实施并全量验证通过。实现:(1) `version_index.py`(新增):归档发现 `discover_archived_versions`(结构校验:bundle 唯一 manifest、内目录=pack ID)、`load_archived_pack`(经现有 loader 全量哈希重验后,再校验归档目录名与 manifest 的 pack ID/version 相等)、`PackVersionIdentity`(semantic/rules/corpus 三哈希)、`CapabilityPackVersionIndex.register` 只增注册(同 key 不同身份 → `CapabilityPackVersionCollisionError`);(2) `registry.py`:`archive_root` 属性、`_manifest_paths` 显式排除 archive 目录、`get_exact` 先 active 后 archive(同 key 身份冲突即抛,不回退 active/current/最近版本/其他 hash;pack 与版本均不存在时保留原 NotFound/Inactive 语义)、`build_version_index()` 与 `list_versions()`;(3) loader/`resolve_server_resource`/`rules://`/`corpus://` 语义零改动——归档 bundle 的 `capability_packs` 目录作为 capability_root 传入现有 loader。archive 不进入 list_active/list_public_active/match 路由。
- **文件与精确行号**: backend/app/capability_packs/version_index.py(新,约 180 行);backend/app/capability_packs/registry.py(get_exact 重写与新增方法);backend/tests/test_capability_pack_version_archive.py(新,14 测试,含 12 项任务书要求场景 + archive/archive 冲突单元测试 + 生产 registry 行为不变)
- **命令与结果**(环境:Python 3.12.3 uv venv,Node/npm 未涉及):
  1. `pytest -q tests/test_capability_pack_version_archive.py` → **14 passed**(1.00s)
  2. `pytest -q tests/test_capability_pack_api.py tests/test_country_independent_fixture_flow.py tests/test_capability_pack_version_archive.py` → **27 passed**(24.29s)
  3. `python -m compileall -q app tests` → 通过
  4. `ruff check app/capability_packs/registry.py app/capability_packs/version_index.py tests/test_capability_pack_version_archive.py` → All checks passed
  5. 全量 `pytest tests -q` → **309 passed**(92.72s;基线 295 + 新增 14,零失败零跳过,未修改任何既有测试)
  6. `bash scripts/check_release_boundaries.sh` → 全部 OK;`git diff --check` → 干净
- **原始结果摘要**: 见上;真实 1.3.1/2.9/1.13 归档未创建(留给 C2,仓库内无 archive 目录,C1 测试仅用 tmp_path 合成 bundle)。
- **提交 SHA**: 见本轮提交(feat(capability-packs): add exact archived version lookup)
- **是否已复现**: 单轮;每项命令一次通过。
- **限制和不确定性**: 动态验证仍限 SQLite 测试库;startup 扫描(C4)、消费方版本注册表(C3)未实施;`list_versions`/`build_version_index` 暂无生产调用方(为 C2~C4 与未来 startup 扫描准备)。

## EV-0021

- **claim**: C1-F1(inactive live-root 精确身份 Bug)已修复(C1.1)。修复前失败模式:`get_exact` 经 `self.get(pack_id)`(require_active=True)读取 live root,导致 (1) inactive live-root Pack 无法按精确 version/hash 被冻结历史场景读取(抛 CapabilityPackInactiveError);(2) inactive live-root 与 archive 同 pack_id/version 但身份不同时绕过 collision 检查(live 侧被当作不存在);(3) 与 `build_version_index()` 纳入全部 live-root Pack 的行为不一致。修复:`get_exact` 改用 `self.get(pack_id, require_active=False)` 且仅将 `CapabilityPackNotFoundError` 视为 live-root 不存在;routing 行为不变(get 默认仍 require_active、list_active/list_public_active/match/match_material 仍仅 active、archive 仍不参与 routing);新增保守输入验证:version 须匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`(非严格 SemVer,禁路径分隔符),semantic_hash 规范化小写后须为 64 位十六进制,非法输入抛 CapabilityPackRegistryError;version 不用于拼接 archive 路径(仍经服务器扫描索引查找)。
- **文件与精确行号**: backend/app/capability_packs/registry.py(_EXACT_VERSION/_SEMANTIC_HASH 常量与 get_exact 重写);backend/tests/test_capability_pack_version_archive.py(新增 5 测试:inactive 精确读取、inactive 对 get/routing 仍不可用、inactive/archive 身份冲突、inactive/archive 同一身份允许、非法 version/hash 格式拒绝+大写 hash 规范化)
- **命令与结果**(Python 3.12.3 uv venv):
  1. `pytest -q tests/test_capability_pack_version_archive.py` → **19 passed**(1.07s;原 14 全部保留未降级)
  2. `python -m compileall -q app tests` → 通过
  3. `ruff check`(3 文件)→ All checks passed
  4. 全量 `pytest tests -q` → **314 passed**(86.68s;309 + 新增 5,零失败零跳过)
  5. `bash scripts/check_release_boundaries.sh` → OK;`git diff --check` → 干净
- **原始结果摘要**: 生产 registry 行为(test_production_registry_behavior_unchanged)与 fixture 行为(test_fixture_behavior_unchanged)测试保持通过;version_index.py 未改动。
- **提交 SHA**: 见本轮提交(fix(capability-packs): preserve inactive exact version identity)
- **是否已复现**: 单轮;每项命令一次通过。
- **限制和不确定性**: 行为变化披露:此前 get_exact 对"仅存在 inactive live-root 且身份失配"抛 CapabilityPackInactiveError,现统一抛 "version/hash 与冻结身份不一致";全库无依赖旧行为的调用方(全量测试绿)。

## EV-0022

- **claim**: WS-1C/C2 真实归档已创建且 byte-identical。归档结构:`backend/app/capability_packs/archive/brazil_new_energy_greenfield/1.3.1/bundle/{capability_packs/brazil_new_energy_greenfield/manifest.json, rules/brazil_new_energy.json, data/brazil_legal_corpus.json}`,以 `shutil.copyfile` 原始字节复制,无任何重新序列化。**冻结常量(本轮实测)**:manifest raw-file SHA-256 = `dd69255f56e9b4589f27987f11d7e3cf2b471de0c8293b25867aa4257dbba108`(新登记);rules = `351c7d6f6f71a5d1cedd3527a10a8b89f1cd72d3079d4b41d42b827aeba62c9c`(与 manifest 内 content_hash 一致);corpus = `b91783bc354d57a84453b7c064d8bb413939a2693109835fbcc5b20ce54c787f`(一致);semantic = `dd26e226ea600fd05e23d6141dab8a051881b3ed3723abcf718ddf3bc81e808b`;身份:pack 1.3.1 / rules 2.9 / corpus 1.13。
- **文件与精确行号**: 上述 3 个归档文件;backend/tests/test_capability_pack_real_archive.py(8 测试)
- **命令与结果**:
  1. 复制前后 `sha256sum` 源三文件:两次输出完全一致(manifest dd69255f…、rules 351c7d6f…、corpus b91783bc…),源文件未被改动;
  2. 归档三文件 `sha256sum` 与源逐一相同;Python bytes 比较 `byte_equal=True` ×3;`cmp -s` ×3 全部相同(CMP_MANIFEST_OK/CMP_RULES_OK/CMP_CORPUS_OK);
  3. 长期回归测试只依赖冻结常量(不依赖 active 与归档永远相同):raw hash ×3、semantic hash、pack/rules/corpus 版本标识、discover/load、加载路径在 bundle 内、active+archive 同身份无 collision、list_versions 单一 1.3.1 身份、不进 public/active/routing、无 active 时可 get_exact 但 get/match 失败、单字节篡改(保持 JSON 合法)命中 rules content hash 校验、删除 rules/corpus 副本 fail-closed。
- **提交 SHA**: 见 C2 提交(chore(capability-packs): archive brazil pack 1.3.1 artifacts),分支 claude/vela-ws-1c-c2-real-archive(基于 730b9fd)
- **是否已复现**: 哈希三重验证(sha256sum、Python bytes、cmp);测试单轮通过。
- **限制和不确定性**: 一次性创建证据(源==归档)只在 C2 时点成立,后续 active 升级后仅冻结常量有效——测试已按此设计。

## EV-0023

- **claim**: 【C2 打包包含性发现与修复】两个 backend Dockerfile 为逐文件 COPY allowlist + backend/.dockerignore 默认拒绝:(1) 归档目录默认被排除于后端镜像;(2) **C1 打包回归**——`version_index.py` 不在 COPY/dockerignore 允许清单,registry.py 导入它,镜像内应用将 ImportError(CI production-compose-smoke 会拦截,但属 C1 遗漏)。最小修复:backend/.dockerignore 增加 4 行放行(version_index.py + 3 个归档文件);两个 Dockerfile 的 capability_packs COPY 行加入 version_index.py,并新增 `COPY app/capability_packs/archive ./app/capability_packs/archive`;scripts/release_safety.py 的 EXPLICIT_RUNTIME_FILES 加 version_index.py、PACKAGE_TREES 加 archive 树(仅新增条目,未放宽任何既有边界);新增边界测试 test_backend_image_allowlists_include_version_index_and_archive。
- **文件与精确行号**: docker/Dockerfile.backend:18-20;docker/Dockerfile.backend.prod:18-20;backend/.dockerignore(capability_packs 段);scripts/release_safety.py(EXPLICIT_RUNTIME_FILES/PACKAGE_TREES);backend/tests/test_release_safety.py(新增测试)
- **命令与结果**: `bash scripts/check_release_boundaries.sh` → 全 OK,backend COPY 候选 127(dev)/137(prod),较修复前 +4,恰为 version_index.py + 3 归档文件;fixtures/pending corpus 排除检查保持 OK。
- **提交 SHA**: 见 C2 提交
- **是否已复现**: 单轮。
- **限制和不确定性**: 容器内探针结果见 EV-0024(镜像构建另记)。

## EV-0024

- **claim**: 【未验证项,如实登记】后端镜像构建与容器内探针在本执行环境**未完成验证**。已用 CI 真实命令尝试:`docker build --pull -f docker/Dockerfile.backend.prod -t vela-backend:ci backend`(与 .github/workflows/ci.yml:113 完全一致;本地先行启动 dockerd)。失败于 Dockerfile 第 6 行 `pip install -r requirements.lock`:pypi.org 连接被环境的透明 TLS 拦截代理终结,证书链含自签 CA,`SSLCertVerificationError: self-signed certificate in certificate chain`;实测即使清空代理环境变量,容器直连仍被同一 MITM 拦截。修复该错误需在构建容器内禁用证书校验或改造 Dockerfile/构建方式,两者均被纪律禁止(环境:不得禁用 TLS 校验;任务书:不得发明不同构建方式)。
- **文件与精确行号**: docker/Dockerfile.backend.prod:6;.github/workflows/ci.yml:113
- **命令与结果**: build 退出码 1;pip 报错原文以及直连测试输出已记录于本会话;`docker system prune -af` 已清理残留。
- **提交 SHA**: 见 C2 提交
- **是否已复现**: 失败模式两次复现(代理与直连)。
- **限制和不确定性**: **镜像包含 archive、容器内 registry 发现/加载、archive 不参与 routing 四项容器级断言均为未验证**;当前包含性证据仅为静态双重验证:(1) release_safety check-docker 按真实 dockerignore+COPY 语义计算的传输/候选集合含 version_index.py 与 3 个归档文件(EV-0023);(2) 等效加载逻辑在宿主机测试中通过(EV-0022)。待具备可信出网或 CI 环境时,应由远端 GitHub Actions production-compose-smoke(真实构建+烟测)闭环,其结果以具体 commit 的 Actions run 为准。

## EV-0025

- **claim**: C2.1 完成:(1) 修复长期回归测试对当前 active 版本/数量的错误依赖——原 `test_registry_index_and_exact_lookup_with_real_archive` 严格断言 `list_versions(PACK_ID)` 仅含 1.3.1 一条、原 `test_real_archive_not_in_public_active_or_routing` 严格断言 active/public 总数为 1,active 升级到 1.4.0 或新增第二个真实 Pack 时会错误失败;修改后:list_versions 只锚定 1.3.1 条目(哈希与冻结常量一致、同 (pack_id,version) 恰出现一次、允许未来更多版本)、active/public/routing 断言改为"active 清单任何 Pack 的 manifest_path 不在 archive root 下、公开清单不因归档产生重复 PACK_ID@1.3.1、当前 active Brazil route 的 match() 返回非归档制品",不固定未来版本号。(2) 新增未来升级模拟测试 `test_future_active_upgrade_keeps_archived_version_readable`(合成:archive 1.3.1 + 同 pack active 1.4.0 + 第二个不同 pack_id active):list_versions 同含 1.3.1/1.4.0 各一次、1.3.1 仍可 get_exact 且路径在 bundle 内、routing 只返回 1.4.0、归档不增加 routing candidate、第二个 active Pack 不影响。(3) **无网络 Docker context 实探针通过**:临时 Dockerfile(FROM scratch,仅 2 条 COPY,不入仓库)+ 真实 daemon `docker build --no-cache --progress=plain -f <scratch>/vela-c2-context-probe.Dockerfile -t vela-c2-context-probe backend`,`docker create`+`docker export`+`tar -tf` 确认四个目标路径全部存在:probe/app/capability_packs/version_index.py 与 archive bundle 的 manifest/rules/corpus 三文件。该探针只验证真实 .dockerignore 与 Docker context/COPY 语义,不宣称完成正式生产镜像运行验证(该项仍按 EV-0024 未验证)。探针容器/镜像/Dockerfile/tar 已全部删除。
- **文件与精确行号**: backend/tests/test_capability_pack_real_archive.py(两测试重写);backend/tests/test_capability_pack_version_archive.py(_build_pack/_install_* 参数化 + 新增模拟测试;既有断言未删未降)
- **命令与结果**(Python 3.12.3):专项 2 文件 → **28 passed**(19+9,含新增模拟测试);compileall 通过;ruff 2 文件 All checks passed;全量 `pytest tests -q` → **324 passed**;check_release_boundaries.sh 全 OK;git diff --check 干净;探针四路径断言全 PRESENT。
- **提交 SHA**: 见 C2.1 提交(test(capability-packs): future-proof archive regression coverage)
- **是否已复现**: 单轮通过;探针输出已原样记录。
- **限制和不确定性**: 探针不含 pip 安装与运行时导入;完整生产镜像构建仍由远端 CI production-compose-smoke 闭环(EV-0024)。

## EV-0026

- **claim**: 【C3 设计前提:版本身份全景与失败模式,三路只读分析交叉验证】(1) 全库唯一显式版本分支是 gate 的 `compilation.compiler_version != COMPILER_VERSION`(answerability_gate_service.py:111-116,reason `compiler_version_stale`,409 经 api/scenarios.py:149);无任何按版本分发的 reader。(2) proof body "0.1"(mechanism_service.py:596)从不被回读分支;_assert_coverage_integrity 用当前 builder 重算比对(answerability_gate_service.py:246-257)。(3) proof 0.1 与 compiler 0.2 无显式兼容声明;唯一耦合是 proof body 内嵌 compiler_input/output_hash(mechanism_service.py:599-600)。(4) **gate_version "1.0" 被持久化两处且 hash 绑定进 release**:gate 字典整体嵌入 `mechanism.answerability_gate`(delivery_assurance_service.py:899,949)→ delivery snapshot("1.0",:982)→ stable_hash 进 attestation/artifact/release 的 snapshot_hash(:1167,:1459,:2362)与冻结 audit bundle bytes(:1168-1175,bundle_version "1.4");无任何回读。改动 gate 字典任何键即漂移所有历史 snapshot_hash(`delivery_release_snapshot_stale` :2453)。(5) release "1.1" 仅存在于被散列后弃存的 _release_body(:803)与 evaluate 返回报告(:2713);**ScenarioDeliveryRelease 无 schema 列**(models/delivery_assurance.py:417-440);pydantic `Literal["1.1"]`(schemas/delivery_assurance.py:540,全后端唯一 Literal 版本钉)用于 GET status 响应,builder 改版会致 FastAPI 响应校验 500。(6) 任何 builder 变更使全部历史 hash 失配的比对点:input snapshot :135(compiler_input_snapshot_stale/409)、claim values :152(compiler_output_hash_invalid/422)、proof :252-257(coverage_proof_stale/409)、snapshot :2453(delivery_release_snapshot_stale)、release :2693(delivery_release_hash_invalid)、attestation 自洽 :2481-2483、content manifest :2230/:2581(certification hash invalid)。(7) 持久化版本身份清单:可靠——ClaimCompilation.compiler_version(列,0003 迁移)、CoverageProof.proof.schema_version(JSON 内)、ScenarioGenerationInput.schema_version(列,0001:128;writer scenario_scope SCOPE_SCHEMA_VERSION="2.0"/GENERATION_INPUT_SCHEMA_VERSION="1.0",scenario_scope_service.py:32-34,fail-closed 相等校验 :320)、attestation.snapshot JSON 内嵌 "1.0"、manifest_schema_version "1.1";装饰性——ComplianceChecklist.version "v0.1"(仅回显);bytes 冻结——audit bundle "1.4"(基底 builder "1.2",audit_bundle_service.py:92,test_review_safety.py:269 钉 "1.2");**缺失——ScenarioDeliveryRelease(无版本列,body 不存)与 legal content manifest(仅存 hash)**。(8) 测试钉扎:唯一锁 "1.1" 的断言 test_delivery_assurance.py:858-859;descriptor/receipt "1.0" fixtures :728,:746;**无任何测试钉 compiler "0.2"/proof "0.1";compiler_version_stale 无测试覆盖**;前端零运行时版本分支(仅 TS 类型与 mock,MechanismView.spec.ts:122 甚至用过期 '0.1')。
- **文件与精确行号**: 见 claim 内逐条(三个子代理独立复核,证据一致)
- **命令**: 本会话 rg 全景扫描(155 hits)+ ultracode workflow 三路只读深潜(310k tokens,113 tool calls)
- **原始结果摘要**: 完整三份报告存于本会话 workflow journal;要点已收录。
- **提交 SHA**: ace91d2(C2 分支)
- **是否已复现**: 三路独立分析对关键事实(gate 嵌入链、release 无版本列、无历史 reader)相互印证。
- **限制和不确定性**: 静态分析;golden vector 生成待 C3.0 实施。

## EV-0027

- **claim**: WS-1C/C3-A 实施完成并全量验证。(1) **C3.0 goldens**(commit 061be1e):四组合成 golden 从重构前行为(efc76e0)生成,固定 uuid 序列与时间戳,两次生成 byte-identical;raw SHA-256:compiler_v0_2.json=8787a1644a0c6fe4076978e3b181caa9f3072e29db1e71d3b5670415df4679b4、coverage_proof_v0_1.json=206cb55372dcdb7d00a12d4af38b69a95e10ec57d662f538498c64e138807ffb、answerability_v1_0.json=e40f68050c8e3f56c26ea20fb19772a6fe78109c76d2f5d29d98efc5426f257a、delivery_release_v1_1.json=6cdce303c806ff36e804f01d67e42595d6307984a83312efe211a50f4fdac256;冻结的六个关键 hash:compiler input 5e566256…ded0b / output e731487b…458ab、proof 08536aca…29184、denominator 9a1dbe05…8c6ac、snapshot e3dfe751…01f88、release 92a35172…aad73;测试与冻结 JSON/hash 常量比较,非函数对函数。(2) **C3.1**(dafc96e):canonical_hash_v1(D-0015,与 stable_hash 算法逐字符等价,测试覆盖中文/排序/list/datetime/None-bool-number/嵌套+全部 golden hash)、静态只增 registry(唯一性构造器,重复/空即抛)、claim_compiler/v0_2 冻结模块(不 import mechanism/gate,私有 FactRecord 查询序)、mechanism_service 薄 wrapper(writer 仍写 0.2,hash 与 golden 一致)、gate 按持久化 compiler_version 分发:未注册→422 compiler_version_unsupported(D-0014),取代旧 compiler_version_stale 一揽子拒绝;既有 stale/tamper 409/422 语义不变;Docker/.dockerignore/边界测试同 commit。(3) **C3.2**(e39edf0):coverage_proof/v0_1 纯冻结模块、SUPPORTED_COVERAGE_PROOF_READERS、显式兼容矩阵 (0.2,0.1)、gate 回读 proof.schema_version:缺失/未注册→422 coverage_proof_schema_unsupported,注册但矩阵外→422 version_combination_unsupported:<c>+<p>;重算/哈希全部经存储版本 reader。(4) **验证**:靶向 53 passed;全量 **359 passed**(基线 324+35 新增,零删改降级);compileall、ruff(全部新增/修改文件)、check_release_boundaries、git diff --check 全过;写默认前移模拟(CURRENT→"0.3")后存储 0.2 仍经 0.2 reader 验证;无网络 FROM scratch context 探针确认 8 个 versioned .py 全部进入 backend 构建 context(探针产物已删)。完整生产镜像仍按 EV-0024 未验证(TLS 拦截)。
- **文件与精确行号**: backend/app/services/versioned/{__init__,registry,canonical_hash/v1,claim_compiler/v0_2,coverage_proof/v0_1}.py;mechanism_service.py(薄 wrapper);answerability_gate_service.py(双分发);backend/tests/{goldens/versioned/*,test_versioned_goldens.py,test_versioned_registry.py};backend/.dockerignore;docker/Dockerfile.backend{,.prod};test_release_safety.py
- **命令与结果**: 见 claim;环境 Python 3.12.3 uv venv。
- **提交 SHA**: 061be1e(C3.0)、dafc96e(C3.1)、e39edf0(C3.2),分支 claude/vela-ws-1c-c3a-versioned-readers(基于 efc76e0)
- **是否已复现**: goldens 双次生成一致;测试单轮全绿。
- **限制和不确定性**: C3-B 范围(snapshot/release reader、Alembic 0007)未实施;golden 再生成需经批准的新决定。

## EV-0028

- **claim**: C3-A.1(持久化 JSON 结构验证 + Registry 自洽性 + writer 版本单一事实源)完成。**修复前三类可 500 的失败模式**:(1) `compilation.input_snapshot` 被 raw SQL 改为 list(哈希同步重算)→ gate `stored_snapshot.get()` AttributeError → 500;(2) snapshot.drafts 含标量/缺字段(哈希同步重算)→ v0_2 `draft["checklist_code"]` TypeError → 500;(3) `proof.proof` 改为 list/字符串或当前 checklist payload 改为非对象 → `.get()`/reader 内部 AttributeError → 500。**修复**:gate reader 调用边界显式结构验证(无宽泛 except):snapshot 非对象/draft 结构非法 → 422 `compiler_input_snapshot_invalid`;当前 payload 非法形状(payload/sections/items/legal_hits/brief 逐层检查)→ 422 `compiler_current_payload_invalid`;proof body 非对象或 schema 非字符串/未注册 → 422 `coverage_proof_schema_unsupported`;已知 0.1 schema 但 denominator/covered/uncovered 结构非法(含 uncovered 元素 checklist_code/status/unanswerable_reasons 类型)→ 422 `coverage_proof_body_invalid`;即使攻击者同步重算 hash 仍被阻断(全部有对抗测试)。**Registry 自检**:`validate_registry_configuration` 纯函数(key==reader.version、CURRENT 写版本已注册、兼容矩阵对已注册版本封闭、必需历史条目 0.2/0.1/(0.2,0.1)、重复即抛),模块装载时执行一次,违规抛 `VersionedRegistryConfigurationError`,不自动修复/忽略/fallback。**writer 单一事实源**:compile_claims 持久化 `writer.version`(经 current_compiler_writer()),COMPILER_VERSION 仅为只读兼容别名并注释禁止用于写库身份;合成 0.3 writer 测试证明新 compilation 保存 "0.3" 且 input/output hash 用该 writer 的 hash 函数(未把 0.3 加入生产 Registry)。
- **文件与精确行号**: backend/app/services/answerability_gate_service.py(_drafts_structure_ok/_checklist_payload_structure_ok/_coverage_proof_body_structure_ok + 两处边界插入);backend/app/services/versioned/registry.py(validate_registry_configuration + 装载自检);backend/app/services/mechanism_service.py(compile_claims writer.version);backend/tests/test_versioned_payload_validation.py(新增 21 测试:4 组 compiler 结构、3+4+1 组 proof 结构、真实 gate 排除 (0.2,0.1) 组合 → version_combination_unsupported:0.2+0.1、5 组配置自检、生产 registry 自洽、writer 单源)
- **命令与结果**(Python 3.12.3):新专项 **21 passed**;靶向 4 文件 39 passed;compileall/ruff 过;全量 **380 passed**(359+21,零删改降级);check_release_boundaries OK(无新增运行时模块,Docker allowlist 未动);git diff --check 干净;**golden 四文件 raw SHA-256 与 EV-0027 冻结值逐一相同**(frozen v0_2/v0_1/goldens 未触碰)。
- **提交 SHA**: b41921e(fix(versioning): validate persisted reader identities),分支 claude/vela-ws-1c-c3a-versioned-readers
- **是否已复现**: 单轮全绿;21 个对抗测试均先按"攻击者重算哈希"构造。
- **限制和不确定性**: compile 写路径(payload 服务器生成)未加同套结构验证——gate 是唯一交付边界;PostgreSQL 动态验证仍属 WS-4/WS-5。

## EV-0029

- **claim**: Codex 从远端 Claude 交接分支的精确 HEAD `00b47bc89f11aa5a8eaaf38dae18565e8fd07274` 建立独立 `codex/vela-mvp-integration`,并完成 WS-1C/C3-A.2。修复内容:(1) persisted draft 的 `fact_refs`/`evidence_refs` 除外层必须为 list 外,元素必须全部为字符串;非法形状在 frozen compiler 0.2 reader 前返回 422 `compiler_input_snapshot_invalid`。(2) 每个 ClaimRecord 的 `fact_refs`、`evidence_refs`、`reason_codes` 必须为 `list[str]`;None、标量、字符串、dict 或含非字符串元素的 list 返回 422 `claim_record_json_invalid:<checklist_code>`,并在任何 `list(...)`、集合推导或 provisional evidence disclosure 前阻断。(3) CoverageProof 0.1 的 denominator 元素必须含字符串 checklist_code/statement,covered_checklist_codes 必须为 `list[str]`,uncovered 的 checklist_code/status 必须为字符串且 unanswerable_reasons 必须为 `list[str]`;非法结构返回 422 `coverage_proof_body_invalid`。全部攻击测试在可行处同步重算 input/proof/denominator hash 与 counts,证明阻断来自结构验证而非哈希碰巧失配。
- **文件与精确行号**: `backend/app/services/answerability_gate_service.py:85-120`(draft/Claim JSON),`:170-199`(proof 嵌套结构),`:289-306`(Claim 校验早于 JSON 消费);`backend/tests/test_versioned_payload_validation.py:90-127`(draft 引用),`:148-178`(Claim JSON 与 supported disclosure),`:208-242`(proof 嵌套结构)。
- **命令与结果**(macOS;独立 `work/vela-review-venv`;Python 3.12;requirements.lock + CI 同版 pytest 8.4.2):
  1. `python -m pytest -q tests/test_versioned_payload_validation.py` → **34 passed**,1 个既有 reportlab 弃用警告;
  2. 指定组合 `test_versioned_payload_validation.py test_versioned_registry.py test_versioned_goldens.py test_mechanism_layer.py test_delivery_assurance.py` → **73 passed**,3 个既有第三方弃用警告;
  3. `python -m compileall -q app tests` → 通过;`ruff check app/services/answerability_gate_service.py tests/test_versioned_payload_validation.py` → All checks passed;
  4. 全量 `python -m pytest tests -q` → **393 passed**,3 warnings,零失败零跳过;
  5. `bash scripts/check_release_boundaries.sh` → 全部 OK;`git diff --check` → 干净;
  6. 四个 golden raw SHA-256 逐一与 EV-0027 相同:compiler `8787a1644a0c6fe4076978e3b181caa9f3072e29db1e71d3b5670415df4679b4`;proof `206cb55372dcdb7d00a12d4af38b69a95e10ec57d662f538498c64e138807ffb`;answerability `e40f68050c8e3f56c26ea20fb19772a6fe78109c76d2f5d29d98efc5426f257a`;release `6cdce303c806ff36e804f01d67e42595d6307984a83312efe211a50f4fdac256`。
- **提交 SHA**: `a6d985402ebe606cc423c9c3d2c270e00229979c` (`fix(versioning): validate nested persisted references`)
- **是否已复现**: 专项和全量各完成一次最终绿测试;全量首次运行暴露测试夹具收集顺序问题(29 setup errors,非产品失败),修正为保留原 pytest fixture 导入并对该特定 F811 语义加窄范围 Ruff 指令后,专项与全量均重跑通过。
- **限制和不确定性**: 本轮数据库为 SQLite 合成测试;PostgreSQL 并发/事务攻击仍属 WS-4/WS-5。C3-B 的 delivery snapshot/release reader 与 Alembic 0007 未实施。完整生产镜像运行探针仍按 EV-0024 未验证。法律认证、真实客户 UAT、客户生产部署证据均继续为 `blocked_external`。

## EV-0030

- **claim**: C3-B 已实现持久化版本精确分发且不改变冻结 hash。Delivery Snapshot / Answerability Gate 1.0 与 Delivery Release 1.1 已抽入只增不减 reader；兼容组合为 compiler 0.2 / proof 0.1 / snapshot 1.0 / release 1.1；release writer 显式保存所选 `reader.version`；evaluator 按 `ScenarioDeliveryRelease.schema_version` 与 snapshot 内版本读取，unknown release/snapshot 分别稳定阻断为 `delivery_release_schema_unsupported` / `delivery_snapshot_schema_unsupported`，无 current/latest fallback。状态响应继续使用 envelope 1.1，并以普通字符串 `release_schema_version` 披露未来 reader 身份，避免响应校验 500。
- **文件与精确行号**: `backend/app/services/versioned/registry.py:191-297`;`backend/app/services/versioned/delivery_snapshot/v1_0.py`;`backend/app/services/versioned/delivery_release/v1_1.py:157`;`backend/app/services/delivery_assurance_service.py:2298-2355,2438-2453,2742-2750`;`backend/app/models/delivery_assurance.py:398-430`;`backend/app/schemas/delivery_assurance.py:518,541-549`。
- **命令与原始结果摘要**: Python 3.12.13 靶向 C3-A.2/C3-B/readiness/migration/release-safety 组合 → **98 passed**；全量后端 → **404 passed**；compileall 与本轮全部 Python 文件 Ruff 通过；四个 golden raw SHA-256 与 EV-0027 精确一致。
- **提交 SHA**: `1e4bc79` (`feat(versioning): freeze delivery readers and release schema`)。
- **是否已复现**: 是；专项与全量各完成最终绿测试。
- **限制和不确定性**: PostgreSQL 实例验证未执行；本轮 migration 动态证据来自 disposable SQLite。法律正确性与真实外部证据不在该工程证据内。

## EV-0031

- **claim**: C4/C5 已实现只读 version readiness 与存储版本重验。空库为 ready 且不写库；未知 compiler/proof/snapshot/release 在 development 明确 warning、在 production readiness 阻断；启动审计与 `/api/v1/readiness` 不自动修复数据。历史 release 重验在模拟未来 snapshot/release writer 后仍使用存储的 1.0/1.1 reader；unknown 版本 fail-closed。Alembic 0007 将存量 release 回填为 1.1，最终 `NOT NULL` 且无 server default；downgrade 遇非 1.1 行拒绝删除版本身份。
- **文件与精确行号**: `backend/app/services/version_readiness_service.py:27-152`;`backend/app/api/system.py:50-64`;`backend/app/main.py:63-73`;`backend/tests/test_version_readiness.py:97-155`;`backend/tests/test_delivery_assurance.py:859-944`;`backend/alembic/versions/20260719_0007_delivery_release_schema_version.py:20-63`;`backend/tests/test_delivery_release_schema_migration.py:65-125`;`docs/operations/VERSIONED_READERS_RUNBOOK.md`;`docs/REQUIREMENTS_TRACEABILITY.md` B-09。
- **命令与原始结果摘要**: SQLite migration tests 覆盖 fresh head、0006→0007、backfill、NOT NULL、无默认、0007→0006→head、unknown downgrade guard，均包含在 98 passed；历史 writer 前移/unknown 版本攻击包含在同一专项与 404 passed 全量中；`bash scripts/check_release_boundaries.sh` 全部 OK。
- **提交 SHA**: `8ceaff3` (`feat(readiness): audit persisted reader versions`)、`c8328b4` (`test(versioning): prove historical revalidation isolation`)。
- **是否已复现**: 是，SQLite 与服务层均为真实动态执行。
- **限制和不确定性**: 本机没有 PostgreSQL、Docker、Podman、Colima 或 nerdctl；因此 PostgreSQL migration 与真实无网络 `FROM scratch` context probe 保持 environment-unverified。静态 Docker transmitted/COPY candidate 检查已通过，但不得替代 runtime probe。

## EV-0032

- **claim**: Engineering Demonstrator RC0 的原创 synthetic preview UI 已完成八项信息架构、持久上下文/版本/Gate/演示标识、法律研究三栏、完整九阶段交付管线、CoverageProof、审计时间线和 loading/empty/error/blocked/read-only/demo-only/stale/unknown-version。所有拟制对象（含嵌套 context、versions、counts）经递归测试强制携带 `simulated=true`、`evidence_origin=synthetic_demo`、`status=demo_only`、`formal_release_allowed=false`；页面与导出持续警示；正式 Expert Attestation/UAT/Deployment/Release 保持 `blocked_external`。RC0 前端不调用正式 API，BYD/Campinas 不进入该 demo adapter。
- **文件与精确行号**: `frontend/src/demo/rc0SyntheticCase.ts:1-136`;`frontend/src/views/Rc0WorkspaceView.vue:9-130`;`frontend/src/views/Rc0WorkspaceView.spec.ts:14-91`;`frontend/src/styles/rc0.css:1-356`;`frontend/src/router/index.ts`;`docs/ui/UI_RESEARCH_LEDGER.md`。
- **命令与原始结果摘要**: `npm run test:components` → **8 files / 34 passed**；`npm run build` → 164 modules transformed、production build 成功。真实浏览器 desktop 1280 与 mobile 390 检查八个路由：每页 `SYNTHETIC DEMO` 可见、390px 时 `scrollWidth == viewportWidth`、交付 9 stages、desktop 法律研究 3 columns、console errors 0；原生 link/button、`aria-pressed` 与 focus ring 已检查。自动化 Tab 漫游受 in-app browser keypress 运行时限制，未将该工具限制误报为通过。
- **截图路径**: `docs/ai-review/screenshots/rc0-overview-desktop.jpg`;`rc0-legal-research-desktop.jpg`;`rc0-delivery-desktop.jpg`;`rc0-overview-mobile-390.jpg`。
- **提交 SHA**: `360ab8b` (`feat(rc0): add synthetic matter workspace`)、`4ea1dfc` (`fix(rc0): mark nested synthetic objects`)。
- **是否已复现**: 单元/build 两次绿；浏览器 desktop/mobile smoke 一次完整通过。
- **限制和不确定性**: UI 是隔离的 synthetic preview，不是法律内容、真实客户 UAT、律师认证或生产部署证据；截图中的本地用户与数据库为一次性合成环境，已停止并移至废纸篓中的临时清理路径。

## EV-0033

- **claim**: RC0 feature-freeze 最终工程验证通过，且冻结制品未漂移。Golden raw SHA-256:compiler `8787a1644a0c6fe4076978e3b181caa9f3072e29db1e71d3b5670415df4679b4`;proof `206cb55372dcdb7d00a12d4af38b69a95e10ec57d662f538498c64e138807ffb`;answerability `e40f68050c8e3f56c26ea20fb19772a6fe78109c76d2f5d29d98efc5426f257a`;release `6cdce303c806ff36e804f01d67e42595d6307984a83312efe211a50f4fdac256`。Release boundaries 检查所有 Docker transmitted contexts/COPY candidates 均 OK；git diff 无 whitespace 错误。
- **文件与精确行号**: 四个 `backend/tests/goldens/versioned/*.json`;`scripts/check_release_boundaries.sh`;本条与 EV-0030~EV-0032。
- **命令与原始结果摘要**: Python 3.12.13:专项 98 passed、全量 404 passed、compileall 通过、Ruff 通过；Node/Vitest:34 passed；Vite production build 通过；release boundaries 全部 OK；`git diff --check` 通过；raw SHA 逐一匹配。
- **提交 SHA**: 实施提交 `88c2195`,`1e4bc79`,`8ceaff3`,`c8328b4`,`360ab8b`,`4ea1dfc`;证据提交的实时 SHA 必须按 D-0004 由 Git 查询。
- **是否已复现**: 是；所有可在本机执行的 P0/P1 工程验证均完成。
- **限制和不确定性**: PostgreSQL 与真实容器 runtime probe 未执行；Legal Content MVP、Controlled Pilot Ready、Formal Customer Release Ready 均缺真实律师、客户与生产证据，只能保持 `blocked_external`。
