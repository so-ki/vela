# Vela Active Handoff

## Repository State
- Product baseline SHA: 65f0b398f94af72680f8c1139aa59f7df6b88d71
- Target base branch: codex/vela-release-hardening(不得直接推送)
- Checkpoint branch: claude/gracious-brahmagupta-bbg2dw(仅承载交接文件提交)
- Last verified product-code SHA: 65f0b398f94af72680f8c1139aa59f7df6b88d71(产品代码与基线零差异;checkpoint 分支上的提交只触碰下列允许文件)
- Allowed checkpoint-only commits: 仅 `AGENTS.md`、`CLAUDE.md`、`docs/ai-review/ACTIVE_HANDOFF.md`、`docs/ai-review/DECISION_LOG.md`、`docs/ai-review/EVIDENCE_LEDGER.md`
- Resume 时必须执行的 Git 核验命令:
  ```
  git status --short
  git branch --show-current
  git rev-parse HEAD
  git fetch origin
  git rev-parse origin/codex/vela-release-hardening        # 必须 = 65f0b398...
  git diff --stat 65f0b398f94af72680f8c1139aa59f7df6b88d71 HEAD  # 差异必须仅含上述 5 个允许文件
  ```
- 注意:Git 的实时 HEAD 只能在恢复时通过 `git rev-parse HEAD` 获取;本文件不记录、也不得用文件记录替代 Git 实时查询(D-0004)。

## Current Phase
- Phase: Phase 0.5 — 纠错与外部证据核验(只读)——已完成,等待用户批准
- Workstream: 总控复核(未进入任何实施 workstream)
- Status: complete_pending_approval
- Allowed file scope: 仅上述 5 个交接文件
- Prohibited actions: 修改产品代码/规则/语料/迁移/测试/产品文档/UI;推送 Draft 分支;创建或合并 PR;主动安全实验

## Frozen Product Definition
- 见 `AGENTS.md` 第 2–4 节;`docs/REQUIREMENTS_TRACEABILITY.md` 与 `docs/ai-review/TARGET_PRODUCT_STATE.md` 为既有冻结口径。
- 补充口径(D-0006):系统角色固定为 business/legal/admin 三种;客户 UAT 由原 business 提交人承担;E2E 用多个独立人物账号验证职责分离,不虚构第四系统角色。"产品步骤 1–19"指任务书流程枚举的第 1–19 步(身份→Answerability Gate,在线协查链);20–27 为交付与外部证据链。

## Approved Decisions
- D-0001(分支校正到精确基线,已获用户追认)、D-0002(五文件全新创建)、D-0003(交接文件提交推送到独立 Claude 分支,已获用户追认;不授权提交产品代码)、D-0004(Repository State 不记录实时 HEAD)、D-0005(Phase 0 findings 纠正口径)、D-0006(步骤编号与角色问题关闭)。

## Work Completed
- Phase 0:基线核验、交接协议建立、四路只读复核(见 EV-0001~EV-0012)。
- Phase 0.5:(1) HEAD 自引用修复(本节新结构);(2) Findings 1–6 纠正(EV-0013~EV-0016,D-0005);(3) 外部证据核验完成:21 项全部经当日(2026-07-18)实际访问原始来源,结果与未核验残留见 EV-0017 与本轮报告;(4) WS-1 拆分为 WS-1A~WS-1E。

## Files Changed
- 仅上述 5 个交接文件;产品代码/规则/语料/迁移/测试/产品文档/UI:零改动。

## Tests and Commands
- command: `git fetch origin && git rev-parse origin/codex/vela-release-hardening`
- result: 65f0b398...(与产品基线一致)
- environment: 远程受管容器(Linux),出网经代理
- evidence: EV-0001
- 注:本轮仍未运行任何产品测试套件;所有代码结论为静态复核。仓库自称测试数不作为本轮证据。

## Findings

### rejected_with_evidence
- R1【原 Phase 0 finding "三角色而非四角色是缺陷"】:产品系统角色本来就是 business/legal/admin 三种(core/roles.py:9-11);客户 UAT 由 scenario 所属 business 用户签署是设计而非缺陷。E2E 须用多个独立人物账号验证职责分离,但不得虚构第四种系统角色。(D-0005)

