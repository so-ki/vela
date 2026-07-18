# Vela API 集成说明

Base URL（本地）：`http://127.0.0.1:8000/api/v1`

交互式文档：

- Swagger UI（仅本地开发）：http://127.0.0.1:8000/docs；生产受控试点不暴露 OpenAPI/Swagger/ReDoc
- ReDoc：http://127.0.0.1:8000/redoc

认证：除 `/health`、`/auth/login`、`/auth/register`、`/auth/sso/config` 外，请求头需携带：

```http
Authorization: Bearer <JWT>
```

## 核心流程 API

| 顺序 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 0 | GET | `/capability-packs` | 读取服务端正式启用的 Capability Pack；前端提示不具有路由权威性 |
| 0b | GET | `/capability-packs/catalog` | 读取正式包的维度、阈值与展示元数据 |
| 1 | POST | `/scenarios/extract-document` | 可选：上传 `.txt/.md/.docx/.pdf` 抽取事实供业务核对 |
| 2 | POST | `/scenarios/submit-materials` | **业务角色**：上传材料并确认已知当前支持边界，创建 `pending_scope`；不生成 |
| 3 | GET | `/scenarios/{id}` | 法务读取 `scenario_scope.proposed`、`fit_assessment`、材料与 `proposal_hash` |
| 4 | POST | `/scenarios/{id}/confirm-scope` | **法务角色**：原子确认场景/维度，冻结 Capability Pack、规则、语料和生成配置快照，并启动唯一 attempt |
| 5 | GET | `/scenarios/{id}` | 读取已持久化的清单、RAG、简报和 attempt 状态；不得通过读接口隐式生成 |
| 6 | POST | `/scenarios/{id}/review/init` | 仅基于已有生成结果初始化复核 |
| 7 | PATCH | `/scenarios/{id}/review/items/{code}` | 更新复核项；body 必须回传 `expected_revision` |
| 7b | POST | `/scenarios/{id}/review/return-to-business` | **法务**：退回业务在同一项目补充；body 必须回传 `expected_revision` |
| 8 | POST | `/scenarios/{id}/review/finalize?expected_revision={revision}` | **法务角色**：定稿复核记录；这一步本身不授予交付导出权限 |
| 8a | POST | `/scenarios/{id}/mechanism/claims/compile` → Claim 人工确认 → `/mechanism/coverage-proofs` | **法务角色**：为当前 checklist、事实和证据快照生成 Answerability 交付证明 |
| 8b | POST | `/scenarios/{id}/revise-and-resubmit` | **业务**：补充材料后重新进入 `pending_scope` |
| 9 | GET | `/scenarios/{id}/export/docx` | **法务角色**：仅下载 active release 绑定、签署前冻结的原始 Word bytes；不再临时重渲染 |
| 9b | GET | `/scenarios/{id}/export/pdf` | **法务角色**：仅下载 active release 绑定、签署前冻结的原始 PDF bytes |
| 9c | GET | `/scenarios/{id}/export/audit-bundle` | **法务角色**：仅下载同批冻结、已签署哈希覆盖的 canonical JSON bytes |

当前 `/capability-packs` 只返回一个正式包：`brazil_new_energy_greenfield`（巴西 · 新能源制造 · 绿地设厂）。自动化测试 fixture 不是法律能力，不进入生产 Registry 或发布制品。

`confirm-scope` 请求必须携带当前 `expected_proposal_hash`、`fit_decision` 和所选 `compliance_dimensions`。相同请求幂等返回已有快照或结果；不同参数的重复确认返回冲突。失败后仅可调用 `POST /scenarios/{id}/retry-generation`，并严格沿用原快照。

## 机制层 API（受控试点）

这些接口把“材料、事实、主张、覆盖”拆为独立、可审计对象；它们**不会**修改已冻结的 Capability Pack 或把临时来源自动写入正式语料。

