# Vela 真实客户交付保证

日期：2026-07-18
状态：`engineering-implemented / external-evidence-blocked / not-production-authorized`

## 可宣称的产品边界

Vela 当前代码实现的是：**由巴西执业律师控制、签署并承担专业判断责任的法律协查工作底稿系统**。它不是自动出具巴西法律意见的系统。

巴西《律师法》把法律咨询、顾问和法律指导列为律师专属活动；OAB 的生成式 AI 建议要求专业人工监督，不得把律师专属活动委托给 AI：

- [Lei 8.906/1994](https://planalto.gov.br/ccivil_03/leis/l8906.htm)
- [OAB Recomendação 001/2024](https://diario.oab.org.br/pages/materia/842347)

因此，模型、检索器、第二个模型或工程测试都不能把 `provisional` 自动升级为法律真值。

## 不可绕过流程

```text
冻结 scope / input / Capability Pack
  → 业务确认事实
  → Claim Compiler + 法务逐项决定
  → 可重算 CoverageProof / Answerability Gate
  → 两名独立巴西律师认证 rules + corpus + gold release
  → API 生成唯一 canonical content manifest/hash 供双签
  → 冻结 exact DOCX/PDF/audit bytes
  → 场景参与者只以“未获客户交付授权”候选件完成签署/UAT
  → 场景律师外部数字签名 artifact manifest
  → 独立管理员核验 ITI VALIDAR 报告
  → 客户 UAT 绑定 target_environment_id
  → production provenance / image digests / SBOM / runtime probe
  → 限时 ScenarioDeliveryRelease
  → 只下载原冻结 bytes
```

任一依赖被撤回、过期、篡改、错绑或落后于当前场景，`delivery_allowed=false`。最终 Word/PDF/audit 端点返回 `409`，不会临时重新渲染另一个文件冒充已签制品。

## 三方职责分离

| 主体 | 可以做 | 不能做 |
|---|---|---|
| `business` 项目提交人 | 确认事实、签客户 UAT | 决定法律适用、核验律师或发布 |
| 精确 `legal` 角色 | 确认 Claim、冻结候选制品、用本人已核验凭证签署 | 自核验 OAB 凭证、核验本人签名、创建发布授权 |
| `admin` | 独立核验凭证/签名/部署证据，创建或撤回 release | 被当作 legal 专家代签；放行本人签署的法律结论 |

生产法律内容另要求两个不同、当前有效、OAB 状态为 `regular` 的巴西律师覆盖精确 rules/corpus/gold 哈希。该双人政策是 Vela 的高风险控制，不宣称为巴西法律强制规定。

## 数字签名边界

巴西官方 ITI VALIDAR 可以验证 ICP-Brasil、GOV.BR 等受支持签名的签署身份和签后完整性。ITI 同时明确：验证结果不证明文档内容真实或法律结论正确。

- [ITI VALIDAR](https://validar.iti.gov.br/)
- [ITI VALIDAR 说明](https://validar.iti.gov.br/sobre.html)
- [OAB Cadastro Nacional](https://consulta.oab.org.br/)
- [OAB ConfirmADV](https://confirmadv.oab.org.br/)

代码因此保存签名 artifact hash、VALIDAR 报告 hash、证书主体/序列/有效期，并要求独立管理员决定；它从不把普通数据库按钮称为数字签名。

签名前必须先调用内容 manifest 或场景 artifact manifest 接口取得 canonical JSON/hash；内容认证与专家签署提交时会重算并拒绝任何不一致的签名 hash。候选文件只向该场景提交人、legal 和 admin 开放，响应带 `Cache-Control: no-store` 与 `X-Customer-Delivery-Authorized: false`；正式导出仍必须通过 active release 门。

## 部署与 gold 证据

`DeploymentEvidence` 必须绑定：

- Git commit 与 migration head；
- backend/frontend/database 三镜像 digest；
- CI run、构建 artifact、SBOM 和安全证据；
- provenance 和客户环境 runtime probe；
- config schema hash；
- 精确 Capability Pack、rules、corpus 哈希；
- gold dataset、预注册 evaluation policy 和 evaluation run 哈希，且状态为 `passed`；
- 与客户 UAT 完全相同的 `target_environment_id`。

工程参考可采用 [SLSA](https://slsa.dev/spec/v1.2/)、[Sigstore Cosign](https://docs.sigstore.dev/cosign/signing/overview/) 和 [in-toto](https://github.com/in-toto/in-toto)。这些工具证明来源和完整性，不证明法律内容正确。

## 已由代码实现

- CAS/状态机、时效、撤回、职责分离；
- 当前 checklist/facts/evidence/brief Claim 快照重算；
- CoverageProof 与 affirmative Claim 的 fail-closed 门；
- OAB/ConfirmADV 和 ITI 官方域名限制；
- 两律师 rules/corpus/gold release 认证对象；
- 精确 artifact bytes 冻结与签名 manifest；
- canonical manifest 预览、受控候选件审阅下载及各证据对象列表接口；
- 业务、legal、admin 分权的客户交付证据台，以及凭证/签名/UAT/内容认证/部署/release 撤回入口；
- UAT 与 production 环境、pack、gold、部署证据绑定；
- release hash 重算与最终端点统一门禁；
- 应用 ORM 不可变核心、数据库 check/partial unique、审计记录；
- 过期、撤回、bytes 篡改、release hash 篡改时即时阻断。

## 仍为外部阻断，程序不能伪造

当前仓库没有以下真实证据，所以默认状态必须保持 `blocked_external`：

1. 两名真实巴西执业律师的委聘、OAB/ConfirmADV 实查和利益冲突确认；
2. 生产 rules/corpus 的逐项专业认证；当前语料 `expert_verified=0`；
3. 经双人独立标注、分歧仲裁并冻结的巴西 gold acceptance set；
4. 客户在其真实环境完成的 UAT；
5. 新分支远端 CI、三镜像 digest/CVE/SBOM/provenance 和 runtime probe；
6. 客户 IdP/KMS、TLS、备份恢复、DPA/LGPD 和事故流程；
7. 客户控制的 WORM/object lock。应用数据库无法抵抗拥有数据库超级权限的恶意管理员。

这些证据真实进入 API 前，任何 AI、开发者或管理员都不能把状态改写为“可对真实客户交付”。

## 审核方法

审核者应从 [`REQUIREMENTS_TRACEABILITY.md`](./REQUIREMENTS_TRACEABILITY.md) 和 [`ai-review/CLAUDE_CODE_ARGUE_PROMPT.md`](./ai-review/CLAUDE_CODE_ARGUE_PROMPT.md) 开始，重点攻击：

- admin 冒充律师或同一人自核验/自签/自发布；
- 过期或撤销凭证重放；
- 签署后修改事实、法源、规则、模板或 bytes；
- UAT 与 production 环境错绑；
- 伪造合法 CI URL但替换镜像 digest；
- 并发产生两个 active release；
- 修改 release hash 或 certification manifest；
- 法源变化后继续下载旧 release；
- 将签名有效错误宣传成法律内容正确。
