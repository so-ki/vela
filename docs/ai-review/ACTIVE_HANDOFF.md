# Vela Active Handoff

## Repository State
- Repository: so-ki/vela
- Current branch: claude/gracious-brahmagupta-bbg2dw
- Exact HEAD: 83ac279(基于精确基线 65f0b398f94af72680f8c1139aa59f7df6b88d71,仅新增交接协议文件提交)
- Target base: codex/vela-release-hardening @ 65f0b398f94af72680f8c1139aa59f7df6b88d71(未动)
- Worktree status: 干净(交接文件已提交;产品代码零改动)
- Last verified timestamp: 2026-07-18

## Current Phase
- Phase: Phase 0 — 完整 MVP 架构复核(只读)——已完成,等待用户批准进入 workstream
- Workstream: 总控复核
- Status: complete_pending_approval
- Allowed file scope: 仅 `AGENTS.md`、`CLAUDE.md`、`docs/ai-review/ACTIVE_HANDOFF.md`、`docs/ai-review/DECISION_LOG.md`、`docs/ai-review/EVIDENCE_LEDGER.md`
- Prohibited actions: 修改产品代码/规则/语料/迁移/测试/产品文档/UI;向 Draft 分支推送;创建或合并 PR;主动安全实验

## Frozen Product Definition
- 见 `AGENTS.md` 第 2–4 节。补充锚点:`docs/REQUIREMENTS_TRACEABILITY.md`(A/B/C/D/E 条目与状态口径)、`docs/ai-review/TARGET_PRODUCT_STATE.md`(架构宪法与三条抽象纪律)为既有冻结口径,本轮复核未发现需要推翻之处。

## Approved Decisions
- D-0001(分支重置到精确基线)、D-0002(交接五文件全新创建)、D-0003(因环境 stop-hook 与临时容器,交接文件提交并推送到会话分支,Draft 分支未动;待用户追认)。

## Work Completed
- Git 基线核验(EV-0001/0002);交接协议五文件创建并提交(83ac279)。
- 四路只读代码复核完成:问题一(平台边界)、问题二(BYD 污染)、产品流程步骤 1–14、步骤 15–27。
- 三个根本问题结论、六层架构、Gap Matrix、WS-1~WS-10 workstreams 已输出(见本次会话报告;要点回填于下方 Findings)。

## Files Changed
- 新增:AGENTS.md、CLAUDE.md、docs/ai-review/{ACTIVE_HANDOFF,DECISION_LOG,EVIDENCE_LEDGER}.md
- 产品代码/规则/语料/迁移/测试/产品文档/UI:零改动

## Tests and Commands
- command: `git fetch origin && git rev-parse origin/codex/vela-release-hardening`
- result: 65f0b398...(与精确基线一致)
- environment: 远程受管容器(Linux)
- evidence: EV-0001
- 注:本轮未运行任何产品测试套件(只读静态复核);仓库自称的 "295 passed" 等结果未在本基线复现,不作为本轮证据(见 experiment_required)。

## Findings

