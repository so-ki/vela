# Vela 需求追踪与完成判据

> 本表是需求、代码、测试与外部验收之间的统一状态口径。`implemented` 只表示代码存在；只有达到“完成判据”并附证据后才可标记 `accepted`。法律内容、生产部署和客户验收不得由工程测试代替。

## 状态定义

| 状态 | 含义 |
|---|---|
| `accepted` | 已达到本表完成判据，并有可复核证据 |
| `implemented` | 工程实现完成，尚缺独立验收或外部条件 |
| `partial` | 只有窄范围实现，不得宣传为完整能力 |
| `blocked_external` | 代码可继续准备，但最终完成依赖具名外部主体、凭证或真实环境 |
| `not_started` | 尚无可验收实现 |

## A. 当前受控试点

| ID | 需求 | 当前状态 | 完成判据 | 证据/下一动作 |
|---|---|---|---|---|
| A-01 | 业务提交材料，法务确认范围后才生成 | `accepted` | 未确认时零清单；确认后冻结输入与能力包身份 | `test_capability_pack_api.py`、`test_demo_onboarding.py` |
| A-02 | 30 项巴西圣保罗新能源绿地设厂清单 | `accepted`（工程） | 30 项稳定生成、版本与哈希冻结 | `brazil_new_energy.json`、Capability Pack manifest |
| A-03 | 确定性检索、S1/S2/S3 与拒答 | `accepted`（工程） | 零命中不补写结论；低可信命中进入人工复核 | `test_legal_quality_eval.py`、`test_review_safety.py` |
| A-04 | 中葡简报 | `accepted`（工程） | 简报由冻结结果生成，法源组成按真实命中披露 | `test_brief_source_disclosure.py`、全量后端测试 |
| A-05 | Word/PDF/审计包 | `accepted`（工程） | 精确 bytes 在签署前冻结；最终端点只返回 active release 绑定的原制品，携带可复核哈希 | `test_export_citation_service.py`、`test_delivery_assurance.py` |
| A-06 | 单客户私有化部署 | `accepted`（RC） | PostgreSQL migration、三镜像、登录/业务页面和 API 黄金路径通过 | GitHub Actions production compose smoke |
| A-07 | 法律内容达到可对客户交付质量 | `implemented / blocked_external` | 两名巴西执业律师认证 rules/corpus/gold release；场景律师签署精确制品；客户 UAT 与生产证据有效 | 代码门见 Alembic `0006`、`test_delivery_assurance.py`；真实证据仍为 0 |
| A-08 | Engineering Demonstrator RC0 | `accepted`（工程演示） | 八页 synthetic preview 可运行、可理解、可验证；全部拟制对象携带四元组且正式 Gate 仍阻断；desktop/mobile smoke、前后端回归和 frozen hash 全绿 | EV-0030~EV-0033；不得外推为法律内容、受控试点或正式客户发布就绪 |

## B. 冻结讨论中的机制层

| ID | 需求 | 当前状态 | 完成判据 | 证据/下一动作 |
|---|---|---|---|---|
| B-01 | 六状态材料账本 | `accepted`（工程） | 每个材料块仅处于一个允许状态；转换受控、留痕、并发安全 | `test_mechanism_layer.py`、Alembic `0003` |
| B-02 | 事实五元组 | `accepted`（工程） | 主体、属性、值、时间、出处 block_id、事实包版本和业务确认状态均可追溯 | `test_mechanism_layer.py`、机制层 API |
| B-03 | Claim Compiler | `accepted`（工程） | 每个输出主张绑定 checklist、已确认事实和落地法源；缺任一必要证据时 fail-closed | `test_mechanism_layer.py`；定稿门禁另见 B-05 |
| B-04 | CoverageTask/覆盖证明 | `accepted`（工程） | 明确分母哈希、已覆盖、未覆盖、不可判定；无官方分母时禁止声称穷尽 | `test_mechanism_layer.py`、CoverageProof API |
| B-05 | Answerability Gate | `accepted`（工程） | 每次最终下载重算 checklist/brief/facts/evidence、Claim 与 CoverageProof；缺失/过时/篡改均阻断并审计 | `answerability_gate_service.py`、`test_demo_onboarding.py` |
| B-06 | 审计日志 | `accepted`（应用层） | 关键写操作与复核同事务记录 | 审计原子性与 audit bundle 测试 |
| B-07 | 抗特权管理员篡改 | `blocked_external` | 客户 WORM/对象锁或签名哈希链部署并演练恢复 | 当前仅应用审计与导出 SHA-256 |
| B-08 | “删除巴西”平台边界 | `accepted`（工程） | 移除正式巴西包后，非真实 fixture 仍能完成生成/拒答测试；核心不得含巴西默认回退 | `test_country_independent_fixture_flow.py` 阻止读取正式 Brazil manifest/rules/corpus |
| B-09 | 历史对象多版本读取与就绪门 | `accepted`（工程） | compiler/proof/snapshot/release 按存储版本精确读取；reader 只增不减；未知版本在使用时及 production readiness fail-closed；空库可启动；不得自动改写历史对象 | versioned registry、`/api/v1/readiness`、Alembic `0007`、`test_version_readiness.py`、`test_delivery_release_schema_migration.py` |

## E. 真实客户交付保证

