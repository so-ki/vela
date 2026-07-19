# 决赛宣称允许清单

以下口径仅在对应证据仍可重验时使用。

| 允许宣称 | 必须同时披露 | 证据边界 |
|---|---|---|
| 平台通过正式上传、事实确认、Scope 冻结、编译、证明和 Gate 服务处理比赛测试案件 | 测试企业材料是合成输入 | 正式服务不等于真实客户案件 |
| Claim Compiler 0.3 从冻结 Pack 恢复固定 30 项分母 | Scope 只标记 in/out；screening 不缩小分母 | 30 项不是 30 张法律规则卡 |
| 没有真实法务草稿时只建立或更新 ResearchItem | ClaimRecord 只来自法务提交的非空草稿 | 系统不补写法律结论 |
| CoverageProof 0.2 披露五类 in-scope disposition | out-of-scope 项没有 disposition | 证明覆盖过程，不证明法律内容充分 |
| 关键事实及法务引用选择变化会改变真实编译 hash | hash 只证明确定性绑定和变化可见 | hash 不证明结论正确 |
| 正式 Release Gate 在缺少外部证据时保持 `blocked_external` | 明示缺少哪些律师、客户或生产证据 | 不得把工程测试当作外部批准 |
| compiler 0.2、proof 0.1 仍可读取且冻结 Golden hash 不漂移 | 新 writer 是 0.3/0.2 | 历史可读不等于可用旧 writer 生成新制品 |

超出表内范围的表述默认为未批准，须先进入证据账本和决策日志。
