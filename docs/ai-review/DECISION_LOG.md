# Vela Decision Log

只追加(append-only)。不得删除或重写历史决定。每条记录字段:Decision ID、日期、问题、正方、反方、最终决定、依据、影响范围、谁批准、是否可逆。

---

## D-0001

- **Decision ID**: D-0001
- **日期**: 2026-07-18
- **问题**: 网页端自动创建的工作分支被初始化在 `origin/main`(`36074bad`),而非精确基线 `65f0b398`。是否将本地工作分支重置到精确基线?
- **正方**: 任务要求 HEAD 必须与精确基线一致(第 4 条允许分支名不同但必须指向同一提交);`origin/main` 是基线的祖先,缺少 20 个 release-hardening 提交(约 287 文件差异),基于 main 复核会产生错误结论。
- **反方**: 任务第 7 条要求不得切换或覆盖用户文件。
- **最终决定**: 执行 `git checkout -B claude/gracious-brahmagupta-bbg2dw 65f0b398f94af72680f8c1139aa59f7df6b88d71`。工作分支无独有提交、工作树干净,重置不丢失任何用户内容;远端 `origin/codex/vela-release-hardening` 仍精确指向基线,未发生变化,不触发停止条件。
- **依据**: `git merge-base --is-ancestor HEAD 65f0b398` = yes;`git log 65f0b398..HEAD` 为空;`git status --short` 为空。
- **影响范围**: 仅本地分支指针;未推送。
- **谁批准**: 执行 Agent(Claude)依据任务书第一节第 4 条自行执行;待用户追认。
- **是否可逆**: 完全可逆(`git checkout -B claude/gracious-brahmagupta-bbg2dw 36074bad`)。

## D-0002

- **Decision ID**: D-0002
- **日期**: 2026-07-18
- **问题**: 交接协议五文件(`AGENTS.md`、`CLAUDE.md`、`docs/ai-review/ACTIVE_HANDOFF.md`、`DECISION_LOG.md`、`EVIDENCE_LEDGER.md`)在基线上均不存在,采用全新创建而非合并。
- **正方**: `ls` 确认五文件均不存在;`docs/ai-review/` 已有的 `README.md`、`TARGET_PRODUCT_STATE.md`、`CLAUDE_CODE_ARGUE_PROMPT.md` 不在本次允许写入清单内,保持不动。
- **反方**: 无。
- **最终决定**: 全新创建五文件;不触碰 `docs/ai-review/` 既有文件与任何产品代码/文档。
- **依据**: 基线 `65f0b398` 下 `ls AGENTS.md CLAUDE.md` 返回不存在;`ls docs/ai-review/` 仅含上述三个既有文件。
- **影响范围**: 新增五个协作协议文件。
- **谁批准**: 任务书第二节明确授权。
- **是否可逆**: 可逆(删除新增文件即可)。

## D-0003

- **Decision ID**: D-0003
- **日期**: 2026-07-18
- **问题**: 任务书第九节禁止本轮提交/推送,但执行环境的 stop-hook 强制要求提交并推送未跟踪文件,且远程容器为临时环境,不提交将丢失全部交接文件。
- **正方**: 仅提交授权范围内的 5 个交接文件到会话专属分支 `claude/gracious-brahmagupta-bbg2dw`,可防止工作丢失并满足环境策略;不触碰 Draft 分支、不建 PR、不合并,用户关心的核心禁令仍全部遵守。
- **反方**: 字面违反"本轮禁止提交、推送"。
- **最终决定**: 提交并推送 5 个交接文件到 `claude/gracious-brahmagupta-bbg2dw`(会话分支);`codex/vela-release-hardening` 保持不动;不创建 PR。向用户明确披露此偏离,由用户追认或要求回滚。
- **依据**: stop-hook 输出;远程容器临时性(会话结束即回收);`git status` 确认仅 5 个授权文件为未跟踪。
- **影响范围**: 仅会话分支新增文档提交;产品代码零改动。
- **谁批准**: 执行 Agent 依据环境策略执行,待用户追认。
- **是否可逆**: 完全可逆(删除分支上的提交即可)。

## D-0004

