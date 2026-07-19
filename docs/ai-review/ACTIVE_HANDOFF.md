# Vela Active Handoff

## Repository State
- Product baseline SHA: 65f0b398f94af72680f8c1139aa59f7df6b88d71
- Target base branch: codex/vela-release-hardening(不得直接推送)
- Checkpoint branch: claude/gracious-brahmagupta-bbg2dw(仅承载交接文件提交)
- Claude handoff source: `origin/claude/vela-ws-1c-c3a-versioned-readers` = `00b47bc89f11aa5a8eaaf38dae18565e8fd07274`(Codex 接管时已 fetch 核验)
- Codex integration branch: `codex/vela-mvp-integration`(从上述精确交接点创建;不得自动合并或推送 Draft 分支)
- RC0 sprint branch: `codex/vela-rc0-sprint-20260719`(从可信 C3-A.2 交接提交 `33d8fe1cfdfebb2bdd4066f7aa4b49658d6ce16e` 创建并已推送；不得触碰占用旧 integration 分支的 worktree)
- Finalist hardening branch: `codex/vela-finalist-hardening-20260719`(从精确 RC0 提交 `14e3cd395cccfe2218b8013a448a137b881a9860` 创建并已推送空恢复点；本轮唯一可写分支)
- Last verified implementation SHA: `b2c1be62d52bdda6b18aac31cbd548f7efaa946c`(Finalist P0-1~P0-5 实现与精确 SHA CI 全绿；交接文件实时 HEAD 仍须按 D-0004 查询)
- Allowed commits: 5 个交接文件 + 经批准的 WS-1C 产品提交(C1/C1.1/C2/C2.1/C3-A/C3-A.1/C3-A.2/C3-B/C4/C5) + RC0 synthetic preview UI、测试、研究账本、截图与验证证据
- Resume 时必须执行的 Git 核验命令:
  ```
  git status --short
  git branch --show-current
  git rev-parse HEAD
  git fetch origin
  git rev-parse origin/codex/vela-release-hardening        # 必须 = 65f0b398...
  git diff --stat 33d8fe1cfdfebb2bdd4066f7aa4b49658d6ce16e HEAD  # 差异只允许:本轮批准的 C3-B/C4/C5、RC0 UI、测试与证据
  ```
- 注意:Git 的实时 HEAD 只能在恢复时通过 `git rev-parse HEAD` 获取;本文件不记录、也不得用文件记录替代 Git 实时查询(D-0004)。

## Current Phase
- Phase: Vela 决赛竞争力硬化——工程 Green Gate 完成
- Workstream: WS-1C(C1、C1.1、C2、C2.1、C3-A/C3-A.1/C3-A.2 已独立复核批准；C3-B/C4/C5 已获本轮明确实施授权)
- Status: finalist_hardening_engineering_verified
- 分支说明: `codex/vela-rc0-sprint-20260719` 从已复核交接提交 `33d8fe1` 建立；旧 `codex/vela-mvp-integration` 与其占用 worktree 保留为历史恢复点且禁止操作
- 外部状态: 法律认证、真实客户 UAT、客户生产部署证据继续为 `blocked_external`,工程测试不得升级这些状态
- 分支说明: C2 在独立分支 `claude/vela-ws-1c-c2-real-archive`(基于 C1.1 提交 730b9fd);checkpoint 分支 `claude/gracious-brahmagupta-bbg2dw` 停在 C1.1
- Allowed file scope(Finalist): D-0018 所需 compiler 0.3、proof 0.2、ResearchItem、Alembic 0008、registry/readiness/Gate、正式 API 流程、比赛工作台、竞赛文档、测试、CI 与证据。
- Prohibited actions: 改动 frozen compiler 0.2 / proof 0.1 / 现有 Golden；伪造律师、客户或生产证据；使正式流程依赖硬编码输出；弱化 Gate；创建正式 Release；合并 Draft；修改/删除历史分支或它们的 worktree。

## Frozen Product Definition
- 见 `AGENTS.md` 第 2–4 节与 D-0006;产品语义新增冻结决定:**D-0007(分母 A+ 方案)、D-0008(多版本不可变共存)、D-0009(ResearchItem 与 ClaimRecord 分离)、D-0010(外证矩阵采用状态修正)**——以 DECISION_LOG 原文为准,不得再列为 unresolved。

