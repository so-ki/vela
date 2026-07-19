# Vela Active Handoff

## Repository State
- Product baseline SHA: 65f0b398f94af72680f8c1139aa59f7df6b88d71
- Target base branch: codex/vela-release-hardening(不得直接推送)
- Checkpoint branch: claude/gracious-brahmagupta-bbg2dw(仅承载交接文件提交)
- Claude handoff source: `origin/claude/vela-ws-1c-c3a-versioned-readers` = `00b47bc89f11aa5a8eaaf38dae18565e8fd07274`(Codex 接管时已 fetch 核验)
- Codex integration branch: `codex/vela-mvp-integration`(从上述精确交接点创建;不得自动合并或推送 Draft 分支)
- Last verified product-code SHA: `a6d985402ebe606cc423c9c3d2c270e00229979c`(C3-A.2;基于 C3-A/C3-A.1 交接点)
- Allowed commits: 5 个交接文件 + 经批准的 WS-1C 产品提交(C1/C1.1/C2/C2.1/C3-A/C3-A.1/C3-A.2)
- Resume 时必须执行的 Git 核验命令:
  ```
  git status --short
  git branch --show-current
  git rev-parse HEAD
  git fetch origin
  git rev-parse origin/codex/vela-release-hardening        # 必须 = 65f0b398...
  git diff --stat 65f0b398f94af72680f8c1139aa59f7df6b88d71 HEAD  # 差异只允许:5 个交接文件 + 已批准的 WS-1C 产品文件
  ```
- 注意:Git 的实时 HEAD 只能在恢复时通过 `git rev-parse HEAD` 获取;本文件不记录、也不得用文件记录替代 Git 实时查询(D-0004)。

## Current Phase
- Phase: WS-1C/C3-A + C3-A.1 + C3-A.2(嵌套持久化 JSON 引用结构验证)——已实施并全量验证,等待独立复核
- Workstream: WS-1C(C1、C1.1、C2、C2.1、C3-A/C3-A.1/C3-A.2 完成;C3-B/C4/C5 未开始)
- Status: complete_pending_review
- 分支说明: Codex 从 Claude 精确 HEAD `00b47bc` 建立 `codex/vela-mvp-integration`;C3-A.2 产品提交 `a6d9854`
- 外部状态: 法律认证、真实客户 UAT、客户生产部署证据继续为 `blocked_external`,工程测试不得升级这些状态
- 分支说明: C2 在独立分支 `claude/vela-ws-1c-c2-real-archive`(基于 C1.1 提交 730b9fd);checkpoint 分支 `claude/gracious-brahmagupta-bbg2dw` 停在 C1.1
- Allowed file scope(C3-A.2): `answerability_gate_service.py`、`test_versioned_payload_validation.py` 与交接文件;已严格遵守
- Prohibited actions: 未获明确批准前开始 C3-B 迁移/Release reader、ResearchItem、C4/C5;创建 PR;合并;推送 Draft 分支

## Frozen Product Definition
- 见 `AGENTS.md` 第 2–4 节与 D-0006;产品语义新增冻结决定:**D-0007(分母 A+ 方案)、D-0008(多版本不可变共存)、D-0009(ResearchItem 与 ClaimRecord 分离)、D-0010(外证矩阵采用状态修正)**——以 DECISION_LOG 原文为准,不得再列为 unresolved。

## Approved Decisions
- D-0001~D-0006(见前);**D-0007 分母 A+**(30 条全量冻结分母,in_scope/out_of_scope_by_scope,五类 disposition,screening 不改分母,CoverageProof 披露 pack_total/scope_total/out_of_scope_by_scope_count/五类计数/denominator hash);**D-0008 多版本不可变共存**(历史 artifact byte-identical 保留、新版本递增、reader 只增不减、未知版本 fail-closed、空库可启动);**D-0009 独立 ResearchItem 模型**(Alembic 迁移,无 draft 不再造伪 ClaimRecord);**D-0010**(Tesseract→受控实验→生产候选;LangGraph→当前不采用、未来仅非安全核心实验、不得声称其必然破坏 frozen bytes;WS-1D 验收=平台核心无 Brazil-specific branch/default/fallback/validation/source mapping/corpus path/release rule,非 grep 字面量)。

