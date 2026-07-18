# Vela 自我反驳与修复裁决（2026-07-18）

本记录不是“证明产品完美”，而是主动采用最不利解释攻击真实客户交付门。结论是：工程门可以继续加固，但真实律师、真实客户与真实生产环境的事实不能由代码、论文或第二个模型生成。

## 最强反对意见与裁决

| ID | 最强反对意见 | 复现前状态 | 裁决与修复 | 当前证据 |
|---|---|---|---|---|
| SR-01 | 任意 `legal` 用户都可能冻结或签署别的律师定稿的场景，`n` 个律师身份并不等于该场景责任人 | 成立 | **accept**。冻结和场景签署现在必须匹配 `review.finalized_by_id`；定稿人必须仍是精确 `legal` 角色 | `test_delivery_assurance.py` 的非主审签署攻击 |
| SR-02 | 同一个 admin 可以核验凭证、签名、内容认证和部署证据后，再批准最终 release；形式上多对象，实质上单人放行 | 成立 | **accept**。最终 release admin 必须与上述全部核验 actor 分离；运行时 evaluator 也重算该关系 | 同一 admin 发布被拒，第二个独立 admin 才能放行 |
| SR-03 | 候选 bytes 在律师提交签名后、管理员批准签名前被替换，旧实现直到下载时才可能发现 | 成立 | **accept**。签名批准和最终发布两个事务点都重新读取 DB、校验三个唯一制品、全部 manifest 元数据、长度与 SHA-256 | 签名前 raw SQL bytes 篡改攻击 |
| SR-04 | release hash 只绑定对象 ID；具有 DB 写权限者可改 UAT、部署、内容签名或发布说明而不改变 ID | 成立 | **accept**。release checkpoint 升级为 schema `1.1`，绑定场景签署证据、artifact manifest、UAT、内容双签、三份律师凭证、完整部署证据和 release note 的派生哈希 | raw SQL 修改 release note 后 `delivery_release_hash_invalid` |
| SR-05 | 较长的部署/release 有效期可越过内容认证、签名证书或律师凭证的到期日 | 部分成立 | **accept**。部署不得晚于内容认证；release 不得晚于证据链任一凭证、证书、签署、UAT、内容认证或部署证据 | 创建时拒绝 + evaluator 运行时重算 |
| SR-06 | UI 仍会诱导刚完成核验的 admin 点击最终发布，产生可预见的权限错误 | 成立 | **accept**。证据台显示四眼冲突原因并禁用最终按钮；服务端仍是权威门 | Vue 组件测试与 TypeScript 构建 |
| SR-07 | 上述对象只保存 URL/手填 hash，调用者可用任意 64 位字符伪装 OAB、ITI、UAT、gold 或部署证据 | 成立 | **accept**。新增按角色/场景绑定的不可变内容寻址原件库；全部业务动作与发布 evaluator 从 DB 重读 bytes/长度/SHA-256/时效/状态；构建 receipt 绑定独立 descriptor、commit、迁移、环境与镜像 | 伪 hash 被拒绝，原件 raw-SQL bytes 篡改/撤回后 `delivery_evidence_objects_invalid` |
| SR-08 | 有效原件可能被重放到另一律师凭证、artifact/content manifest 或 UAT 环境 | 成立 | **accept**。OAB 申报/核验报告禁止跨凭证复用；场景签名与报告锁定 artifact manifest；内容双签/报告锁定 content manifest；UAT 计划/结果锁定 snapshot 与 target environment | 凭证、场景签名、内容签名与 UAT 重绑攻击测试 |

## 修复后的不可绕过不变量

1. 场景主审律师身份来自冻结 review，不从“当前登录者声称自己是律师”推断。
2. 最终 release 至少需要业务提交人、场景主审律师、两名内容认证律师、证据核验 admin 和另一名最终发布 admin；发布 admin 也不得是客户 UAT 签署人。同一真实主体使用多个账号仍属于组织治理和身份系统需要阻止的外部风险。
3. 数字签名提交、签名核验、最终发布、每次正式下载均有重新验证点；任何一点失败都不能返回正式制品。
4. release hash 是证据链检查点，不是法律正确性证明；ITI 签名有效也不证明文档内容真实或法律结论正确。
5. ORM 不可变限制不是唯一防线；evaluator 会从数据库记录重算派生哈希，用 raw SQL 绕过 ORM 仍会 fail-closed。
6. 字段里的 SHA-256 不再被当成证据；它必须解析到正确类型、上传人/场景、当前有效的 exact bytes。release hash 另外绑定全部原件 manifest。

## 仍不能由程序解决

- 两名账号是否真的是两个独立自然人，必须由客户 IdP、用工/委聘与利益冲突流程证明；
- OAB/ConfirmADV 和 ITI 报告是否真实，仍需外部查询证据与具名核验人；
- 原件库能证明“当时上传的是这些 bytes”，不能自动证明报告内容真实、官方网页未被伪造或法律结论正确；
- rules/corpus/gold 的法律正确性与覆盖充分性，必须由巴西律师和真实评测集验收；
- 客户 UAT、生产镜像、KMS、WORM、备份恢复、LGPD/DPA 与 runtime probe 必须来自目标环境；
- 数据库超级管理员可同时改记录与重算所有哈希。要抵抗该主体，必须把原件与签名/checkpoint 写入客户控制的 KMS、透明日志或对象锁/WORM。

因此产品状态仍是 `engineering-implemented / external-evidence-blocked / not-production-authorized`，不能改写为“完全完美”或“已可真实客户交付”。

## 可复核验收

```bash
cd backend && python -m pytest tests -q
cd frontend && npm run test:components && npm run build
git diff --check
```

本轮本地结果：后端 `295 passed`；前端 `29 passed`；Vite `158 modules transformed`；Alembic base/head 往返与漂移检查、controlled-pilot 法律质量门、发布边界和差异检查通过。远端 CI 必须以具体 commit 的 GitHub Actions 结果为准。
