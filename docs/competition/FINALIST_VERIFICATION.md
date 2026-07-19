# Vela 决赛竞争力硬化核验

核验日期：2026-07-19
状态：工程 Green Gate 通过；法律认证、真实客户 UAT 与客户生产部署仍为 `blocked_external`

## 精确身份

- 分支：`codex/vela-finalist-hardening-20260719`
- 精确起点：`14e3cd395cccfe2218b8013a448a137b881a9860`
- 已验证实现 SHA：`b2c1be62d52bdda6b18aac31cbd548f7efaa946c`
- GitHub Actions：<https://github.com/so-ki/vela/actions/runs/29681515075>
- 触发方式：`push`
- 结果：`completed / success`
- 证据工件：`production-security-and-smoke-evidence`，artifact ID `8440743065`
- 工件 ZIP SHA-256：`2367aaba2063456ab29b3e1c435ba914e25596ff662c0931b80b96364392139f`

本文件所在交接提交的实时 SHA 必须按 D-0004 从 Git 查询；上述 SHA 是被完整运行时矩阵验证的实现提交，不用文档内容替代 Git 身份。

## 决赛机制验收

- Claim Compiler 0.3 对正式 Capability Pack 固定生成 30 项，Scope 只决定 `in_scope` / `out_of_scope_by_scope`，不改变 Pack 分母。
- CoverageProof 0.2 使用五类 in-scope disposition，并验证 `pack_total = 30` 与全部计数守恒。
- 没有真实法律草稿时写入独立 ResearchItem，不创建占位 ClaimRecord；ClaimRecord 仍只承载真实法律草稿。
- Alembic 0008 增加 ResearchItem 与业务事实否定极性，upgrade/downgrade/re-upgrade 均通过。
- writer 显式持久化 0.3/0.2 reader 版本；0.2/0.1 历史 reader 继续可读；unknown 版本保持 fail-closed。
- Answerability Gate、readiness 与正式 delivery gate 未削弱；演示最终状态仍为 `blocked_external`。
- 正式比赛流程通过上传、事实登记/确认、Scope 冻结、编译、Claim、CoverageProof、Gate、audit 等正式服务/API；RC0 synthetic 工作台仅保留为机制说明附录。
- 自动化证明修改测试材料中的关键已确认事实会改变 compiler input/output hash；没有固定结果 demo endpoint，也没有直接 seed 最终输出。

## 精确 SHA 远端验证

| 验证项 | 结果 |
|---|---|
| Backend tests and migrations | 412 passed；SQLite fresh / full downgrade-upgrade / 0007→0008→0007→0008 通过 |
| API golden path | 23 passed，0 failed |
| Frontend audit, tests and build | 0 vulnerabilities；9 files / 36 tests passed；production build 通过 |
| Release boundary | 通过；竞赛禁语扫描覆盖 5 个对外表面 |
| 镜像安全 | backend/frontend/PostgreSQL High/Critical CVE gate 通过；三份 CycloneDX SBOM 已生成 |
| Production Compose | 隔离生产栈启动与 readiness 通过 |
| PostgreSQL | `16.14` |
| Alembic head | `20260719_0008` |
| PostgreSQL migration | fresh head、0008→0007→0008、再次 downgrade/re-upgrade 通过 |
| 正式 API 路径 | 22 passed，0 failed；保留真实 scenario id `1` 给浏览器验证 |
| Browser E2E | business、legal、admin 三角色，3 passed；legal 读取八个 live scenario 页面 |

### 容器身份

- backend：`sha256:64b0a3fa3acfe5006a4463da1ee96d0c612fef0e4e7fbdd9a898bab37366c38e`
- frontend：`sha256:044df113c4a2440c013d1df087d84137c0edd31754b50e2d475628c9a5440c24`
- PostgreSQL：`sha256:38baa3000763a998e25a9b6432f7c054692f7cb4997ebd104449e575f58c8a3d`

## 本机复核

- Python 3.12.13 全量 backend：`412 passed, 3 warnings`。
- scoped Ruff 与 `compileall`：通过；全仓 Ruff 仍有本轮前已存在的非阻断遗留，不以批量无关改动掩盖。
- frontend：9 files / 36 tests passed；production build 通过。
- release safety：14 passed；release boundary、竞赛禁语扫描、发布包 allowlist/秘密扫描与 `git diff --check` 通过。
- 本机无 Docker/PostgreSQL runtime，相关结论只引用绑定精确 SHA 的 GitHub Actions，不伪装成本机验证。

## Frozen Golden raw SHA-256

| 文件 | SHA-256 |
|---|---|
| `compiler_v0_2.json` | `8787a1644a0c6fe4076978e3b181caa9f3072e29db1e71d3b5670415df4679b4` |
| `coverage_proof_v0_1.json` | `206cb55372dcdb7d00a12d4af38b69a95e10ec57d662f538498c64e138807ffb` |
| `answerability_v1_0.json` | `e40f68050c8e3f56c26ea20fb19772a6fe78109c76d2f5d29d98efc5426f257a` |
| `delivery_release_v1_1.json` | `6cdce303c806ff36e804f01d67e42595d6307984a83312efe211a50f4fdac256` |

四个历史文件未修改，raw SHA 与 RC0 前记录一致。

## 声明边界

这些证据证明工程控制在指定提交、容器和合成比赛输入上按设计运行，不证明法律内容完整、法律意见成立、律师认证完成、客户验收完成或客户生产部署完成。不得创建正式 Release，不得把 `blocked_external` 升级为通过，不得把比赛流程结果描述为律师或客户证据。
