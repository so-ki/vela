# Versioned Readers：升级、恢复与回滚手册

适用范围：Claim Compiler 0.2、CoverageProof 0.1、Delivery Snapshot / Answerability Gate 1.0、Delivery Release 1.1，以及以后只增不减的 reader。

## 不变量

1. reader 由静态 registry 按持久化版本字符串精确选择；禁止 current/latest/最大版本回退。
2. `CURRENT_*_WRITE_VERSION` 只决定新对象的 writer；不得用于解释历史对象。
3. frozen reader、Capability Pack archive 与 golden 文件只增不改。算法或形状变化必须新增版本和 golden。
4. readiness、重验与恢复均只读；不得为“修好”未知版本而批量改写数据库。
5. 正式 release 的 unknown schema 固定产生 `delivery_release_schema_unsupported`，下载继续由正式 Gate 以 409 阻断。

## 升级步骤

1. 在独立提交中新增 reader 模块和 golden，保留全部历史条目。
2. 把新 reader 显式加入 registry，再把允许的完整组合加入 compatibility matrix。
3. 先验证旧对象仍经旧 reader 得到相同 hash；再切换 `CURRENT_*_WRITE_VERSION`。
4. 若新增持久化版本列，迁移先加 nullable + 临时 server default，回填、核验非空、改为 NOT NULL，最后删除 server default；writer 显式写 `reader.version`。
5. 执行 fresh upgrade、上一 head → 新 head、可丢弃库 downgrade/upgrade 往返、SQLite 与 PostgreSQL 验证。
6. 检查 `/api/v1/readiness`：required readers、current writers、compatibility matrix 与 persisted versions 均为 passed。
7. 运行 frozen golden raw SHA、专项、全量、release boundary 与 Docker context probe，再发布镜像。

## 从备份恢复

1. 先恢复应用提交、数据库、Capability Pack archive 和 exact artifact bytes，禁止只恢复数据库后用当前代码猜读。
2. 在不启动 worker 的维护窗口执行 Alembic 到备份记录的 migration head。
3. 运行只读 readiness；若出现未知版本，恢复包含该历史 reader 的应用提交或部署一个只增补 reader 的兼容版本。
4. 对抽样 release 执行 evaluator/revalidation；确认 snapshot/release hash 与冻结记录相同。
5. readiness 通过前不得恢复正式下载流量。开发环境的 warning 不能当作生产放行。

## 回滚 writer / 应用

- writer 默认可回退到仍已注册的旧版本，但已写入新版本的对象只能由包含该新 reader 的应用解释。
- 因此应用回滚目标必须仍包含数据库中所有已出现版本；若不包含，production readiness 必须失败，禁止强行启动为 ready。
- 不得删除新 reader、重标历史 `schema_version`、重算历史 hash 或自动重建 release。
- Alembic `0007` downgrade 仅允许可丢弃数据库，且只有全部 release 仍为 `1.1` 时才会删除列；发现其他版本会拒绝 downgrade。

## Alembic 0007 验收

- 现存 `scenario_delivery_releases` 全部回填 `schema_version='1.1'`。
- 列为 `VARCHAR(16) NOT NULL`，无永久 server default。
- 新 writer 显式写 delivery release reader 的 `version`。
- disposable SQLite：`0006 → 0007 → 0006 → 0007` 通过。
- PostgreSQL：fresh upgrade 与 `0006 → 0007` 必须在真实实例验证；若执行环境没有可信 PostgreSQL，则保持未验证，不得以 SQLite 外推。

## 事故停止条件

- registry 缺历史 reader、current writer 未注册或 compatibility matrix 不闭合；
- readiness 报告任何 unknown/missing version；
- 旧对象经存储 reader 重验后 hash 漂移；
- frozen archive 或 golden raw SHA 改变；
- downgrade 发现非 1.1 release；
- Docker/release package 缺少任一 reader 模块。