## Approved Decisions
- D-0001~D-0006(见前);**D-0007 分母 A+**(30 条全量冻结分母,in_scope/out_of_scope_by_scope,五类 disposition,screening 不改分母,CoverageProof 披露 pack_total/scope_total/out_of_scope_by_scope_count/五类计数/denominator hash);**D-0008 多版本不可变共存**(历史 artifact byte-identical 保留、新版本递增、reader 只增不减、未知版本 fail-closed、空库可启动);**D-0009 独立 ResearchItem 模型**(Alembic 迁移,无 draft 不再造伪 ClaimRecord);**D-0010**(Tesseract→受控实验→生产候选;LangGraph→当前不采用、未来仅非安全核心实验、不得声称其必然破坏 frozen bytes;WS-1D 验收=平台核心无 Brazil-specific branch/default/fallback/validation/source mapping/corpus path/release rule,非 grep 字面量)。

## Work Completed
- Phase 0 / 0.5:见前轮(EV-0001~EV-0017)。
- Phase 0.6:(1) D-0007~D-0010 落账;(2) **基线动态验证首次通过**(EV-0018):靶向 35 passed、全量后端 295 passed、compileall、前端 29 passed + 构建、发布边界、git diff --check,全部绿,Python 3.12.3(未用系统 3.11);(3) WS-1C 设计前提事实采集(EV-0019);(4) WS-1C 实施方案冻结(见下节)。
- C3-A.2(EV-0029):draft 引用、ClaimRecord 三个 JSON 字段及 CoverageProof 0.1 嵌套元素全部在 frozen reader 前按 `list[str]`/对象结构校验;非法形状即 422,新增 13 个对抗测试;全量后端 **393 passed**;四个 golden raw SHA 不变。
- RC0 接管(2026-07-19):用户确认 C3-A.2 已独立复核批准；独立分支从 `33d8fe1` 创建并推送；Draft 仍为 `65f0b398`;Python 3.12 指定基线 73 passed、前端组件 29 passed。
- C3-B(提交 `1e4bc79`):冻结 delivery snapshot / Answerability Gate 1.0 与 release 1.1 reader；release 按持久化 `schema_version` 精确分发；Alembic 0007 回填 1.1、NOT NULL、无永久 server default；unknown schema 正式路径 fail-closed；API envelope 与 reader 版本解耦。
- C4/C5(提交 `8ceaff3`、`c8328b4`):新增只读 `/api/v1/readiness` 与启动审计；空库 ready、development warning、production unknown-version blocked；历史 evaluator 只用存储版本 reader；新增升级/恢复/回滚手册与需求追踪。
- RC0 UI(提交 `360ab8b`、`4ea1dfc`):八页原创拟制工作台、持久上下文栏、法律研究三栏、九阶段交付链、审计时间线、八类非 happy-path；所有嵌套拟制对象递归携带四元组，正式 Release 保持 `blocked_external`。
- Final validation(2026-07-19):Python 3.12.13 专项 98 passed、全量后端 404 passed；前端 34 passed + production build；SQLite 0006→0007→0006→head/fresh head/backfill/NOT NULL/no-default/unknown downgrade guard；release boundaries、compileall、Ruff、git diff、四个 frozen golden SHA 全通过；浏览器八页 desktop/mobile smoke 与控制台检查通过。
- Finalist P0-1/P0-2(提交 `fc1c3e2`,`92c60db`,`e89d337`):compiler 0.3 固定 30 项、proof 0.2 disposition 守恒、ResearchItem/Claim 分离、Alembic 0008、版本 registry/readiness/Gate 边界与 live scenario API 八页工作台完成；关键事实变化导致真实 input/output hash 变化；正式 delivery 保持 `blocked_external`。
- Finalist P0-3/P0-4(提交 `d5fe2de`):唯一定位口径、allow/block list、五表面禁语扫描与显式 estimate/hypothesis 商业模型完成。
- Finalist P0-5(EV-0036):精确实现 SHA `b2c1be62d52bdda6b18aac31cbd548f7efaa946c` 的 GitHub Actions <https://github.com/so-ki/vela/actions/runs/29681515075> 全绿；backend 412 passed、frontend 36 passed、API/release boundary、CVE/SBOM、PostgreSQL 16.14、0008 downgrade/re-upgrade、生产 Compose、business/legal/admin E2E 与 readiness 全通过。