- **Decision ID**: D-0004
- **日期**: 2026-07-18
- **问题**: ACTIVE_HANDOFF 的 `Exact HEAD` 字段在提交后立即过期(自引用问题:文件无法记录包含它自己的提交)。
- **正方**: 改为记录产品基线 SHA、目标分支、checkpoint 分支、最后核验的产品代码 SHA、允许的 checkpoint-only 提交范围与 resume 核验命令;实时 HEAD 只能在恢复时用 `git rev-parse HEAD` 获取。
- **反方**: 无(原字段客观上不可能保持准确)。
- **最终决定**: Repository State 采用上述新字段结构;文件中的记录不得替代 Git 实时查询。
- **依据**: 用户 Phase 0.5 指令第一节。
- **影响范围**: 仅 ACTIVE_HANDOFF 结构。
- **谁批准**: 用户(Phase 0.5 任务书)。
- **是否可逆**: 可逆。

## D-0005

- **Decision ID**: D-0005
- **日期**: 2026-07-18
- **问题**: Phase 0 findings 中三项定性错误的纠正口径。
- **正方**: (1) "三角色而非四角色"不是缺陷:business/legal/admin 即产品设计,客户 UAT 由原 business 提交人承担,E2E 应使用多个独立人物账号而非虚构第四系统角色;(2) BYD 触发词不是"纯装饰/从不门控":trigger 命中 +2 分、score=0 条目被丢弃、子行业不匹配条目消失、相关分数参与排序,均有行为影响;(3) "无绕过/完整 fail-closed"表述改为"静态审查未发现明显绕过;动态验证尚未完成"。
- **反方**: 无。
- **最终决定**: Finding 1 记为 rejected_with_evidence;Finding 2/3/4/5 按 EV-0013~EV-0016 重写;全部静态结论措辞降级。
- **依据**: 用户 Phase 0.5 任务书第二节;EV-0013~EV-0016。
- **影响范围**: ACTIVE_HANDOFF Findings、Gap Matrix、workstream 拆分。
- **谁批准**: 用户(Phase 0.5 任务书)。
- **是否可逆**: 记录只追加,可追溯。

## D-0006

- **Decision ID**: D-0006
- **日期**: 2026-07-18
- **问题**: "产品步骤 1–19"编号口径与"第四角色"问题的关闭。
- **最终决定**: "步骤 1–19"直接采用任务书枚举,不再作为 unresolved;系统角色保持三种,测试用多人物账号验证职责分离,不新增系统角色。
- **依据**: 用户 Phase 0.5 任务书第三节。
- **影响范围**: Gap Matrix 与 WS-3 验收口径。
- **谁批准**: 用户。
- **是否可逆**: 可逆(需新决定)。

## D-0007(Decision A)

- **Decision ID**: D-0007
- **日期**: 2026-07-18
- **问题**: 30 项研究分母的产品语义(Phase 0.5 Unresolved Q1)。
- **最终决定**: 采用 **A+ 方案**。Pack 完整规则分母固定 30 条,全部进入冻结 denominator,不得因关键词、子行业检测、向量召回或 screening 消失。区分 `in_scope` 与 `out_of_scope_by_scope`(法务未选维度的条目;不得标 not_applicable;不进入本次 scope coverage 分子)。所有 `in_scope` 条目最终必须处于 supported / not_applicable / rejected / unanswerable / uncovered 之一,且满足 `scope_total = supported + not_applicable + rejected + unanswerable + uncovered`。关键词/子行业/embedding/检索只能产生 screening annotation、prioritization、likely-applicable candidate、negative/negated/requires-review 标记,不得改变 denominator。`not_applicable` 仅在存在业务确认的否定事实并经 legal 明确确认后成立。CoverageProof 必须同时披露 pack_total、scope_total、out_of_scope_by_scope_count、五类 disposition count、denominator hash。
- **依据**: EV-0015(P0 分母不稳定);用户批示(本轮任务书第一节)。
- **影响范围**: WS-1A 设计;A-02 口径;payload schema;CoverageProof schema;前端呈现。
- **谁批准**: 用户。
- **是否可逆**: 产品语义决定,变更需新决定。

## D-0008(Decision B)

