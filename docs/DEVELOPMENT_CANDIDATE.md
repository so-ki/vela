# Vela 当前开发候选记录

日期：2026-07-18（Asia/Shanghai）
分支：`codex/vela-release-hardening`
状态：`local-verified / remote-CI-pending / draft-review-only`

本文件记录当前开发分支相对上一冻结 RC 的新增工程事实。它不是新的发布放行声明；提交、推送、Draft PR CI、独立人工审查和生产镜像烟测全部完成前，上一 RC 的远端绿色证据不能移植到本分支。

## 本批已实现

1. **真实法源披露：** 简报和检索提示只列本次冻结命中实际存在的来源，零命中明确披露，不再硬编码 LexML/STF/STJ。
2. **可交接导出：** Word/PDF 增加标识、pinpoint、效力、状态时点、最近核验、review status、verification scope 和官方链接；DOCX 只创建 HTTPS 外部链接。
3. **机制层：** 六状态材料账本、CAS 更新、持久业务事实、Claim Compilation、法务人工确认、CoverageTask 和 CoverageProof 均已持久化、审计并提供 API。
4. **法规变化候选：** 不可变 LegalSourceVersion/LegalChangeEvent、原文/规范化哈希、文章/关系 diff、官方域名约束、法务状态机与 CAS 已实现；`active` 仅表示 registry-approved snapshot，不设唯一 current，也不发布到正式 corpus。
5. **平台边界：** 隔离的非真实 Capability Pack fixture 可独立完成生成、确定性命中、零命中拒答与简报；测试会阻止读取正式 Brazil manifest/rules/corpus，核心场景模型不再默认 Brazil。
6. **研究路线：** 已记录 BGE-M3、Qwen3-Embedding、pgvector、Docling、Tesseract、RAGChecker、RefChecker 与 LegalBench-RAG 的实验角色和退出条件，没有把候选项目写成已上线能力。
7. **多模型审查：** `docs/ai-review/` 固化目标状态、架构纪律、当前缺口和 Claude Code 只读红队提示词。
8. **真实交付门：** Answerability Gate 已接入所有最终下载；OAB 凭证、两律师法律内容认证、精确 bytes 冻结、ITI 签名核验、客户 UAT、production provenance/gold evidence 和限时 release 已形成统一 fail-closed 链。
9. **机制层界面：** 新增 `/scenarios/:id/mechanism` 双角色工作台，业务可维护材料/事实，法务可编译并确认 Claim、生成 CoverageProof；客户交付状态与机制通过状态明确分离。
10. **客户交付证据台：** 新增 `/scenarios/:id/delivery-assurance` 角色化界面，支持候选件审阅、OAB 凭证、canonical manifest、场景签名/ITI 核验、客户 UAT、双律师内容认证、生产证据、限时 release 与紧急撤回；所有操作仍经过服务端门禁。

## 本地验收证据

| 验收项 | 当前结果 |
|---|---|
| 后端 Python 3.12 全量 | `293 passed`；3 条第三方弃用警告 |
| Python 编译 | `app` 与 `tests` compileall 通过 |
| 前端组件 | `27 passed` |
| 前端 TypeScript/Vite | 生产构建通过，158 modules |
| 锁定依赖审计 | `pip-audit: No known vulnerabilities found`；`npm audit --offline: 0 vulnerabilities`；远端在线审计待 CI |
| Alembic | base → `20260718_0005` → base → `20260718_0005` 通过；`alembic check` 无漂移 |
| 法律质量门 | controlled pilot 通过；GA 按设计失败，`expert_verified=0` |
| 发布边界 | Docker context/COPY allowlist、测试 fixture 排除、密钥边界与 GitHub Actions SHA pins 通过 |
| 差异格式 | `git diff --check` 通过 |

## 尚未完成，不能对外宣称

- 真实客户的 OAB/ConfirmADV、双律师法律内容认证、ITI 数字签名、客户 UAT、gold acceptance set 和 production provenance 尚未由外部主体提供；代码按设计保持不可交付。
- 机制层业务/法务界面已完成工程实现；真实用户 UAT 尚未完成。
- 新法规模块没有官方源调度、唯一 current 指针、自动 corpus 发布或回滚。
- OCR、多语 embedding、向量存储和 RAG 评测尚处于实验路线。
- 巴西法律内容没有具名律师认证；第二法域和第二行业能力包尚不存在。
- 新分支尚未完成远端在线依赖审计、三生产镜像 CVE/SBOM、PostgreSQL 迁移、Playwright 和 API 黄金路径。

## 审查入口

- 目标与反对意见：[`ai-review/README.md`](./ai-review/README.md)
- 需求状态：[`REQUIREMENTS_TRACEABILITY.md`](./REQUIREMENTS_TRACEABILITY.md)
- Claude Code 提示词：[`ai-review/CLAUDE_CODE_ARGUE_PROMPT.md`](./ai-review/CLAUDE_CODE_ARGUE_PROMPT.md)
- 上一冻结 RC：[`RELEASE_CANDIDATE.md`](./RELEASE_CANDIDATE.md)

Draft PR 远端 CI 绿色后，应把运行 URL、head SHA、镜像/SBOM 结果与独立审查裁决补入本文件，再讨论是否形成新的冻结 RC。
