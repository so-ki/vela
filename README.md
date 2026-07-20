# Vela 合规协查过程保证平台

Vela 是面向中国企业法务的拉美投资前合规协查过程保证平台。

## 当前验证范围

- 首个完成端到端验证的 Capability Pack：**巴西 · 圣保罗州 · 新能源制造 · 绿地设厂**
- 当前演示案例：**Aurora 储能系统集成工厂（虚构测试案例）**
- 当前只完成上述首个 Pack 的端到端验证，覆盖范围不扩展至整个拉丁美洲、巴西全国或市级规则。
- 法律内容状态为 `provisional`，仍须由律师复核与确认。
- 律师认证、客户 UAT、生产部署和正式 Release 均为 `blocked_external`。
- Vela 用于保障合规协查过程，不替代律师，也不构成正式法律意见。

## 启动比赛环境

```bash
git switch codex/vela-final-handoff-20260720
./scripts/start_competition.sh
```

启动后访问：

- 前端：<http://127.0.0.1:5180>
- 后端：<http://127.0.0.1:8010>

## 演示账号与路径

### 业务角色

- 账号：`biz@demo.vela`
- 密码：`Demo1234!`
- 路径：<http://127.0.0.1:5180/competition/1/business>
- 职责：材料、事实确认、补件和提交法务。

### 法务角色

- 账号：`legal@demo.vela`
- 密码：`Demo1234!`
- 路径：<http://127.0.0.1:5180/competition/1/overview>
- 职责：项目总览、材料与事实、固定 30 项、法律研究、Claim 与缺口、CoverageProof、交付中心和审计记录。

## 最终文档

- [用户手册](docs/submission/USER_MANUAL.pdf)
- [演示案例](docs/submission/DEMO_CASE.pdf)
- [评审指南](docs/submission/EVALUATOR_GUIDE.pdf)

GitHub 文档用于项目交接。实际比赛上传文件是单独整理的三份 PDF 和一份 MP4；MP4 不存放在 GitHub 仓库中。

## 交接说明

仓库中可能保留早期研发阶段的历史脚本或文档；它们不属于当前比赛入口、当前演示案例或运行基准。对外交接只以本 README、`start_competition.sh` 和 Aurora 比赛环境为准。本轮仅纠正首页说明，不删除历史文件。
