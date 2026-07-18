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