## Work Completed
- Phase 0 / 0.5:见前轮(EV-0001~EV-0017)。
- Phase 0.6:(1) D-0007~D-0010 落账;(2) **基线动态验证首次通过**(EV-0018):靶向 35 passed、全量后端 295 passed、compileall、前端 29 passed + 构建、发布边界、git diff --check,全部绿,Python 3.12.3(未用系统 3.11);(3) WS-1C 设计前提事实采集(EV-0019);(4) WS-1C 实施方案冻结(见下节)。
- C3-A.2(EV-0029):draft 引用、ClaimRecord 三个 JSON 字段及 CoverageProof 0.1 嵌套元素全部在 frozen reader 前按 `list[str]`/对象结构校验;非法形状即 422,新增 13 个对抗测试;全量后端 **393 passed**;四个 golden raw SHA 不变。

## WS-1C Frozen Plan(v1,待批准;完整版见本轮会话报告)
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
- 交接文件:5 个(持续更新)。
- C3-A.2 未触碰:frozen v0_2/v0_1 readers、四个 goldens、active manifest、生产 rules/corpus、loader、release evaluator、Alembic、前端与产品文档。

## Tests and Commands(本轮,EV-0018)
- environment: 远程受管容器 Linux;Python 3.12.3(uv venv,scratchpad;未用系统 3.11);Node v22.22.2;npm 10.9.7;Docker 29.3.1
- 靶向 6 文件 pytest → 35 passed(32.11s);`python -m compileall -q app tests` → 通过;全量 `pytest tests -q` → **295 passed**(73.70s);`npm ci` + `npm run test:components` → 29 passed;`npm run build` → 成功(3.62s);`bash scripts/check_release_boundaries.sh` → OK;`git diff --check` → 干净
- 未运行:Alembic 升降级往返(需一次性 PostgreSQL,专项);PostgreSQL 并发(WS-4);浏览器 E2E。
- Codex C3-A.2(EV-0029,macOS/Python 3.12):专项 34 passed;指定组合 73 passed;全量后端 393 passed;compileall、Ruff、release boundaries、git diff --check 全通过;四个 golden SHA 与 EV-0027 一致。

## Findings
- 前轮 findings(R1、C1~C11、potential、experiment_required、blocked_external)不变,见 Phase 0.5 记录与 EV-0013~EV-0016;本轮新增 EV-0019(版本链设计前提):冻结快照只存 hash 不存内容、全库无历史归档、消费方为"重算+哈希相等"式 fail-closed、格式变更即历史制品失配——证实 D-0008 所需的归档+版本注册表是当前缺失能力。
- experiment_required 消项:基线动态验证已完成(EV-0018);仍留:PostgreSQL 并发/事务、Alembic 往返(一次性库)、四合成案例动态回归、全角色浏览器 E2E、priming 定量。

## Unresolved Questions(真正需要用户决定)
1. C3-B 的迁移与 release reader 实施批准:是否按冻结设计为 `ScenarioDeliveryRelease` 增加显式 schema identity,以及 Alembic 0007/后续 ResearchItem 0008 的线性编号。
2. ResearchItem 模型命名偏好:`ResearchItem` vs `ClaimCompilationItem`(D-0009 两候选,WS-1A 冻结方案时定,可由实施者建议)。

## C3 Frozen Plan(v1,待批准;完整版见本轮会话报告,证据 EV-0026)
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
- 独立复核 C3-A.2 产品提交 `a6d9854` 与 EV-0029;通过后进行 **C3-B 只读实施前审计**(delivery snapshot 1.0 / release 1.1 reader / Alembic 0007)。C3-B 涉及迁移和 release 语义,在 Decision Log 追加明确批准前不得修改产品代码。

## Stop Conditions
- 远端基线移动、产品代码出现非授权改动、或操作将超出当前批准文件范围 → 立即停止并报告。
- 不自动合并 `main` 或 `codex/vela-release-hardening`,不向 Draft 分支推送,不创建 PR;法律认证、客户 UAT、生产部署证据只能保持 `blocked_external` 直到真实证据进入审计链。