## WS-1C Frozen Plan(v1,历史记录；完成状态以上文为准)
- **核心结论**:采用**文件系统不可变归档 + 代码级 reader 版本注册表,零 Alembic 迁移**。不建 DB 版本表(与现行"文件系统为 Pack 事实源"一致,并把 Alembic 0007 让给 WS-1A 的 ResearchItem,避免迁移冲突)。
- **归档布局**:新增 `backend/app/capability_packs/archive/<pack_id>/<pack_version>/`,内含 byte-identical 的 manifest.json 与其引用的 rules/corpus JSON(自包含);loader 对 archive manifest 以"manifest 所在目录"为资源解析根,active pack 仍用现行 app/rules、app/data 根(不动现有文件)。
- **registry**:`_all()` 不变(archive 永不 active、不进 list_active/list_public_active);新增 `_archived()` 扫描与 `list_versions(pack_id)`;`get_exact(pack_id, version, semantic_hash)` 先查 active,失配再查 `archive/<pack_id>/<version>/`,加载时全量哈希重验且 `semantic_hash` 必须相等;未知版本抛 `CapabilityPackNotFoundError`(fail-closed,不回退)。
- **reader 版本注册表(只增不减)**:compiler `{"0.2": v02_builder}`、proof body `{"0.1": v01_builder}`、release body `{"1.1": v11_builder}`、gate 按存储的 compiler_version 分发;`CURRENT_*` 常量仅供 writer;未知存储版本 → 新增 reason code(如 `compiler_version_unsupported`/`delivery_release_schema_unsupported`)fail-closed。write-default 可回退为旧常量,历史 reader 条目禁止删除(由枚举测试守护)。
- **startup 扫描**:advisory 模式——启动时扫描 DB 中 distinct pack 身份(scenario_scope snapshot)与 compiler_version,对照 registry 可解析性,产出报告/健康端点;不因个别未知版本阻断启动(空库/首次部署必须可启动),**使用时**对未知版本仍硬 fail-closed。
- **byte-identity 证明**:归档创建 = 复制现文件 + sha256 对照 manifest 常量(rules 2.9=351c7d6f…62c9c、corpus 1.13=b91783bc…c787f、semantic dd26e226…808b)+ 专项测试断言;哈希登记 EVIDENCE_LEDGER。
- **commit 计划**(每个可独立 revert):C1 registry/loader 归档发现+get_exact 回退+测试;C2 生成 1.3.1/2.9/1.13 归档+byte-identity 测试;C3 消费方版本注册表+未知版本 fail-closed+测试;C4 startup advisory 扫描+测试;C5 相关文档同步。
- **测试矩阵**:旧场景经归档重现(active 升 3.0 后)、新场景用新版、write-default 回退、未知版本 fail-closed、空库/首次部署/SQLite 测试库启动、fixtures 不受影响、archive 不进 active 列表、路径遍历安全、release boundary 脚本对 archive 的允许清单。
- **风险**:release_safety/Docker COPY 允许清单需纳入 archive;legal_quality_eval 硬编码路径绕过 registry(加只增参数,后续提交);rules_registry 传统路径与 material fields 耦合需实施时确认;前端 pack 身份相等校验对归档场景的呈现留给 WS-2。
- **与 WS-1A 协调**:WS-1C 零迁移;WS-1A 用 Alembic 0007(research_items),其新 compiler "0.3" 作为新 writer 注册进 WS-1C 注册表,无迁移冲突。
- **ultracode 建议**:WS-1C 实施本身**不建议**进入 ultracode(范围收敛、提交线性、测试脚手架强);建议 WS-1A(模型+迁移+双版本 compiler)与 WS-5(对抗验证)采用多代理编排。

## Files Changed
- WS-1C/C1 产品提交:`backend/app/capability_packs/registry.py`(修改)、`backend/app/capability_packs/version_index.py`(新增)、`backend/tests/test_capability_pack_version_archive.py`(新增)。
- WS-1C/C3-A.2 产品提交:`backend/app/services/answerability_gate_service.py`、`backend/tests/test_versioned_payload_validation.py`。
- C3-B/C4/C5:delivery snapshot/release frozen readers 与 registry、`ScenarioDeliveryRelease.schema_version`、Alembic 0007、readiness service/API/startup audit、migration/readiness/revalidation/release-safety tests、运维手册与需求追踪。
- RC0 UI:`frontend/src/demo/rc0SyntheticCase.ts`、`Rc0WorkspaceView.vue`/spec、`Rc0StatePanel.vue`、`styles/rc0.css`、router/layout 入口、`docs/ui/UI_RESEARCH_LEDGER.md` 与 `docs/ai-review/screenshots/`。
- 交接文件:5 个(持续更新)。
- 冻结不变量:frozen v0_2/v0_1 readers、四个 goldens、active manifest、生产 rules/corpus 与 archive 内容未改；ResearchItem 已通过独立模型与 Alembic 0008 实现，不复用 ClaimRecord。

