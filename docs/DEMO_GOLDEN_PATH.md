# 复赛演示 Golden Path

> 3 分钟路演 **只走这一条线**；备用方案见文末「一键样本」。

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

## 逐步演示（约 3 分钟）

| 步骤 | 角色 | 操作 | 话术要点 |
|------|------|------|----------|
| 1 | 业务 | 登录 → 工作台 → 「BYD 坎皮纳斯」或提交中文场景 | 「中文输入，系统自动生成巴西投资协查清单」 |
| 1b | 任意 | （可选）工作台 → **AI 设置** 配置 Qwen/SiliconFlow 并测试连接 | 「LLM 可选；Key 存用户偏好，不进 git」 |
| 2 | 法务 | 切换 `legal@demo.vela` → **先看缺口面板** → 可选采纳 LLM 建议议题 → 确认范围 | 「缺口优先 Gate A，法务定范围，不是 AI 自动开查」 |
| 3 | 系统 | 触发 RAG → 展示法条片段 + LexML 链接 | 「~70 条精选语料 + 外链官方法源，不是聊天瞎编」 |
| 4 | 系统 | 指出 **70 分门控**、S2/S3「需法务复核」标签 | 「低于阈值硬阻断，见 `docs/match_tier_and_gate.md`」 |
| 5 | 系统 | 生成中葡双语简报（可开 LLM 润色） | 「LLM 只润色，不新增法条」 |
| 6 | 法务 | 复核工作台逐条确认 → 定稿 | 「协查工具 + 律师定稿，非正式法律意见」 |
| 7 | 法务 | 导出 Word 协查底稿 | 「可交付成果，含免责声明与溯源」 |

## 自动化验收（答辩前必跑）

```bash
./scripts/verify_e2e.sh
```

通过即表示 golden path 与 CI 脚本一致。

## 备用：现场网络/LLM 不稳定

1. 登录 `legal@demo.vela`
2. 调用 **「一键完整样本」**（API：`POST /api/v1/scenarios/demo/sample` 或前端等价入口）
3. 直接打开预生成的 BYD 坎皮纳斯 docx 样本

## 不要分散评委注意力

演示中 **暂不展开**：SSO、合同审查、材料 OCR、六国扩张、融资叙事。  
差异化能力可在 Q&A 用一页图 `docs/vela_differentiation_v2.html` 补充。

## 相关文档

- [匹配度与门控说明](./match_tier_and_gate.md)
- [合规与安全](./compliance_and_security.md)
- [3 分钟汇报稿](./星瀚杯_3分钟汇报稿_泳道简版.md)
