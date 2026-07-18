# Vela Active Handoff

## Repository State
- Product baseline SHA: 65f0b398f94af72680f8c1139aa59f7df6b88d71
- Target base branch: codex/vela-release-hardening(不得直接推送)
- Checkpoint branch: claude/gracious-brahmagupta-bbg2dw(仅承载交接文件提交)
- Last verified product-code SHA: 65f0b398f94af72680f8c1139aa59f7df6b88d71 + 已批准的 WS-1C/C1 产品提交(仅 `backend/app/capability_packs/registry.py`、新增 `backend/app/capability_packs/version_index.py`、新增 `backend/tests/test_capability_pack_version_archive.py`;其余产品代码与基线零差异)
- Allowed commits: 5 个交接文件 + 经用户逐项批准的 workstream 产品提交(当前仅 WS-1C/C1)
- Resume 时必须执行的 Git 核验命令:
  ```
  git status --short
  git branch --show-current
  git rev-parse HEAD
  git fetch origin
  git rev-parse origin/codex/vela-release-hardening        # 必须 = 65f0b398...
  git diff --stat 65f0b398f94af72680f8c1139aa59f7df6b88d71 HEAD  # 差异只允许:5 个交接文件 + 已批准的 WS-1C/C1 三个产品文件
  ```
- 注意:Git 的实时 HEAD 只能在恢复时通过 `git rev-parse HEAD` 获取;本文件不记录、也不得用文件记录替代 Git 实时查询(D-0004)。

## Current Phase
- Phase: WS-1C/C1 — Capability Pack 历史版本索引与精确寻址基础——已实施并全量验证,等待用户复核
- Workstream: WS-1C(C1 完成;C2~C5 未开始,未获批准)
- Status: complete_pending_review
- Allowed file scope(C1 已批准范围): registry.py、新增 version_index.py、新增 test_capability_pack_version_archive.py、5 个交接文件
- Prohibited actions: 修改 active manifest/生产 rules/生产 corpus/真实归档制品/loader scheme 语义/机制层模型/Claim-Coverage/compiler-proof-release evaluator/Alembic/前端/产品文档/startup-readiness/release 行为;开始 C2~C5 与 WS-1A/B/D/E;创建 PR;合并;推送 Draft 分支

## Frozen Product Definition
- 见 `AGENTS.md` 第 2–4 节与 D-0006;产品语义新增冻结决定:**D-0007(分母 A+ 方案)、D-0008(多版本不可变共存)、D-0009(ResearchItem 与 ClaimRecord 分离)、D-0010(外证矩阵采用状态修正)**——以 DECISION_LOG 原文为准,不得再列为 unresolved。

## Approved Decisions
- D-0001~D-0006(见前);**D-0007 分母 A+**(30 条全量冻结分母,in_scope/out_of_scope_by_scope,五类 disposition,screening 不改分母,CoverageProof 披露 pack_total/scope_total/out_of_scope_by_scope_count/五类计数/denominator hash);**D-0008 多版本不可变共存**(历史 artifact byte-identical 保留、新版本递增、reader 只增不减、未知版本 fail-closed、空库可启动);**D-0009 独立 ResearchItem 模型**(Alembic 迁移,无 draft 不再造伪 ClaimRecord);**D-0010**(Tesseract→受控实验→生产候选;LangGraph→当前不采用、未来仅非安全核心实验、不得声称其必然破坏 frozen bytes;WS-1D 验收=平台核心无 Brazil-specific branch/default/fallback/validation/source mapping/corpus path/release rule,非 grep 字面量)。

## Work Completed
- Phase 0 / 0.5:见前轮(EV-0001~EV-0017)。
- Phase 0.6:(1) D-0007~D-0010 落账;(2) **基线动态验证首次通过**(EV-0018):靶向 35 passed、全量后端 295 passed、compileall、前端 29 passed + 构建、发布边界、git diff --check,全部绿,Python 3.12.3(未用系统 3.11);(3) WS-1C 设计前提事实采集(EV-0019);(4) WS-1C 实施方案冻结(见下节)。

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
- 交接文件:5 个(持续更新)。
- 未触碰:active manifest、生产 rules/corpus JSON、loader.py、机制层、evaluator、Alembic、前端、产品文档;仓库内未创建任何真实 archive 目录(C1 仅用临时目录合成 bundle)。

## Tests and Commands(本轮,EV-0018)
- environment: 远程受管容器 Linux;Python 3.12.3(uv venv,scratchpad;未用系统 3.11);Node v22.22.2;npm 10.9.7;Docker 29.3.1
- 靶向 6 文件 pytest → 35 passed(32.11s);`python -m compileall -q app tests` → 通过;全量 `pytest tests -q` → **295 passed**(73.70s);`npm ci` + `npm run test:components` → 29 passed;`npm run build` → 成功(3.62s);`bash scripts/check_release_boundaries.sh` → OK;`git diff --check` → 干净
- 未运行:Alembic 升降级往返(需一次性 PostgreSQL,专项);PostgreSQL 并发(WS-4);浏览器 E2E。

## Findings
- 前轮 findings(R1、C1~C11、potential、experiment_required、blocked_external)不变,见 Phase 0.5 记录与 EV-0013~EV-0016;本轮新增 EV-0019(版本链设计前提):冻结快照只存 hash 不存内容、全库无历史归档、消费方为"重算+哈希相等"式 fail-closed、格式变更即历史制品失配——证实 D-0008 所需的归档+版本注册表是当前缺失能力。
- experiment_required 消项:基线动态验证已完成(EV-0018);仍留:PostgreSQL 并发/事务、Alembic 往返(一次性库)、四合成案例动态回归、全角色浏览器 E2E、priming 定量。

## Unresolved Questions(真正需要用户决定)
1. WS-1C 实施批准(按上节冻结方案与 commit 计划 C1~C5)。
2. ResearchItem 模型命名偏好:`ResearchItem` vs `ClaimCompilationItem`(D-0009 两候选,WS-1A 冻结方案时定,可由实施者建议)。

## Next Exact Action
- 等待用户复核 WS-1C/C1(证据:EV-0020;全量 309 passed)。经复核通过后,请求批准 C2(真实 1.3.1/2.9/1.13 归档 + byte-identity 测试);C2 前不得创建真实 archive 制品。

## Stop Conditions
- 远端基线移动、产品代码出现非授权改动、或操作将超出 5 个允许文件 → 立即停止并报告。
- 本轮输出完成 → 停止等待批准;不修改产品代码、不建迁移、不开始 WS-1A/B/D/E、不推送 Draft 分支、不建 PR。