## Tests and Commands(本轮,EV-0018)
- environment: 远程受管容器 Linux;Python 3.12.3(uv venv,scratchpad;未用系统 3.11);Node v22.22.2;npm 10.9.7;Docker 29.3.1
- 靶向 6 文件 pytest → 35 passed(32.11s);`python -m compileall -q app tests` → 通过;全量 `pytest tests -q` → **295 passed**(73.70s);`npm ci` + `npm run test:components` → 29 passed;`npm run build` → 成功(3.62s);`bash scripts/check_release_boundaries.sh` → OK;`git diff --check` → 干净
- 未运行:Alembic 升降级往返(需一次性 PostgreSQL,专项);PostgreSQL 并发(WS-4);浏览器 E2E。
- Codex C3-A.2(EV-0029,macOS/Python 3.12):专项 34 passed;指定组合 73 passed;全量后端 393 passed;compileall、Ruff、release boundaries、git diff --check 全通过;四个 golden SHA 与 EV-0027 一致。
- RC0 final(EV-0030~EV-0033,macOS/Python 3.12.13):C3-B/C4/C5 专项 **98 passed**;全量后端 **404 passed**;前端 **34 passed** + build;浏览器 desktop 1280 与 mobile 390 八页 smoke 无横向溢出/console error;SQLite Alembic 矩阵通过;release boundaries、compileall、Ruff、git diff、golden raw SHA 全通过。无本机 Docker/Podman/Colima 与 PostgreSQL，真实 context probe 和 PostgreSQL migration 保持 environment-unverified。
- Finalist(EV-0035~EV-0036):本机 Python 3.12.13 全量 **412 passed**；前端 **36 passed** + build；release safety 14 passed、发布边界/禁语/allowlist/秘密扫描与 diff check 通过。远端精确 SHA 补齐 PostgreSQL 16.14 fresh/0007→0008/downgrade/re-upgrade、三镜像 CVE/SBOM、生产 Compose/readiness/API、business/legal/admin browser E2E；详见 `docs/competition/FINALIST_VERIFICATION.md`。

## Findings
- 前轮 findings(R1、C1~C11、potential、experiment_required、blocked_external)不变,见 Phase 0.5 记录与 EV-0013~EV-0016;本轮新增 EV-0019(版本链设计前提):冻结快照只存 hash 不存内容、全库无历史归档、消费方为"重算+哈希相等"式 fail-closed、格式变更即历史制品失配——证实 D-0008 所需的归档+版本注册表是当前缺失能力。
- experiment_required 消项:基线动态验证、SQLite/Alembic 往返、PostgreSQL 0008 migration、Docker runtime、三角色浏览器 E2E 与正式 API 比赛路径均完成；仍留:高并发/事务专项、四合成案例动态回归、priming 定量与全部真实外部证据。

## Unresolved Questions(真正需要用户决定)
1. 是否在独立复核 `b2c1be62d52bdda6b18aac31cbd548f7efaa946c` 与本交接提交后，进入后续集成决策；本任务不自动合并。
2. 真实律师认证、客户 UAT 与客户生产部署由谁、在哪个环境、以何种可审计证据完成；未确定前正式交付继续 `blocked_external`。