| 方法 | 路径 | 权限与 fail-closed 规则 |
|---|---|---|
| GET | `/scenarios/{id}/mechanism/material-ledger` | 业务提交人或法务读取场景材料状态。 |
| PUT | `/scenarios/{id}/mechanism/material-ledger/{block_id}` | 业务可登记 `missing/received/unreadable/ambiguous`；`verified/not_applicable` 必须法务并附确认说明。更新必须带 `expected_revision`。 |
| GET / POST | `/scenarios/{id}/mechanism/facts` | 仅场景业务提交人可创建五元组事实（主体、属性、值、时间、`block_id`、事实包版本）；新事实只是 `submitted`。 |
| POST | `/scenarios/{id}/mechanism/facts/{fact_id}/confirm` | 仅原登记人可确认业务事实；未经业务确认的事实不能进入可确认 Claim。 |
| GET / POST | `/scenarios/{id}/mechanism/coverage-tasks` | 法务创建；必须给出官方分母引用、分母项及已覆盖项，`denominator_snapshot_hash` 为 `{source, denominator_ref, denominator_items}` 的稳定 SHA-256。它是工作任务，不等同于法律结论。 |
| POST / GET | `/scenarios/{id}/mechanism/claims/compile`、`/claims/latest` | 法务编译；每条 checklist 项都被纳入分母。缺事实或未落地法源一律 `refused`。 |
| POST | `/scenarios/{id}/mechanism/claims/{claim_id}/confirm` | 法务才能把 `awaiting_human_confirmation` 变为 `supported` 或 `refused`；暂存或待复核法源只可进入人工确认队列，不能自动支持主张。 |
| POST / GET | `/scenarios/{id}/mechanism/coverage-proofs`、`/coverage-proofs/latest` | 法务生成；只把 `supported` Claim 计入 covered，其他均保留为 uncovered/unanswerable。 |

当前 Claim 编译器只消费上述持久化事实记录，不把文件抽取出的临时文本当作已确认事实。`supported` 仅表示该受控场景内、经法务人工确认的限定主张；不代表法规检索已完整、专家认证已完成，或可直接作为正式法律意见。

### 不可绕过的交付 Answerability Gate

`GET /scenarios/{id}/brief` 始终是只读草稿预览，不要求 Claim/CoverageProof。Word、PDF 和 audit bundle 属于交付型制品，每次渲染前都会重新校验：

1. 使用最新 `ClaimCompilation`，且编译器版本为当前版本；
2. 对当前 checklist（含规则项语义哈希）、双语简报结论文字、全部持久化事实、完整法源 hit 哈希重新构造输入快照；
3. 重算 compiler input/output SHA-256，并核对 Claim 不可变字段与人工确认归属；
4. 所有 `gate_status=passed`、会作为肯定结论输出的条目必须对应 `supported` Claim，且中文交付文字必须与人工确认的 Claim statement 精确一致；显式 blocked/refused 项可以作为“无法回答”披露；
5. 最新 `CoverageProof` 必须绑定该 compilation，proof/denominator 哈希和计数必须能从当前 Claim 状态重算。

缺 compilation/proof、快照过时、结论待确认返回 `409 Conflict`；存储哈希、Claim 或 CoverageProof 无法重算返回 `422 Unprocessable Content`。响应 `detail.reason_codes` 给出机器可读原因；所有被阻止的交付尝试写入 `delivery.answerability_gate_blocked` 审计日志。audit bundle 的 `answerability_gate` 字段记录通过时使用的 compilation/proof/hash。

`review_status=pending/provisional` 不会被 Gate 或编译器改写为 `expert_verified`。它只有在法务显式确认限定 Claim 后才能支持该 Claim，且 audit bundle 仍在 `provisional_evidence_refs` 披露，`provisional_evidence_promoted=false`。

### 真实客户交付发布门

Answerability Gate 通过仍然**不能**下载正式制品。最终端点还会调用统一的 Customer Delivery Release Gate，依次要求：