### confirmed(P0)
- C1【在线研究/覆盖分母不稳定且缩减不可见】(EV-0015):规则文件恰有 30 条,但仅 5 条 always_include;25 条依赖触发词命中(score=0 即消失,rule_engine.py:180-181),其中 8 条再受子行业门控(:334),全部受法务选维过滤;Claim/CoverageProof 分母 = 生成后 payload 子集(mechanism_service.py:202-211),被过滤条目永不进入覆盖记账。措辞不同但法律等价的项目获得不同分母。稳定 30 分母仅存在于离线 CI 评测(legal_quality_eval.py:228-244)。A-02"30 项稳定生成"与在线代码不一致。

### confirmed(P1)
- C2【BYD 触发词具有真实行为影响】(EV-0013,修正 Phase 0 "纯装饰/从不门控"的错误定性):trigger 命中 +2 分并参与排序(:387-394);"450"(LAB-001/LAB-005)、"1000"(IND-005/IND-006 触发词,且是 electric_bus 子行业关键词)、"比亚迪"(FOR-004)、"坎皮纳斯"(LAB-003/TAX-003)均能改变 checklist 组成与排序;corpus 含 str(employee_count)(:306),子串语义下 "1450" 含 "450"。
- C3【否定语义缺失,confirmed bug】(EV-0014):detect_sub_sectors 纯子串匹配(:250-253),"不生产电池/不涉及任何电池生产或包装活动/设备供应给电池厂但本项目不生产电池/未说明是否生产电池"四种表述全部误判 battery_pack,连带电池条目进入评分;泛化关键词("系统"→energy_storage、"1000"→electric_bus、"回收/防火"→battery_pack)扩大误判面。
- C4【交付认证门硬编码巴西法域】(EV-0004):delivery_assurance_service.py:536-541,618-619;第二法域无法完成认证/release。
- C5【平台核心残留巴西字面量】(EV-0004 附):legal_rag/brief_generator 源标签表、legal_ingest 默认语料路径、document_extractor Campinas 回退与巴西化提示词、intent_parser、main.py、cold_start、rule_engine 拉美标题;brazil_connector/lexml 未走 Pack 接口。
- C6【事实抽取非国家无关;VALID_DIMENSIONS 缺 data_compliance】(EV-0009)。
- C7【法规版本链无 rollback、无唯一 current、无调度;registry 与语料 validity 双源不同步】(EV-0011);废止在生成侧靠语料 validity、交付侧靠 _active_legal_changes_after,草稿/简报窗口存在呈现风险(potential)。
- C8【材料块账本无内容哈希】(EV-0009):block_id 自由字符串,内容可在 ID 不变下替换。

### confirmed(P2)
- C9【research/legal claim 语义混淆】(EV-0016):无 draft 条目以 `待核验事项:…` 占位文案存为 ClaimRecord.statement,模型无 claim_type 区分;缓解:此类记录必然 refused,不可能升级 supported;风险为"尚未研究"与"法务拒答"在 CoverageProof.uncovered 与审计视图中不可区分。不得把该占位文案描述为"法务提出的法律主张"。
- C10【冲突检测为非阻断占位、无测试;gap_explanation LLM 死代码;抽取 few-shot 含 BYD 数字(priming 未定量);legacy schema 默认 campinas;前端 BYD placeholder】(EV-0008/0009)。
- C11【浏览器 E2E 仅覆盖 business;bytes 重现靠冻结制品;交付时 eval 只验哈希不重算分数】(EV-0012)。

### 静态结论措辞(D-0005)
- 交付链、Scope 冻结、Pack 加载、Claim/Coverage、Answerability 等处的结论一律表述为:**"静态审查未发现明显绕过;动态验证尚未完成。"** 不得表述为"无绕过路径/已完整 fail-closed"。

### potential(待动态验证)
- PostgreSQL 并发 partial unique 与撤回传播原子性;registry-语料不同步的呈现窗口;块内容替换对审计链影响;few-shot priming 定量。

