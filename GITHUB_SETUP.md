# GitHub 上传与邀请测试者

本地仓库已初始化并完成首次提交（**不含** `backend/.env` 与 API Key）。

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
cd /Users/kys/test/vela-platform

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
cp .env.example .env
# 可选：填入自己的 QWEN_API_KEY 以测试 LLM 润色
```

演示账号由种子脚本创建：`legal@demo.vela` / `Demo1234!`

## 五、安全清单

- [x] `.env` 已在 `.gitignore`，未提交
- [ ] 确认 GitHub 仓库为 **Private**
- [ ] 若曾泄露 Key，在 DashScope 控制台轮换 `QWEN_API_KEY`
- [ ] 仅邀请可信 Collaborator

## 六、可选：发布 Release 供下载 zip

若对方不使用 Git，可在 GitHub 打 Release 附 zip：

1. 仓库 → **Releases** → **Create a new release**
2. Tag：`v0.1.0-mvp`
3. 上传 `Vela_MVP_给Gemini.zip` 或让 GitHub 自动生成 Source code

---

**当前本地状态：** 已 commit，等待 `git push` 到你在 GitHub 新建的 remote。