## C3 Frozen Plan(v1,历史审计记录；D-0016 与 EV-0030 已完成后续实施)
- **四个版本单元**(reader 只增不减,显式静态 mapping,无动态 import):`versioned/claim_compiler/v0_2`(七个 builder 函数+FactRecord 查询序+全部 hash 承载字符串)、`versioned/coverage_proof/v0_1`(纯函数,零依赖)、`versioned/delivery_snapshot/v1_0`(build_delivery_snapshot+_current_mechanism_snapshot+gate 字典 1.0 形状——gate 无独立持久化身份,其字典被嵌入 snapshot 散列,故随 snapshot 冻结)、`versioned/delivery_release/v1_1`(_release_body+六个 evidence helper+私有 _iso/_as_utc)。
- **registry.py**:`SUPPORTED_*_READERS` 静态 dict + `CURRENT_*_WRITE_VERSION` 常量;注册重复即抛;枚举测试守护历史条目不可删;COMPAT 显式矩阵:compiler 0.2→proof 0.1→gate 1.0→snapshot 1.0→release 1.1;不在矩阵内的组合 fail-closed `version_combination_unsupported`(422)。
- **分发点**:gate `_assert_compiler_integrity` 按 `compilation.compiler_version` 查 reader,未知→`compiler_version_unsupported`(409);`_assert_coverage_integrity` 回读 `proof.proof["schema_version"]`,缺失/未知→`coverage_proof_schema_unsupported`(409);release 按持久化 schema_version 分发,未知→`delivery_release_schema_unsupported`(evaluate blocking_reason,导出经 DeliveryGateBlocked 409)。绝不 fallback 当前 reader/最大版本/静默重算。
- **迁移判断**:ClaimCompilation/CoverageProof/GenerationInput/attestation 均已有可靠版本身份,不加重复字段;**唯一缺失是 ScenarioDeliveryRelease**(body 弃存只留 hash)→ 需最小迁移 `scenario_delivery_releases.schema_version String(16) NOT NULL server_default '1.1'`。不占用 0007:方案 A(推荐)C3 用 0007、WS-1A 顺延 0008;方案 B 零迁移(按已注册 reader 逐版本试算 hash,恰一匹配即验证,零匹配 fail-closed,但无法区分未知版本与篡改)。待用户裁决。
- **共享安全边界**:stable_hash/models/validity-policy 检查可共享(输出不进任何存储 hash 体);_iso/_as_utc/evidence dicts/schema 字面量/answerability_rule 中文串/待核验前缀/reason code 串全部 hash 承载,必须随版本模块冻结。
- **characterization(C3.0,先于一切移动)**:四组 golden vector(compiler 0.2 快照/values/双 hash/分母/reason 排序;proof 0.1 body/proof_hash/denominator_hash/四计数;gate 1.0 字典含 included_conclusions_hash;release 1.1 body/hash+snapshot 1.0)——由固定合成 fixture 生成、人工审查、连同哈希登记 EVIDENCE_LEDGER 后提交;重构前后 hash-for-hash 相等。
- **commit 计划**:C3.0 goldens;C3.1 registry+claim_compiler v0_2+gate compiler 分发;C3.2 coverage_proof v0_1+兼容矩阵;C3.3 delivery_snapshot v1_0;C3.4 delivery_release v1_1(+迁移,视裁决);C3.5 Docker/.dockerignore/release_safety 允许清单(注意:`COPY app/services/*.py` 不含子目录,versioned/ 必须显式加入 COPY 与 dockerignore,否则镜像 ImportError——C2 教训)+文档。每个 commit 独立可回滚、全量测试保持绿。
- **测试矩阵**:12 项(现版本组合通过、写默认不变、模拟 0.3 写默认后 0.2 仍由 0.2 reader 验证、三类未知版本 fail-closed、不兼容组合 fail-closed、篡改 version 字段/body fail-closed、reader 不可删、空 registry 可发现、324 基线不删不降)。另补 `compiler_version_stale` 现状无测试的缺口。
- **API/前端影响**:DeliveryGateStatusResponse `Literal["1.1"]` 保持(写版本升级时扩为多值 Literal);gate 错误 detail 不含版本字段,不变;前端零运行时版本分支,无需改动。
- **ultracode 建议**:C3 实施为 hash 冻结高精度重构,建议**单线实施+每 commit 全量测试**,不切换 ultracode;实施完成后的对抗验证(WS-5 式)可用多代理。

## Next Exact Action
- 停止新增工程功能。独立复核本分支的实现 SHA `b2c1be62d52bdda6b18aac31cbd548f7efaa946c`、EV-0035/EV-0036 与最终交接提交；由用户另行决定是否集成。正式 Release 必须等待真实律师认证、客户 UAT 和客户生产部署证据，当前继续 `blocked_external`。

## Stop Conditions
- 远端基线移动、产品代码出现非授权改动、或操作将超出当前批准文件范围 → 立即停止并报告。
- 不自动合并 `main` 或 `codex/vela-release-hardening`,不向 Draft 分支推送,不创建 PR;法律认证、客户 UAT、生产部署证据只能保持 `blocked_external` 直到真实证据进入审计链。
