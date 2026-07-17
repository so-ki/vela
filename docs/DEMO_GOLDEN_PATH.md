# 复赛演示 Golden Path

> 3 分钟路演 **只走这一条显式确认链路**；不存在绕过业务知情或法务确认的一键生成入口。

## 启动

```bash
git clone git@github.com:so-ki/vela.git
cd vela
./scripts/start.sh
```

浏览器打开前端（默认 `http://localhost:5173`），后端 `http://localhost:8000/docs`。

## 账号

| 角色 | 邮箱 | 密码 |
|------|------|------|
| 业务 | biz@demo.vela | Demo1234! |
| 法务 | legal@demo.vela | Demo1234! |

本地 `./scripts/start.sh` 会收敛创建这两个账号，并为法务账号预置 `demo-legal-playbook-v1.0.0`；两账号可立即按下方链路协作。生产部署默认不创建演示账号；只有隔离演示环境显式设置 `SEED_DEMO_USERS=true` 才会 seed，正式生产必须保持 `false`。

当前只有一个正式 Capability Pack：`brazil_new_energy_greenfield`。测试 fixture 不代表真实法律能力；系统输出是待法务复核的协查底稿，不构成正式法律意见。

## 逐步演示（约 3 分钟）

| 步骤 | 角色 | 操作 | 话术要点 |
|------|------|------|----------|
| 1 | 业务 | 登录 → 上传 `scripts/fixtures/sample_storage_project.txt` → 查看当前 Capability Pack 卡片 → 勾选知情并提交 | 「这是 allowlist 内的公开演示材料，不是用户上传数据；业务提交事实并知悉当前支持边界，此时不生成」 |
| 1b | 任意 | （可选）工作台 → **AI 设置** 配置 Qwen/SiliconFlow 并测试连接 | 「LLM 可选；Key 存用户偏好，不进 git」 |
| 2 | 法务 | 切换 `legal@demo.vela` → 查看场景卡、适配结论和缺口面板 → 选择维度 → 点击 **确认范围并生成** | 「法务确认适用范围；系统原子冻结 Capability Pack、规则、语料和检索配置」 |
| 3 | 系统 | 同一 generation attempt 生成清单与 RAG → 展示法条片段 + LexML 链接 | 「读页面不会触发二次生成，失败重试沿用原快照」 |
| 4 | 系统 | 指出 **70 分门控**、S2/S3「需法务复核」标签 | 「低于阈值硬阻断，见 `docs/match_tier_and_gate.md`」 |
| 5 | 系统 | 生成中葡双语简报（可开 LLM 润色） | 「LLM 只润色，不新增法条」 |
| 6 | 法务 | 复核工作台逐条确认 → 定稿 | 「这是经法务复核的协查底稿，不构成正式法律意见」 |
| 7 | 法务 | 导出 Word 协查底稿 | 「可交付成果，含免责声明与溯源」 |

## 自动化验收（答辩前必跑）

```bash
./scripts/verify_e2e.sh
```

通过即表示 golden path 与 CI 脚本一致。

## 备用：现场网络/LLM 不稳定

1. 关闭 LLM 润色，仍走同一条业务提交 → 法务确认链路；规则模板、关键词检索和门控可离线演示。
2. 若服务不可用，只展示冻结证据、流程图与故障边界；发布 ZIP 不携带历史 docx，也不得用旧输出冒充本次实时生成结果。
3. 不调用 `/scenarios/demo/sample`、`generate-and-submit` 或直接 `POST /scenarios`；这些旧入口均返回 `410 Gone`。

## 不要分散评委注意力

演示中 **暂不展开**：SSO、合同审查、材料 OCR、六国扩张、融资叙事。  
差异化能力可在 Q&A 用一页图 `docs/vela_differentiation_v2.html` 补充。

## 相关文档

- [匹配度与门控说明](./match_tier_and_gate.md)
- [合规与安全](./compliance_and_security.md)
- [3 分钟汇报稿](./星瀚杯_3分钟汇报稿_泳道简版.md)
