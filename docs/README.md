# Vela 协查材料文档索引

| 文档 | 读者 | 内容 |
|------|------|------|
| [ai-review/README.md](./ai-review/README.md) | Claude Code / Codex / 独立审核人 | 多模型争议审查入口、阅读顺序、已实现增量与必须攻击的缺口 |
| [ai-review/TARGET_PRODUCT_STATE.md](./ai-review/TARGET_PRODUCT_STATE.md) | 产品 / 法务 / 工程 / AI 审查人 | 目标呈现状态、架构边界、抽象纪律与证据等级 |
| [ai-review/CLAUDE_CODE_ARGUE_PROMPT.md](./ai-review/CLAUDE_CODE_ARGUE_PROMPT.md) | Claude Code / 其他代码模型 | 可直接复制的只读红队提示词和第二轮裁决格式 |
| [DEVELOPMENT_CANDIDATE.md](./DEVELOPMENT_CANDIDATE.md) | 产品 / 工程 / 发布审核人 | 当前开发分支新增能力、本地验收与远端 CI 待办 |
| [REQUIREMENTS_TRACEABILITY.md](./REQUIREMENTS_TRACEABILITY.md) | 产品 / 法务 / 工程 / 审核人 | 原方案与冻结讨论的统一状态、完成判据、证据和外部阻塞 |
| [CUSTOMER_DELIVERY_ASSURANCE.md](./CUSTOMER_DELIVERY_ASSURANCE.md) | 客户 / 巴西律师 / 发布管理员 / 安全审核人 | 真实客户交付证据链、职责分离、精确制品签名、部署门与仍需外部提供的证据 |
| [material-fields-methodology.md](./material-fields-methodology.md) | 产品 / 法务 / 规则维护者 | **如何为一个场景定义字段**（六步流程） |
| [material-fields-decision-table-brazil-new-energy.md](./material-fields-decision-table-brazil-new-energy.md) | 产品 / 法务 | 唯一正式 `brazil_new_energy_greenfield` Capability Pack 的**字段决策表** |
| [business-material-intake-guide.md](./business-material-intake-guide.md) | 业务 / 法务 | **产品说明**：业务核对事实并知情确认、法务确认范围 |
| [experiments/state-metadata-coverage-v1.md](./experiments/state-metadata-coverage-v1.md) | 产品 / 法务 / 工程 | **实验①**：30 条圣保罗州法规 LexML 元数据覆盖率与 Citator 边界决策 |
| [research/recruitment-post-pt-zh.md](./research/recruitment-post-pt-zh.md) | 研究负责人 / 招募主体 | 葡中双语研究标注者招募稿；发布前必填项未完成时禁止外发 |
| [research/annotation-guide-v0.md](./research/annotation-guide-v0.md) | 标注者 / 仲裁者 / 数据负责人 | 可执行的双人独立标注、仲裁、质量门与安全规范（v0 草案） |
| [decisions/2026-07-17-capability-pack-branch.md](./decisions/2026-07-17-capability-pack-branch.md) | 仓库所有者 / 发布负责人 | 旧 scope 分支的证据、保留决定与私有 PR 合并后清理条件 |
| [decisions/2026-07-17-evidence-retrieval-ocr-roadmap.md](./decisions/2026-07-17-evidence-retrieval-ocr-roadmap.md) | 工程 / 法务 / 数据负责人 | Claim/Evidence、跨语 embedding、pgvector 与可审计 OCR 的实验选型和退出条件 |
| [experiments/rule-card-dual-track-brazil-sp-v0.1.md](./experiments/rule-card-dual-track-brazil-sp-v0.1.md) | 产品 / 法务 / 规则维护者 | **实验②**：10 张圣保罗州环境许可 provisional 规则卡的法条正向 / 表单逆向双轨比较 |
| [experiments/ingestion-qa-v3.md](./experiments/ingestion-qa-v3.md) | 产品 / 法务 / 工程 | **实验④**：10 份官方法规文本、30 个源验证锚点的 PDF 摄取遗漏率（v3 有效） |
| [experiments/ingestion-qa-v1.md](./experiments/ingestion-qa-v1.md) | 产品 / 法务 / 工程 | **实验④审计**：v1/v2 错误标注为何被作废且未用于结论 |

受控试点能力包 manifest：`backend/app/capability_packs/brazil_new_energy_greenfield/manifest.json`
绑定规则制品：`backend/app/rules/brazil_new_energy.json`
