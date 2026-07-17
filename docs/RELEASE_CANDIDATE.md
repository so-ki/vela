# Vela 受控试点发布候选记录

## 发布判定

当前版本是 **Vela 巴西 · 圣保罗州 · 新能源制造绿地设厂能力包 1.3.0 的受控试点发布候选（RC）**，不是通用可用（GA）版本，也不构成正式法律意见。

本地冻结验收支持以下范围：单客户、单独部署、私网或本机回环访问、受管账号、受管终端/DMS 已扫描的内部材料，以及法务逐项复核后导出。第二家客户、外部不可信上传、第三方 LLM 外发、生产 SSO、跨租户共享部署或无人复核自动决策均不在本 RC 范围内。

远端最终放行条件尚未满足：必须先把 GitHub 仓库设为 Private，并由 GitHub Actions 的 `production-compose-smoke` 在真实 Docker + PostgreSQL 环境跑绿。该检查未通过前，只能称“本地验收通过的 RC”，不能称“已部署可用”。

## 冻结制品标识

| 制品 | 版本/哈希 |
|---|---|
| Capability Pack | `brazil_new_energy_greenfield` `1.3.0` |
| Pack semantic hash | `de625fc775e9e0e7837f9fb407d8644be3702acd0ff37480f120ad62a646c47b` |
| 规则制品 | `brazil_new_energy` `2.9` |
| 规则 content hash | `351c7d6f6f71a5d1cedd3527a10a8b89f1cd72d3079d4b41d42b827aeba62c9c` |
| 法源语料 | `brazil_legal_corpus` `1.12`，`provisional` |
| 语料 content hash | `70b2d97fde7887304eccc312de2c077c51a0e144a233437eec5262fbfdc90c23` |
| Python lock SHA-256 | `e863b5cc2c4a698b3e143aeb259d508213a09f318333e9c593916bb33b297344` |
| npm lock SHA-256 | `62c9608942dcfb7219a4d8779c7ff7e89bd5e5984232ba248225ee20983456e1` |
| 数据库迁移头 | `20260717_0002` |

发布 ZIP 每次构建后由 `scripts/build_submission_package.sh` 在 ZIP 旁生成 `<zip>.sha256`。必须同时交付并核对该旁车文件；任何源码、文档或构建器变化都会使旧哈希失效。

## 冻结验收证据

验收日期：2026-07-17（Asia/Shanghai）。

| 验收项 | 结果 |
|---|---|
| Python 3.12.13 全新环境安装 | `requirements.lock` 含 45 条跨平台声明，本环境激活 43 条，兼容检查通过 |
| Python 依赖安全 | `pip-audit` 无已知漏洞 |
| 后端全量 | `252 passed`；3 条来自第三方库的弃用警告 |
| 安全/并发/发布重点回归 | 通过 |
| 前端 Node 24.13.0 / npm 11.6.2 | 锁文件安装；`npm audit` 为 0 |
| 前端组件与构建 | `20 passed`；TypeScript 与 Vite 生产构建通过（152 modules） |
| 生产构建浏览器冒烟 | Playwright Chromium：`1 passed`；登录并进入业务工作台，无页面异常或 HTTP 5xx |
| API 黄金路径 | `17 passed / 0 failed` |
| Alembic | `0001 → 0002 → base → 0001 → 0002`；`alembic check` 无漂移 |
| 法律质量门 | controlled pilot 通过；GA 按设计失败 |
| 发布边界 | Docker context/COPY allowlist、密钥与路径扫描通过 |
| 供应链 | 9/9 GitHub 外部 Actions 固定到完整 40 位提交 SHA |
| 静态质量 | Python compile、Shell、YAML、`git diff --check` 全部通过 |

法律质量门覆盖 74 条语料：53 条 `provisional` 可召回、21 条 `quarantined`；7 个已知错源测试的禁用源命中为 0、零命中为 0、声明的预期法源漏召回为 0。36 条有解析审计证据的来源中 19 条可解析、17 条无法解析；无法解析项均已隔离，法源域名一致性错误为 0。当前专家认证数为 0，因此这一结果只证明回归门和错误隔离按设计工作，不证明法律结论正确、法条时点有效或个案适用。

## 原方案关键实验与治理工件

- **实验①州级元数据：** 30 条冻结圣保罗州法规的 LexML URN `30/30` 可解析，但 `legislationChanges` 和可识别整合文本信号均为 `0/30`。Citator v1 因此保持联邦范围；州级修订必须回到 AL-SP 官方关系页人工核对。见 [实验记录](./experiments/state-metadata-coverage-v1.md)。
- **双轨规则卡：** exactly 10 张圣保罗州环境许可规则卡，均为 `provisional`、`production_ready=false`、`runtime_integration=false`；未同期计时的工时保持 `null + reason`，没有事后估算。见 [实验记录](./experiments/rule-card-dual-track-brazil-sp-v0.1.md)。
- **实验④ PDF 摄取：** v1/v2 因源文本中不存在的错误锚点被显式作废；v3 对相同 10 份官方文本的 30 个源验证锚点达到 `30/30`、遗漏率 `0%`。该结果不代表字符错误率、OCR 或法律完整性。见 [v3 结果](./experiments/ingestion-qa-v3.md)与[作废审计](./experiments/ingestion-qa-v1.md)。
- **研究运营：** 已准备[葡中双语招募稿](./research/recruitment-post-pt-zh.md)和[标注指南 v0](./research/annotation-guide-v0.md)；因发布主体、渠道、计酬、合同与隐私联系人尚未由所有者填写，招募稿仍被发布前阻断，未虚构“已经发布/已经招募”。
- **分支治理：** 已记录[能力包分支决策](./decisions/2026-07-17-capability-pack-branch.md)；旧功能分支指针在私有 PR 合并和默认分支验收前保留，不执行破坏性删除。

