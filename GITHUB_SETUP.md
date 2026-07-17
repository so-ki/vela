# GitHub 上传与邀请测试者

本地仓库已初始化并完成提交（**不含** `backend/.env` 与 API Key）。当前远端可见性必须在 GitHub 设置页单独核验；本文档不把“计划设为私有”写成“已经私有”。

## 一、在 GitHub 创建私有仓库

1. 登录 [https://github.com/new](https://github.com/new)
2. 填写：
   - **Repository name：** `vela-platform`（或你喜欢的名字）
   - **Visibility：** **Private**（仅指定人员可访问）
   - **不要**勾选 “Add a README”（本地已有）
3. 点击 **Create repository**

## 二、推送代码（在本机终端执行）

将 `<你的GitHub用户名>` 换成你的账号：

```bash
cd <本地仓库路径>

git remote add origin https://github.com/<你的GitHub用户名>/vela-platform.git
git branch -M main
git push -u origin main
```

首次 push 会要求登录：

- **Username：** 你的 GitHub 用户名
- **Password：** 使用 [Personal Access Token (classic)](https://github.com/settings/tokens)，权限勾选 `repo`
  - 不要用 GitHub 登录密码

### 若已配置 SSH

```bash
git remote add origin git@github.com:<你的GitHub用户名>/vela-platform.git
git push -u origin main
```

## 三、邀请指定人员测试

1. 打开仓库 → **Settings** → **Collaborators**（或 **Manage access**）
2. 点击 **Add people**
3. 输入对方的 **GitHub 用户名或邮箱**
4. 权限选 **Write**（可 clone + 提 Issue）或 **Read**（只读 clone）
5. 对方接受邮件邀请后即可：

```bash
git clone https://github.com/<你的GitHub用户名>/vela-platform.git
cd vela-platform
./scripts/start.sh
```

详细测试步骤见仓库内 **[TESTING.md](./TESTING.md)**。

## 四、对方本地还需自行配置

克隆后**不会**包含你的 API Key，测试者需：

```bash
cd backend
# 发布 ZIP 不含任何 .env*；可选 LLM Key 应由测试者通过自己的环境变量或密钥管理工具注入
```

本地演示账号由 `./scripts/start.sh` 或手工种子脚本创建。生产启动路径不提供演示账号开关，不得公开固定密码账号。

## 五、安全清单

- [x] `.env` 已在 `.gitignore`，未提交
- [ ] 确认 GitHub 仓库为 **Private**
- [ ] 若曾泄露 Key，在 DashScope 控制台轮换 `QWEN_API_KEY`
- [ ] 仅邀请可信 Collaborator

## 六、可选：发布 Release 供下载 zip

若对方不使用 Git，只能上传 allowlist 构建并通过自动扫描的 ZIP；不要在 Finder 或命令行直接压缩工作区：

1. 运行 `./scripts/build_submission_package.sh /tmp/vela-capability-pack-mvp.zip`
2. 再运行 `./scripts/check_release_boundaries.sh /tmp/vela-capability-pack-mvp.zip`
3. 仓库 → **Releases** → **Create a new release**，上传该已扫描文件

发布包不含任何 `.env*`；接收方必须通过自己的密钥管理渠道创建运行环境配置。

---

发布前仍须人工复核分支、变更清单和自动扫描结果。