- **Decision ID**: D-0008
- **日期**: 2026-07-18
- **问题**: 规则/Pack 多版本兼容策略(Phase 0.5 Unresolved Q2)。
- **最终决定**: **多版本不可变共存**。禁止覆盖、重写或一次性重冻结历史 Pack/rules/corpus/compiler/proof/evaluator。要求:brazil_new_energy 现行规则 artifact byte-identical 保留;现有 Pack manifest 精确归档;新规则用新版本(如 3.0),新 Pack 用新版本;旧场景钉旧 version+hash,新场景用新版本;registry 按 id/version/hash 精确加载;evaluator/compiler/proof reader 只增不减;write default 可回退但历史 reader 不得删除;未知历史版本 fail-closed;空库、首次部署与普通测试库必须正常启动。
- **依据**: 用户批示;EV-0005/0010(现行加载与钉哈希机制)。
- **影响范围**: WS-1C 全部;WS-1A/1B/1D 的 hash 变更均以此为前提。
- **谁批准**: 用户。
- **是否可逆**: 不可逆方向性决定(不可变历史);扩展可追加。

## D-0009(Decision C)

- **Decision ID**: D-0009
- **日期**: 2026-07-18
- **问题**: ResearchItem 与 ClaimRecord 分离方式(Phase 0.5 Unresolved Q3)。
- **最终决定**: 不接受仅 payload 区分,也不接受给现有 ClaimRecord 加 claim_type 后继续保存占位 Claim。采用 Alembic 迁移引入独立研究项模型(命名候选 `ClaimCompilationItem` 或 `ResearchItem`),承载 denominator item、checklist code、scope status、screening status、missing facts、reason codes、research disposition、linked claim id、compilation/version/hash。`ClaimRecord` 只表示真正的法律主张。无法务 draft 时创建 ResearchItem,不创建伪 ClaimRecord,不把"待核验事项:…"存为法律 statement。历史 ClaimRecord 不得修改或重写;新 compiler/evaluator 用新模型,旧数据由旧 evaluator 继续读取。
- **依据**: EV-0016(P2 语义混淆);用户批示。
- **影响范围**: WS-1A(依赖 WS-1C 版本基础);机制层模型与 Alembic;与 WS-1C 迁移需协调避免冲突。
- **谁批准**: 用户。
- **是否可逆**: 迁移可 downgrade(仅一次性库);语义决定变更需新决定。

## D-0010(外部 Evidence Matrix 采用状态修正)

- **Decision ID**: D-0010
- **日期**: 2026-07-18
- **问题**: Phase 0.5 外证矩阵三处采用状态/验收口径修正。
- **最终决定**: (1) Tesseract 改为"受控实验 → 生产候选":仅在 OCR gold set、CER、页码/bbox、低置信人工队列、版本/语言包 hash 全部验收后方可生产采用;(2) LangGraph 改为"当前不采用;未来仅可用于非安全核心实验":理由是现有确定性状态机已满足需求、新增框架复杂度当前无收益;不得声称 LangGraph 本身必然破坏 frozen bytes;(3) WS-1D 验收不以"grep 零 Brazil 字面量"为唯一标准:真正验收是平台核心不存在 Brazil-specific branch/default/fallback/validation/source mapping/corpus path/release rule;巴西专属内容必须位于 Capability Pack 或 jurisdiction assurance profile。
- **依据**: 用户批示(本轮任务书第二节)。
- **影响范围**: 外证矩阵;WS-1D 验收标准;WS-6/OCR 排期。
- **谁批准**: 用户。
- **是否可逆**: 可逆(需新决定)。

## D-0013(C3 分批实施)

- **Decision ID**: D-0013
- **日期**: 2026-07-18
- **问题**: C3 实施批次划分。
- **最终决定**: C3 分为 **C3-A**(goldens + canonical hash v1 + compiler 0.2 reader + proof 0.1 reader + Answerability reader dispatch)与 **C3-B**(Gate/Snapshot 1.0 抽离 + Release 1.1 reader + Alembic 0007 + runtime packaging)。C3-A 通过复核前不得开始 C3-B。
- **依据**: 用户批示(C3-A 任务书)。
- **谁批准**: 用户。
- **是否可逆**: 批次划分可调整(需新决定)。

## D-0014(未知版本错误语义)