1. 参与者先把按角色允许的证据 exact bytes 上传为不可变、内容寻址的 `DeliveryEvidenceObject`；后续提交只能引用系统重算得到的 SHA-256；
2. `legal` 专家提交 OAB CNA/ConfirmADV 凭证；另一 `admin` 依据官方报告原件核验为 `regular`，持证人不能自核验，同一报告不得复用于另一凭证；
3. 两名不同、凭证当前有效的巴西律师对精确 Capability Pack、rules、corpus、gold dataset/policy/run 哈希完成内容发布认证；
4. 法务冻结 DOCX、PDF 和 canonical audit JSON 的精确 bytes；API 返回元数据、manifest/hash，并只向场景业务提交人、legal、admin 提供带 `X-Customer-Delivery-Authorized: false` 的候选件审阅下载，不构成对客发布；
5. 场景律师用 PAdES/CAdES/XAdES 覆盖三个 artifact manifest，另一管理员核验 ITI VALIDAR 报告；该签名只证明签署身份与签后完整性，不证明内容正确；
6. 项目业务提交人提交客户 UAT，绑定客户组织、测试证据和目标环境 ID；
7. 管理员提交 production commit、三镜像 digest、migration head、CI、构建描述符/回执、SBOM、CVE/安全、provenance、runtime probe 与同一 gold run 证据；descriptor 与 receipt JSON 必须同时绑定当前 commit、迁移、环境和三镜像 digest，receipt 另外绑定 descriptor hash；
8. 另一发布动作把上述对象及证据原件 manifest 绑定为有时效、可撤回的 `ScenarioDeliveryRelease`。任一依赖过期、撤回、bytes/哈希变化或环境错绑，最终下载返回 `409`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST / GET | `/delivery-assurance/evidence-objects` | 按角色上传/列出受控证据原件；服务器限制 25MB、安全文件名与允许容器，计算 SHA-256 并冻结 bytes。 |
| GET | `/delivery-assurance/evidence-objects/{id}/download` | 仅原上传人或 admin 可下载核对；响应 `no-store`/`nosniff` 并返回 `X-Content-SHA256`。 |
| POST | `/delivery-assurance/evidence-objects/{id}/revoke` | 原上传人或 admin 撤回原件；所有引用它的 release 实时失效。 |
| POST / GET | `/delivery-assurance/credentials` | legal 提交并查看本人执业凭证；admin 可查看全部；business 无权读取。 |
| POST | `/delivery-assurance/credentials/{id}/decisions` | admin 独立核验、拒绝或撤回；`verified` 必须有 OAB 官方引用、证据哈希、`regular` 状态和有效期。 |
| POST | `/delivery-assurance/legal-content-certifications/manifest` | legal/admin 生成唯一规范化 rules/corpus/gold 签名清单及 SHA-256；此 hash 必须被双签覆盖。 |
| GET / POST | `/delivery-assurance/legal-content-certifications` | legal/admin 可列出认证；admin 记录两名不同已核验律师覆盖的 release；双签名必须引用 ITI VALIDAR。 |
| GET / POST | `/scenarios/{id}/delivery-assurance/artifacts` | legal 冻结精确 DOCX/PDF/audit bytes；授权参与者可列出元数据。 |
| GET | `/scenarios/{id}/delivery-assurance/artifact-manifest` | 获取当前同批次三个候选件的规范化 manifest 与 hash。 |
| GET | `/scenarios/{id}/delivery-assurance/artifacts/{artifact_id}/candidate` | 仅场景提交人、legal、admin 可下载 UAT/签名前候选 bytes；响应明确未获客户交付授权。 |
| GET / POST | `/scenarios/{id}/delivery-assurance/expert-attestations` | 列出签署；legal 提交覆盖三个 artifact hash 的外部签名证据，初始为 `pending_validation`。 |
| POST | `/scenarios/{id}/delivery-assurance/expert-attestations/{attestation_id}/signature-decision` | admin 独立核验签名为 `active` 或 `rejected`。 |
| GET / POST | `/scenarios/{id}/delivery-assurance/uat-acceptances` | 授权参与者可列出；仅项目业务提交人可签客户 UAT。 |
| GET / POST | `/delivery-assurance/deployments` | admin 列出或提交与内容认证、gold run 和目标环境绑定的生产部署证据。 |
| GET / POST | `/scenarios/{id}/delivery-assurance/releases` | 授权参与者可列出；admin 创建最终、限时、可撤回授权，且不得放行本人签署的法律结论。 |
| GET | `/scenarios/{id}/delivery-assurance/status` | 实时重算全部依赖，返回 `delivery_allowed` 与机器可读阻断原因。 |
| POST | `.../{evidence_id}/revoke` 或 `.../{acceptance_id}/withdraw` | 由原签署人、原 UAT 提交人或 admin 按对象权限撤回；状态改变后最终下载即时 fail-closed。 |

完整证据边界和外部启用清单见 [`docs/CUSTOMER_DELIVERY_ASSURANCE.md`](./docs/CUSTOMER_DELIVERY_ASSURANCE.md)。

## 法规来源候选与变化事件 API

该模块是与正式 Capability Pack corpus 隔离的候选登记簿。所有写操作要求法务角色；`active` 只表示该快照经 registry 审批，不表示唯一 current，也不会自动更新正式语料。

| 方法 | 路径 | 规则 |
|---|---|---|
| POST | `/legal/source-versions/candidates` | 保存不可变官方来源快照并创建文章/关系 diff；要求 HTTPS URL 与声明的官方域名一致。 |
| GET | `/legal/source-versions` | 按 `canonical_id`、`status` 和 `limit` 查询；响应明确 `release_scope=source_registry_only`。 |
| GET | `/legal/source-versions/{version_id}` | 读取单个候选/已审快照的元数据与哈希，不返回原文正文。 |
| POST | `/legal/source-versions/{version_id}/decisions` | 法务执行 `candidate → reviewed → active` 或 `candidate/reviewed → rejected`；条件更新防并发覆盖。 |
| GET | `/legal/change-events`、`/legal/change-events/{event_id}` | 查询不可变结构化变化事件。 |

URN 在跨法域记录中可空，但 `canonical_id` 与 `citation_id` 必填。`active`、`current_version_designation=not_assigned` 和 `capability_pack_corpus_updated=false` 三个字段必须一起理解；正式发布需另行设计人工 corpus 发布与回滚链。

