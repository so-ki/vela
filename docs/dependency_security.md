# Python 运行依赖安全基线

## 发布矩阵

- Python：3.12（独立验证环境为 CPython 3.12.13）
- 直接依赖源：`backend/requirements.txt`
- 生产安装入口：`backend/requirements.lock`（包含跨平台 marker 的完整锁定图）
- 兼容入口：`backend/requirements-rag.txt`（当前仅引用生产锁定图，不额外安装向量库）
- 漏洞扫描器：PyPA `pip-audit` 2.10.1
- 最后审计日期：2026-07-17

## 生产容器基线

- 生产后端基础镜像：Docker Official Image `python:3.12.13-alpine3.24@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df`（多架构 manifest）。
- 生产数据库基础镜像：Docker Official Image `postgres:16.14-alpine3.24@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`；包装层用 Alpine 官方 `su-exec=0.3-r0` 替换上游 `gosu 1.19` Go 二进制，同时保留官方 entrypoint 的降权调用约定。
- 生产安装使用 `--only-binary=:all:`；完整锁文件已对 CPython 3.12 的 musllinux 1.1/1.2 x86_64 轮子做下载预检，不允许在运行镜像内临时编译依赖。
- 生产镜像不安装 `curl`、编译器或包管理器扩展；Compose 健康检查改用 Python 标准库。
- GitHub Actions 继续以 Trivy 0.70.0 对 High/Critical 漏洞执行 `ignore-unfixed: false` 的阻断策略，不接受通过全局忽略未修复漏洞来制造绿色结果。

此前浮动的 `python:3.12-slim` 在 2026-07-17 的 `--pull` 构建中解析为 Debian 13.6，Trivy 命中 36 个无可用修复版本的系统级 High/Critical CVE（33/3），主要来自 Perl、curl、util-linux、ncurses 与 gzip。由于相应 Debian 版本没有修复包，`apt upgrade` 不能消除风险；因此改为更小且仍受支持的 Alpine 3.24 基线，并移除应用不需要的 curl。最终结论仍以远端生产镜像、SBOM、PostgreSQL 迁移和完整 Compose 冒烟门同时通过为准。

同轮复验中，后端与前端镜像扫描已经通过；官方 PostgreSQL 镜像的 Alpine 系统包也是 0 命中，但 `/usr/local/bin/gosu` 使用 Go 1.24.6 构建，命中 15 个均已有修复版本的 High/Critical Go 标准库 CVE（14/1）。官方容器镜像规范明确允许以 `gosu` 或 `su-exec` 在 entrypoint 中降权；因此包装层删除该 Go 二进制，以 Alpine main 仓库的极小 C 实现 `su-exec` 在相同路径提供 `user[:group] command ...` 调用。数据库最终镜像仍必须重新通过严格扫描、SBOM 与实际初始化/迁移/冒烟，不能仅凭等价接口放行。

摘要固定用于保证本 RC 的基础层可复现，不代表永久停留在该摘要。维护期应至少每周检查 Docker Official Image 的新摘要，以独立 PR 更新，并重新执行完整 Trivy、SBOM、PostgreSQL 迁移和 Compose 冒烟门。

| 直接依赖 | 已审计版本 | 说明 |
|---|---:|---|
| FastAPI | 0.139.0 | 与 Starlette 1.3.1 同组验证 |
| Starlette | 1.3.1 | 显式锁定 Web 框架边界 |
| Uvicorn | 0.51.0 | `standard` extra；Gunicorn worker 配置已检查 |
| PyJWT | 2.13.0 | 取代 `python-jose[cryptography]` |
| python-multipart | 0.0.32 | 上传表单解析 |
| pypdf | 6.14.2 | PDF 文本提取回归通过 |

`requirements.lock` 当前包含 45 条精确版本记录（部分带平台 marker）。在全新 Python 3.12 虚拟环境安装后，隔离的 `pip-audit --path ...` 结果为：

```text
No known vulnerabilities found
```

这是时点性结论，不代表未来不会新增公告。每次发布都必须在新建环境中重新安装并扫描，不得直接扫描开发者长期复用的 `.venv`。

## Chroma 暂停决策

对当时最新 Chroma 1.5.9 的独立安装图扫描命中 `PYSEC-2026-311` / `CVE-2026-45829`：1.0.0 起的受影响版本存在预认证代码注入，当时无修复版本。参见 [OSV 审核记录](https://osv.dev/vulnerability/GHSA-f4j7-r4q5-qw2c)。

本版本因此：

- 不在生产 Docker 镜像中安装 Chroma；
- 不在 `requirements*.txt` 中声明 Chroma；
- 使用已有的确定性关键词检索；
- 仅在上游存在已公布修复、独立服务完成认证与网络隔离、并重新通过回归和依赖审计后恢复向量检索。

## 重复审计

`pip-audit` 必须安装在另一个工具环境，避免将审计器自身的依赖计入应用运行图。

```bash
python3.12 -m venv /tmp/vela-runtime
/tmp/vela-runtime/bin/pip install -r backend/requirements.lock

python3.12 -m venv /tmp/vela-audit
/tmp/vela-audit/bin/pip install pip-audit==2.10.1
/tmp/vela-audit/bin/pip-audit \
  --path /tmp/vela-runtime/lib/python3.12/site-packages \
  --progress-spinner off
```
