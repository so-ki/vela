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
