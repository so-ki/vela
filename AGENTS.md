# AGENTS.md — Vela 跨模型 Agent 协作规则

本文件对所有在本仓库工作的代码 Agent(Claude Code、Codex、其他)具有强制约束力。
开始任何工作前,必须先读本文件与 `docs/ai-review/ACTIVE_HANDOFF.md`。

## 1. 精确基线与目标分支

- 仓库:`so-ki/vela`
- 目标基线分支:`codex/vela-release-hardening`
- 精确基线提交:`65f0b398f94af72680f8c1139aa59f7df6b88d71`
- 工作分支(名称可因平台自动生成而不同)必须从上述精确提交出发。
- 开始前必须只读核验:`git status --short`、`git rev-parse HEAD`、`git fetch origin && git rev-parse origin/codex/vela-release-hardening`。
- HEAD 或远端与基线不一致时:立即停止并报告。不得自动改用更新提交、祖先提交或 `main`。
- 不得直接推送原 Draft 分支(`codex/vela-release-hardening`)。
- 未经用户明确授权:不得推送、不得创建 PR、不得合并。
- 不得切换、清理或覆盖用户文件。

## 2. Vela 完整 MVP 产品定义(冻结)

Vela 是面向跨境投资法律协查的受控交付平台,目标架构为:

> **薄平台机制层 + 按国家/地区/行业/交易动作/法律议题隔离的 Capability Pack 知识层。**

- 第一个完整垂直 Pack:**巴西 · 圣保罗州 · 新能源制造 · 绿地设厂**,用于验证平台架构。
- "最小"仅指范围最小:一个国家、一个州、一个行业、一个项目动作、单客户、单实例、私有化受控试点。
- "最小"**不得**削减:安全边界、材料完整性、事实确认、Scope 冻结、版本重现、规则研究分母、法源验证、Claim 与 Coverage、拒答、人工复核、exact artifacts、律师/UAT/部署/release 门禁、审计、完整测试、文档与 UI 一致性。
- 真实律师签核、客户 UAT、客户环境、WORM/KMS 等外部证据可标记 `blocked_external`,但其数据模型、流程、门禁、撤回逻辑和测试**不得删除**。

## 3. 平台机制层与 Capability Pack 知识层边界

- 平台机制层(身份、材料、事实、Scope、Claim、Coverage、Gate、审计、制品、证据、release)必须国家无关。
- 国家/地区、行业、交易动作、法律维度、材料字段、规则与构成要件、法源、覆盖协议、检索配置、输出配置、质量门,必须封装在 Capability Pack 内。
- 平台核心代码不得直接导入或硬编码 Brazil、CETESB、Campinas、BYD 或具体巴西规则。
- 在存在第二个真实法域 Pack 之前,不得宣称"已完成跨法域验证"。

## 4. BYD 案例的地位

- BYD(比亚迪/Campinas 演示)**只能是隔离的演示或测试案例**。
- BYD 不得成为:平台架构来源、规则设计来源、默认事实、规则触发词、提示词示例、前端默认值、或验收标准(E2E oracle)。
- 发现 BYD 耦合时,记录为缺陷,进入 Gap Matrix 与 workstream,不得就地扩散。

## 5. 工作流程纪律

- 每个 workstream 必须:**先只读分析 → 冻结方案 → 经用户批准 → 再实施**。
- 不得自行扩大范围;超出当前批准范围的发现只记录,不动手。
- 不得通过降低断言、删除测试、跳过测试或放宽门禁来"解决"失败。fail 必须以修复根因或经批准的决定关闭。
- 每个阶段开始与结束必须更新 `docs/ai-review/ACTIVE_HANDOFF.md`。
- 产品决定以 `docs/ai-review/DECISION_LOG.md` 为准(只追加);证据以 `docs/ai-review/EVIDENCE_LEDGER.md` 为准。
- 不得仅依赖聊天历史;跨会话/跨模型交接以上述文件为唯一事实来源。

## 6. 测试与证据纪律

- 所有事实、结论和测试结果必须有证据(命令、原始输出摘要、文件与精确行号、提交 SHA),登记入 `EVIDENCE_LEDGER.md`。
- PostgreSQL 行为不得用 SQLite 结果外推;涉及并发、事务、锁、类型的结论必须在 PostgreSQL 上验证。
- Alembic downgrade 只能在一次性(disposable)数据库中运行,严禁在含真实数据的库上执行。
- `blocked_external` 状态的项不得被描述为"已经完成";只能描述为"内部逻辑已实现、外部证据待补"。
- 未运行的测试不得报告为通过;失败的测试必须原样报告输出。