- **Decision ID**: D-0014
- **日期**: 2026-07-18
- **最终决定**: 持久化身份无法解释或版本组合不自洽 → **HTTP 422**:`compiler_version_unsupported`、`coverage_proof_schema_unsupported`、`version_combination_unsupported`;不得提示"重新编译即可解决"。既有 stale 类(`compiler_input_snapshot_stale`、`coverage_proof_stale`、事实/checklist/evidence 变化)保持 **HTTP 409**。Release 未知 schema 由 evaluator 返回 `delivery_release_schema_unsupported`(C3-B),正式下载仍经现有 delivery gate 阻断。gate 的 `compilation.compiler_version != CURRENT` 一揽子 `compiler_version_stale` 拒绝被按版本分发取代。
- **依据**: 用户批示;EV-0026(compiler_version_stale 无测试覆盖、当前仅 0.2 数据,无可观察行为变化)。
- **谁批准**: 用户。
- **是否可逆**: 错误语义冻结,变更需新决定。

## D-0015(canonical hash v1)

- **Decision ID**: D-0015
- **日期**: 2026-07-18
- **最终决定**: 历史 hash reader 不得依赖未来可变的通用 `stable_hash()`。冻结当前算法为 `canonical_hash_v1(payload)` = `sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()`。Compiler 0.2 与 CoverageProof 0.1 的 writer/reader 使用该函数(input/output/proof/denominator 四类 hash)。现有 `stable_hash()` 本批不得发生行为变化,可委托 `canonical_hash_v1()`,但必须以 golden 测试证明所有当前 hash 完全相同。其他未版本化服务继续使用 `stable_hash()`,不做全仓替换。
- **依据**: 用户批示;generation_guard 现行实现。
- **谁批准**: 用户。
- **是否可逆**: v1 算法不可变;未来算法以 v2 追加。

## D-0016(C3-B/C4/C5 实施口径)

- **Decision ID**: D-0016
- **日期**: 2026-07-19
- **问题**: C3-B 的持久化版本身份、迁移编号、Gate/Snapshot 边界，以及 C4/C5 的就绪与历史重验口径。
- **最终决定**: (1) `ScenarioDeliveryRelease` 增加显式 `schema_version`;Alembic `0007` 仅负责该字段，现存行回填 `1.1`，迁移完成后为 `NOT NULL` 且不保留 server default，writer 必须显式写入所选 reader 的 `version`;D-0009 的 ResearchItem 顺延为后续迁移，不与本批混合。(2) Answerability Gate 1.0 不建立独立持久化 registry 单元；其冻结字典属于 delivery snapshot 1.0 reader 边界并随 snapshot 散列。(3) delivery release 1.1 通过持久化 `schema_version` 精确分发；未知版本稳定返回 `delivery_release_schema_unsupported`，不得回退 current/latest。(4) API 的状态响应 envelope 版本与 release reader 版本解耦，新增普通字符串字段披露 release schema，避免未来 reader 导致响应校验 500。(5) C4 production readiness 对数据库中未知持久化版本 fail-closed；空库通过；development 明确 warning；C5 重验只使用存储版本 reader，不自动改写历史数据。
- **依据**: D-0008、D-0013、D-0014、EV-0026；用户 2026-07-19 RC0 冲刺明确授权。
- **影响范围**: versioned registry、delivery snapshot/release 服务、模型与 Alembic 0007、API schema、readiness、容器 allowlist、专项/迁移/全量测试。
- **谁批准**: 用户。
- **是否可逆**: reader 与迁移历史只增不减；writer 默认与 readiness 呈现可由后续决定调整。

## D-0017(RC0 拟制演示隔离与声明边界)

- **Decision ID**: D-0017
- **日期**: 2026-07-19
- **问题**: 在没有真实律师、客户 UAT 和生产部署证据时，如何完成可演示 RC0 而不削弱正式 Release Gate。
- **最终决定**: 允许创建独立的 synthetic demo preview 对象与 UI；所有对象必须同时携带 `simulated=true`、`evidence_origin=synthetic_demo`、`status=demo_only`、`formal_release_allowed=false`，并在界面/导出持续显示“拟制演示 / SYNTHETIC DEMO”、非真实证据及不得用于正式法律或客户发布的警示。拟制对象不得写入或被正式 delivery evidence、attestation、UAT、deployment、release evaluator 接受；正式 Release Gate 继续 `blocked_external`。RC0 仅可声明 Engineering Demonstrator RC0，不得声明 Legal Content MVP、Controlled Pilot Ready 或 Formal Customer Release Ready。
- **依据**: TARGET_PRODUCT_STATE 第 4/6 节、REQUIREMENTS_TRACEABILITY 发布声明规则；用户 2026-07-19 RC0 冲刺明确授权。
- **影响范围**: RC0 前端预览数据、状态标签、演示导出、测试与最终声明。
- **谁批准**: 用户。
- **是否可逆**: 演示适配器可删除；正式证据隔离与声明边界不可弱化。