### experiment_required
- 本基线全量后端 pytest、前端组件测试与构建、Alembic 升降级往返(一次性库)、legal quality gate;PostgreSQL 并发/事务/重放/raw-SQL/资源实验;四合成案例(含否定用例)动态回归;全角色浏览器 E2E。

### blocked_external
- 两名真实巴西律师认证、场景签名、客户 UAT、客户环境三镜像/SBOM/provenance/probe、IdP/KMS/WORM、gold set 专家验收(内部逻辑已实现,外部证据为零,不得描述为已完成)。

## External Evidence Verification(2026-07-18,全部访问原始来源;详表见本轮报告与 EV-0017)
- 生产采用(直接):LexML URN 标准(Pack 内法源 ID);Shepard's 型 citator 数据模型思想(类型化处理边/要点级锚定/信号可归因,数据不可复制);LegalRuleML 概念核对表(规则 schema 完备性检查);Tesseract(扫描件 OCR,Apache-2.0,可钉版本)。
- 实验→生产候选:in-toto+cosign(交付证据链外部化);Promptfoo(CI 评测层);Docling(抽取前置层,provenance);strict 结构化输出(Claude/GPT/Gemini/DeepSeek 四家官方 GA,用于事实抽取,模型 ID+schema 冻结入制品)。
- 受控实验:BGE-M3 / Qwen3-Embedding / pgvector(嵌入路线,门禁路径保持确定性检索);LegalBench/LegalBench-RAG(评测形态,字符区间级 gold);lexml-linker(GPL-2.0 须容器隔离);br-eli-mcp(存在,v0.7.1,0 star 单人维护,仅离线辅助);RAGChecker(仅诊断报表,永不进门禁)。
- 拒绝采用:LangGraph(官方不承诺确定性重放);GraphRAG 自动图构建(微软 RAI 文档自证需逐条人工验证,法律效力关系只能人工/规则维护);RefChecker(2026-04-08 已归档);STARA(闭源,方法论借鉴其"研究分母"评测设计);CoCounsel/Lexis+AI/Vincent 产品与数据(设计模式对标;Vincent 官方确认覆盖巴西但州/市级深度未披露)。
- 未核验残留(不得当事实用):Qwen3.7-Max 1M 上下文与 strict schema 文档;BGE-M3 葡语逐项列名;in-toto↔SLSA 官方关系表述;各厂商营销数字;CoCounsel 巴西覆盖;Vincent 州/市级深度;LegalBench/lexml-linker 最后提交日期;projeto.lexml.gov.br 根页(503)。

## Unresolved Questions(真正需要用户决定)
1. 【WS-1A 前置】30 项研究分母的产品语义:A 方案——在线也输出全量 30 分母,逐项标注 applicable/not_applicable/not_researched,Claim/Coverage 记账覆盖全部 30;B 方案——保持"生成子集为适用子集",但把被过滤条目显式记入 CoverageProof(如 not_applicable 及其原因),使缩减可见。两案都消除 P0 的"缩减不可见",选择影响 A-02 口径、payload schema 与前端。
2. 【WS-1C 前置】规则/Pack 多版本兼容策略:双版本共存(registry 注册多版本,旧场景钉旧 hash)vs 一次性重冻结(历史快照标旧版,新场景一律新版)。影响历史场景重现与 evaluator 口径。
3. 【WS-1A 范围】ClaimRecord 增加 claim_type(research_item/legal_claim)需要 Alembic 迁移(触碰机制层模型);是否授权纳入 WS-1A,还是先用 payload 层区分(无迁移)。

## Next Exact Action
- 等待用户:(1) 批准修正后 findings 与 Gap Matrix;(2) 回答上述 3 个 unresolved;(3) 批准 WS-1A~WS-1E 拆分与顺序(建议 WS-1C → WS-1A/WS-1B → WS-1D → WS-1E)。获批后第一步仍是运行 experiment_required 基线测试并登记证据,再进入获批 workstream 的"只读分析→冻结方案→批准→实施"。

## Stop Conditions
- 远端基线移动、产品代码出现非授权改动、或操作将超出 5 个允许文件 → 立即停止并报告。
- 本轮输出完成 → 停止等待批准;不修改产品代码、不推送 Draft 分支、不建 PR、不合并。