## 角色

| role | 说明 |
|------|------|
| `business` | 上传项目事实与材料、确认知情、补充材料；不决定法律适用范围 |
| `legal` | 确认 Capability Pack 与协查维度、触发原子生成、复核、定稿、导出 |
| `admin` | 仅负责凭证/签名/部署证据核验和发布；不得作为 `legal` 专家代签 |

本地 `./scripts/start.sh` 会创建 `biz@demo.vela` / `legal@demo.vela`（密码 `Demo1234!`）。business demo 不需要 Legal onboarding；legal demo 已绑定 `demo-legal-playbook-v1.0.0`，可直接进入正式主流程。真实新 legal 用户仍须完成 onboarding，demo profile 不与其他用户共享。生产镜像默认 `SEED_DEMO_USERS=false`，不得依赖这些固定账号。

## SSO（OpenID Connect）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/sso/config` | 是否启用 SSO、是否允许密码登录/开放注册 |
| GET | `/auth/sso/login` | 302 跳转 IdP 授权页 |
| GET | `/auth/sso/callback` | IdP 回调；交换 token 后 302 至前端 `/login/sso/callback` |

生产环境变量与安全创建方式见 **[DEPLOYMENT.md](./DEPLOYMENT.md)**；发布 ZIP 不包含任何 `.env*`。

## Word 导出模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/export/config` | 当前模板（`law_school` / `legacy`）与文档标签 |

环境变量：

- `EXPORT_TEMPLATE=law_school` — 法学院标准《涉外投资合规法律研究意见书》
- `EXPORT_ORG_NAME` / `EXPORT_ORG_DEPARTMENT` / `EXPORT_RECIPIENT_LABEL` — 抬头与致/自/关于表

定稿后 `export/docx` 响应头 `Content-Disposition` 含 UTF-8 文件名，如 `{项目}_法律研究意见书.docx`。

模板名称与文件名仅表示导出版式；系统内容仍是须经法务逐条复核的协查底稿，不构成正式法律意见。

## 兼容与已关闭接口

| 方法 | 路径 | 语义 |
|------|------|------|
| POST | `/scenarios/{id}/retrieve` | 废弃的只读兼容别名；只返回已持久化 RAG，不启动检索 |
| POST | `/scenarios/{id}/brief` | 废弃的只读兼容别名；忽略 `polish`，不生成或润色 |
| POST | `/scenarios` | `410 Gone`；旧直接生成入口已关闭 |
| POST | `/scenarios/generate-and-submit` | `410 Gone` |
| POST | `/scenarios/demo/generate-and-submit` | `410 Gone` |
| POST | `/scenarios/demo/sample` | `410 Gone`；不再提供绕过范围确认的一键样本 |

## 法源与监测

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/legal/status` | 索引状态、语料版本、来源分布 |
| POST | `/legal/index?force=true` | 重建索引 |
| GET | `/legal/monitor` | 法规监测状态与提醒列表 |
| POST | `/legal/monitor/scan?force_reindex=false` | 手动扫描/刷新监测 |

## 法源语料维护（法务角色）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/legal/corpus/meta` | 维度、核查项编号、法源类型等元数据 |
| GET | `/legal/corpus?q=&dimension=&source=` | 列表/筛选 |
| GET | `/legal/corpus/{id}` | 单条详情 |
| POST | `/legal/corpus` | 新增法条条目 |
| PUT | `/legal/corpus/{id}` | 更新条目 |
| DELETE | `/legal/corpus/{id}` | 删除条目 |
| POST | `/legal/corpus/reindex?force=true` | 保存后重建索引 |

## 演示模板

| 方法 | 路径 |
|------|------|
| GET | `/rules/classification` | 兼容读取分类树；不表示存在多个受控试点能力包 |
| GET | `/rules/packs` | 兼容读取已注册规则制品；受控试点能力以 `/capability-packs` 为准 |
| GET | `/rules/catalog` | 当前规则包表单/清单配置（可选 `?pack_id=`） |
| GET | `/rules/demo-template` | BYD 坎皮纳斯投资协查演示 |
| GET | `/rules/demo-template/mining` | **501** — 矿产协查规则包尚未建设 |

## 嵌入 OA / 合规系统

1. 服务端调用 `POST /auth/login` 获取 JWT，或浏览器走 `/auth/sso/login` 企业 SSO
2. 按上表顺序调用 REST API
3. 定稿后导出：`export/docx`（法学院意见书）或 `export/pdf`（legacy 底稿）

CORS 默认允许 `http://localhost:5173`；生产环境在 `backend/.env` 配置 `CORS_ORIGINS`。