### confirmed(有 file:line 证据,见 EVIDENCE_LEDGER EV-0004 起)
1. **问题一判定 B:部分抽象,Brazil 仍污染核心。** Pack 契约/loader/registry/机制层模型/Scope 冻结真实且国家无关;但 delivery release 认证门硬编码 brazil+OAB 域名并对非巴西法域直接 raise(delivery_assurance_service.py:536-541,618-619)、legal_rag.py:13-29 源标签表、document_extractor.py:337-347 Campinas 回退、legal_ingest.py:12 默认巴西语料路径、cold_start_service.py:904,978 默认 jurisdiction、rule_engine.py:435,459-500 拉美标题与 BYD demo 模板、intent_parser.py:15、main.py:85;brazil_connector/lexml 三件套未走 Pack 接口(api/legal.py:357)。
2. **问题二判定:非 BYD 倒推。** 规则适用为通用关键词评分(rule_engine.py:166-188,295-310);450/1000 从未作为数值门槛;Campinas 是合法城市 overlay(brazil_new_energy.json:556-560)。四个合成案例静态推演均走通用谓词。低危污染:抽取提示词 BYD few-shot 数字(document_extractor.py:51-92)、规则 JSON 触发词含 450/坎皮纳斯/比亚迪(brazil_new_energy.json:152,280,298,361,370,512,522)、legacy schema 默认 campinas(schemas/scenario.py:86-89)、前端 BYD placeholder(ScenarioCreateView.vue:51-58)。BYD 演示资产已隔离(is_demo、410 端点、隔离面板)。
3. **角色为三种**(business/legal/admin,core/roles.py:9-11),非四种;客户 UAT 由 scenario 所属 business 用户签署。
4. **材料块账本无内容哈希**:block_id 自由字符串,账本只锁状态转换不锁内容(models/mechanism.py:17-46)。
5. **事实抽取非国家无关**:中/葡硬编码正则+巴西化提示词(document_extractor.py:41-93,860-921);VALID_DIMENSIONS 仅 5 维,缺 data_compliance(document_extractor.py:25 vs rules 6 维)。
6. **冲突检测为占位演示**:硬编码 _PUBLIC_WATCH、非阻断、无测试(conflict_detection_service.py:20-40,57)。
7. **要件定向二次抽取是人工回补环**,无自动二次抽取;gap_explanation LLM 服务为死代码(scenario_pipeline.py:305 disabled_by_snapshot,无调用方)。
8. **检索为关键词优先**:无 pgvector/BM25/embedding 生产实现(legal_rag.py:117-134,162);与 ADR 口径一致。
9. **法规版本链无 rollback**:active/rejected 为终态,无 current 指针、无调度器、无 corpus 联动;registry 与语料 validity 双源不同步,废止仅在交付时阻断(legal_source_version_service.py:33-38;models/legal_source_version.py:17-23)。
10. **精确 bytes 靠冻结制品实现**,重渲染含 datetime.now 不确定(export_service.py:92,220;冻结与逐 bytes 重算 delivery_assurance_service.py:1154,2518)。
11. **交付链 fail-closed 且未发现绕过**:三导出端点统一过 _require_delivery_gate(api/scenarios.py:123-182,1577,1625,1675);四眼分离、原件 CAS、撤回传播、schema1.1 checkpoint 与测试齐备。
12. **交付时 eval 只验哈希与 regression_status 断言,不重算分数**;分数重算仅在 CI(legal_quality_eval + run_legal_quality_gate)。
13. **浏览器 E2E 仅覆盖 business 角色**(frontend/e2e/production-smoke.spec.ts);legal/admin 链路仅有 API/单元测试。
14. **步骤 6/7/8/13/15–25 为生产级 fail-closed 且有测试**(Scope 冻结、Pack 精确加载、事实确认、Claim/Coverage、复核定稿、Answerability、交付链)。

### potential(待动态验证的安全/正确性风险)
- 并发 partial unique 与撤回传播在 PostgreSQL 下的原子性(ai-review/README 亦列为待攻击项)。
- LegalSourceVersion 注册表与语料 validity 双源不同步的可利用窗口(废止后、交付前的草稿/简报呈现)。
- 材料块内容可在 block_id 不变下被替换(账本无内容哈希)对审计链的影响。
- 抽取提示词 BYD few-shot 数字的 priming 风险(有"不得编造"规则缓解,未定量评测)。

### experiment_required
- 在本基线运行后端全量 pytest、前端组件测试与构建、Alembic 升降级往返(一次性数据库)、legal quality gate,登记真实输出。
- PostgreSQL(非 SQLite)并发/事务实验(WS-4)。
- 四合成案例的动态(非静态)回归。

### blocked_external
- 两名真实巴西执业律师认证、场景签名、客户 UAT、客户环境三镜像/SBOM/provenance/probe、IdP/KMS/WORM、gold set 专家验收(与 docs/CUSTOMER_DELIVERY_ASSURANCE.md:97-107 一致;模型与门禁已实现,不得描述为已完成)。

## Unresolved Questions
1. "产品步骤 1–19" 的原始编号出处未在仓库中找到(README 为 5 步 Golden Path,操作手册为 8 步);本轮 Gap Matrix 采用任务书 27 步枚举映射,需用户确认口径。
2. WS-3 "四角色浏览器 E2E" 与代码三角色(business/legal/admin)的差异:第四角色是否指"客户 UAT 签署人"(当前由 business 承担)或需新增独立 customer 角色?
3. BYD 触发词清理(brazil_new_energy.json)会改变规则 artifact hash,进而影响历史快照/评测兼容——WS-1 需先冻结兼容策略。

## Next Exact Action
- 等待用户对本轮结论、Gap Matrix 与 WS-1~WS-10 的批准/修改意见;经批准后从 WS-1(BYD 解耦与稳定研究分母)开始,按"只读分析→冻结方案→批准→实施"执行,先运行 experiment_required 中的基线测试并登记证据。

## Stop Conditions
- 远端基线移动或工作树出现非授权改动 → 立即停止并报告。
- 任何操作将超出当前批准文件范围 → 停止。
- 本轮已输出完成 → 停止等待用户批准;不向 Draft 分支推送、不建 PR、不合并。