| ID | 需求 | 当前状态 | 完成判据 | 证据/下一动作 |
|---|---|---|---|---|
| E-01 | OAB 凭证与职责分离 | `implemented / blocked_external` | 持证人不能自核验；admin 不能代签；只有 `review.finalized_by_id` 对应主审可冻结/签场景；CNA/ConfirmADV 报告 exact bytes 入库且不得跨凭证复用 | 代码与非主审/报告复用攻击测试已完成；等待真实律师 |
| E-02 | 两律师法律内容 release | `implemented / blocked_external` | 两名不同有效律师签名覆盖精确 pack/rules/corpus/gold hashes | `LegalContentCertification`；等待真实双签和 gold set |
| E-03 | 精确制品签名 | `implemented / blocked_external` | 冻结 DOCX/PDF/audit bytes；场景主审签 manifest；签名核验与发布前均重验 bytes/全部元数据；管理员核验 ITI 报告 | `ScenarioDeliveryArtifact/ExpertAttestation` 与签前篡改攻击；等待真实签名 |
| E-04 | 客户 UAT/生产证据 | `implemented / blocked_external` | UAT 与 production `target_environment_id`、commit、image digest、SBOM、provenance、runtime probe 一致；构建描述符与回执 exact bytes 入库，回执绑定上述字段 | API 与 receipt 重算已实现；等待客户环境 |
| E-05 | 最终 release 与下载 | `accepted`（工程） | 最终 admin 未参与该 release 的任一证据核验；schema 1.1 checkpoint 绑定全部关键证据及原件 manifest；统一 evaluator 逐 bytes 重算；最终端点只返回原冻结 bytes；撤回/过期/篡改立即阻断 | `test_delivery_assurance.py` 的同 admin 放行、签前/证据 bytes、撤回原件与 release note raw-SQL 攻击；角色化证据台 |
| E-06 | 证据原件与手填 hash 分离 | `accepted`（工程） | 凭证、签名、UAT、gold/eval 和部署提交必须引用按角色/场景绑定的受控 exact bytes；签名/报告/UAT 原件不得重绑其他 manifest、快照或环境；无原件、过期、撤回或哈希不符即阻断 | Alembic `0006`；`DeliveryEvidenceObject`；伪 hash、重绑、bytes 篡改和撤回攻击测试 |

## C. 法律研究与数据质量

| ID | 需求 | 当前状态 | 完成判据 | 证据/下一动作 |
|---|---|---|---|---|
| C-01 | 州级元数据实验 | `accepted` | 预注册阈值和 30 条结果均留档 | `experiments/state-metadata-coverage-v1.md` |
| C-02 | PDF/OCR 摄取 QA | `partial` | 至少包含真实扫描/OCR 样本，报告字符错误率、版面/脚注/修订注记错误率 | 现有 v3 只证明 30 个锚点，不能外推 OCR |
| C-03 | 10 张双轨规则卡 | `partial` | 法条轨整合全部已知修订，记录工时，并由专家双人核验/仲裁 | 现有卡只作方法审计，`production_ready=false` |
| C-04 | 30 张可运行规则卡 | `not_started` | 每张具有要件、例外、后果、所需事实、版本和认证记录，并接入 runtime | 不得把 30 个 checklist item 等同为规则卡 |
| C-05 | 3 案内部回归集 | `not_started` | 合成/去标识案例，双人独立标注、第三人仲裁、版本冻结 | 需先完成招募和数据协议 |
| C-06 | 研究标注者招募 | `blocked_external` | 招募主体、渠道、计酬、合同、隐私联系人确定且帖子真实发布 | 现有仅为双语发布稿 |

## D. 原始产品愿景扩展

| ID | 需求 | 当前状态 | 完成判据 | 证据/下一动作 |
|---|---|---|---|---|
| D-01 | 墨西哥/智利能力 | `not_started` | 每一法域拥有独立 pack、官方语料、法律核验和端到端回归 | 不允许复制巴西规则或默认值 |
| D-02 | 矿业/跨境电商 | `not_started` | 独立事实 schema、规则卡、红旗与报告模板均通过场景验收 | 先选择一个差异大的第二 pack |
| D-03 | 西语检索与报告 | `not_started` | 西语材料路由、检索评测、术语表、报告与母语法律复核完成 | 模型接入不能替代法律语料和评测 |
| D-04 | 实时多源法规/判例同步 | `partial` | 官方源探测、内容版本化、差异审核、人工发布和回滚全链路运行 | 已实现不可变候选版本、结构化 diff 与人工 registry 状态机；尚无调度、current、corpus 发布/回滚 |
| D-05 | OA/合同系统连接器 | `blocked_external` | 指定 OA、服务账号、字段映射、webhook/重试、权限和集成测试 | 通用 REST API 已有，具体连接器尚无 |
| D-06 | 多租户 SaaS | `not_started` | 租户级数据库/存储/密钥/审计隔离经安全测试 | 当前设计明确为单客户单实例 |
| D-07 | 计费、额度和订阅 | `not_started` | 计量口径、账单、退款、配额与财务对账测试完成 | 商业计划不能算作实现 |
| D-08 | 正式生产 SSO/第三方 LLM | `blocked_external` | 客户 IdP/模型 DPA、数据分类、出境评估、密钥和红队测试完成 | RC 生产配置保持 fail-closed |

## 发布声明规则

1. 对外只能声明达到 `accepted` 的范围；括号中的“工程”“RC”限定语不得删除。
2. `implemented` 不等于真实部署，`partial` 不得缩写成“已支持”。
3. `blocked_external` 只有在具名责任人、真实证据和日期进入审计记录后才能转为 `accepted`。
4. 每次合并影响本表的代码或法律制品时，必须同步更新状态、完成判据证据和 RC 记录。
