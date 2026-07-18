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