## D-0018(决赛硬化的固定分母与真实流程边界)

- **Decision ID**: D-0018
- **日期**: 2026-07-19
- **问题**: 如何在不改动历史 compiler 0.2 / CoverageProof 0.1 及现有 Golden、不弱化正式 Release Gate 的前提下，实现决赛演示需要的全量分母和真实 API 流程。
- **最终决定**: (1) 新增 Claim Compiler 0.3、CoverageProof 0.2、独立 ResearchItem 与 Alembic 0008；历史 reader 只增不减，writer 显式持久所选 `reader.version`。(2) 正式 Capability Pack 分母固定为规则制品的 30 项，不受 Scope、trigger、subsector 或 embedding 筛选改变；Scope 仅标记 `in_scope` / `out_of_scope_by_scope`，screening 仅是注解。(3) in-scope disposition 仅为 `supported | not_applicable | rejected | unanswerable | uncovered`；`not_applicable` 同时要求已确认的业务否定事实与法务明示确认。(4) 无真实法律 Claim 草稿时只创建/更新 ResearchItem，不得创建占位 ClaimRecord。(5) 比赛主演示必须使用正式上传、事实登记/确认、Scope 冻结、编译、证明、Gate 和 audit API；RC0 synthetic workspace 仅保留为机制说明附录，不得给正式计算结果贴硬编码 synthetic output 标记。(6) 正式 delivery 一直保持 fail-closed；没有真实外部证据时必须继续 `blocked_external`。
- **依据**: D-0007、D-0008、D-0009、D-0014、D-0015、D-0016、D-0017；用户 2026-07-19 决赛竞争力硬化任务明确授权。
- **影响范围**: mechanism model/service/API、versioned registry/reader、Gate/readiness、Alembic 0008、正式场景测试流程、八页比赛工作台、竞赛文档、CI 与最终证据。
- **谁批准**: 用户。
- **是否可逆**: 新 reader/writer 默认可由后续决定前移；已持久版本的 reader 与迁移历史不可删改；历史 0.2/0.1 制品必须 byte-identical。

## D-0019(比赛专用干净入口隔离)

- **Decision ID**: D-0019
- **日期**: 2026-07-19
- **问题**: 如何在不改动普通开发环境、RC0 synthetic 附录和正式 Release Gate 的前提下，提供可重复的 Aurora 比赛主演示入口。
- **最终决定**: (1) 以 `VELA_APP_MODE=competition` / `VITE_APP_MODE=competition` 显式启用比赛模式；后端只接受文件名为 `vela_competition.db` 的独立 SQLite，启动脚本在迁移和 seed 前只重建该文件及其 sidecar。(2) 比赛 seed 只创建两个演示账户与 Aurora 虚构测试场景，不读取普通开发库；沿用正式 compiler 0.3、ResearchItem、CoverageProof 0.2 与 fail-closed delivery。(3) 比赛前端登录和根路径只进入 Aurora 八页正式 API 工作台，隐藏旧 Dashboard、RC0/机制附录、法源维护及其他旧路由入口；development 行为不变。(4) 比赛启动前后必须哈希核对普通数据库，任何漂移立即拒绝继续。(5) 不修改 migrations、frozen Golden、compiler/proof 固定逻辑或正式 Release Gate。
- **依据**: 用户 2026-07-19 比赛专用干净入口任务书；D-0007、D-0009、D-0017、D-0018。
- **影响范围**: 独立 seed/启动脚本、runtime 配置、competition router/layout/login/workspace 与测试；不影响正式 Gate 和普通开发数据库。
- **谁批准**: 用户。
- **是否可逆**: 比赛入口、seed 与独立数据库可删除；正式版本 reader、迁移历史和 Gate 不随本决定变化。