## 已实现的关键控制

- 单租户实例强绑定 `INSTANCE_ORGANIZATION`；启动、认证和逐请求均拒绝跨组织账号。
- 生产关闭开放注册、SSO、第三方 LLM 外发和自动语料改写；正式账号只能交互式开通。
- Capability Pack、规则与语料以版本和内容哈希冻结，生成结果保留快照与归因。
- 路由强制同时具备巴西、圣保罗州、新能源制造和绿地设厂证据；里约、收购、扩建及既有工厂冲突均 fail-closed，显式城市不会被静默改写。
- 正式 review 写操作强制 `expected_revision`；整份 checklist 使用数据库 CAS，复核和审计日志同事务提交。
- 上传执行大小/数量/总量配额、魔数与容器检查、压缩炸弹及常见主动内容拦截；PDF 主动内容按完整 name token（含 `#xx` 转义）识别，避免前缀误报；`document_extract` 持久化快照另有 256 KiB 深层上限；原件权限受限。
- 辅助 JSON 状态使用进程锁、0600 权限、fsync 和同目录原子替换，写入失败保留旧文件。
- 后端与前端生产容器均为非 root、只读根文件系统、移除 capabilities 并启用 `no-new-privileges`。
- 发布构建采用显式 allowlist，拒绝 `.env*`、用户材料、数据库、缓存、自动化测试/Capability Pack 测试夹具和检测到的密钥；仅保留 1 个无敏感信息的公开演示样本。

## 首次试点启用清单

以下条件必须全部满足并留档：

1. GitHub 仓库已设为 Private；冻结分支经 PR 审核，所有 Actions 绿色，尤其是 `production-compose-smoke`。
2. 使用全新 PostgreSQL，或仅使用已有 `alembic_version` 且完成迁移演练的数据库；禁止对未知旧库直接 `stamp head`。
3. 外层 TLS 只开放 443，配置 HSTS，并按真实客户端 IP 对登录入口限流；Compose 端口继续只绑定 127.0.0.1。
4. 随机 `SECRET_KEY`、数据库密码和备份密钥由客户密钥管理系统提供，不进入仓库、镜像或发布 ZIP。
5. 每个正式用户由管理员交互式创建并绑定唯一试点组织；关闭演示账号和所有开发环境配置。
6. 书面确认数据保留、删除、备份、恢复演练、访问人员和试点退出责任人。
7. 上传只接受受管终端或 DMS 已扫描的内部材料；下载原件在隔离查看器中打开。
8. 每次定稿导出审计包并计算 SHA-256，转存到客户现有的对象锁/WORM 或等效不可变归档。
9. 巴西执业律师逐项核对 S2/S3 项、法源定位、时点有效性和个案适用，之后才允许对业务交付。
10. 对外试点前由权利人与客户签署明确的试点使用授权、保密、数据处理、支持责任和退出条款；仓库本身不附带也不默示开源或商用许可。

## 保留限制与扩围门槛

- **不是完整 AV/CDR。** 当前主动内容筛查不能排除合法结构文件中的所有恶意载荷。接收外部不可信材料前必须接入并验收企业 AV/CDR。
- **不是抗特权管理员篡改的审计系统。** 数据库内审计与 CAS 可防应用并发覆盖，但没有内置数字签名、哈希链或 WORM；相关保证依赖客户外部不可变归档。
- **不是法律正确性基准。** 质量门借鉴 LegalBench/LawBench 的任务化评估思路和 RAGChecker 的检索诊断方法，但当前 53 条可召回内容仍为 provisional，必须专家复核。
- **不是多租户 SaaS。** 单客户组织边界是本 RC 的硬前提；多租户、第二客户或共享数据库需要重新设计与验收。
- **不是生产 SSO/LLM 版本。** OIDC 与第三方模型外发均在生产 fail-closed；启用前必须单独完成安全、隐私与数据处理评估。
- **依赖与基础镜像仍需持续维护。** Python/npm 版本已锁定并审计，GitHub Actions 已固定 SHA；Python lock 尚未携带 wheel hashes，基础镜像尚未固定 OCI digest，后续供应链迭代应补齐并重新验证多架构构建。

工程治理基线参考 [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)、[OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/) 与 [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)。法律/RAG 评估方法参考 [LegalBench](https://arxiv.org/abs/2308.11462)、[LawBench](https://arxiv.org/abs/2309.16289) 与 [RAGChecker](https://arxiv.org/abs/2408.08067)。这些参考仅用于工程与评估方法，不构成对巴西法律内容的背书。
