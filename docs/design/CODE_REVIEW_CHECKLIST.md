# Code Review 判据清单

> 配套设计说明：`docs/design/平台骨架v0.1与参考能力包v0.1.md`。每条一行，review 时逐条勾选；任何一条不满足即打回，不做口头豁免。

## 1. 归属判定（删除巴西测试）

- [ ] 对每段新代码问过："删掉全部巴西语料和规则后，这段还成立吗？"——成立的才允许进机制层（管线），不成立的放包
- [ ] "不知道该查什么"类内容（清单项、关键词、门户、红旗、文案）没有进 `backend/app/services/`，进的是包数据文件
- [ ] 归属拿不准的代码放在了包里（上提便宜、下放昂贵），没有"先放平台以后再说"
- [ ] 没有新增从包内容反推出来的机制层结构性假设（如"法源必有 URN""许可必是三段式"），有疑似的已在 PR 描述里点名

## 2. 法域中立守卫（机制层禁入字面量）

适用文件：`backend/app/core/statuses.py`、`backend/app/packs/loader.py`，及 `backend/app/services/` 下的机制层服务 answerability_gate / claim_compiler / coverage_service / material_ledger_service / fact_service（个别文件尚未建成的，建成即适用）。

- [ ] 上述文件不含 `brazil` 字面量（含变量名、注释、默认值）
- [ ] 上述文件不含 `lexml` 字面量
- [ ] 上述文件不含 `campinas` / `sao_paulo` 等地名字面量
- [ ] 上述文件不含葡语字段名（`_pt` 后缀、`text_pt` / `title_pt` / `excerpt_pt` 等）；语言相关字段名一律经 manifest locale 配置解析
- [ ] 机制层没有硬编码任何 pack_id 作为默认值或回退值；无包时走结构化拒答（`pack_not_installed`），不静默回退

## 3. payload 写回与状态纪律

- [ ] 每处 `ComplianceChecklist.payload` 写回都调用了 `flag_modified`（漏一处 = 静默丢写，演示数据凭空消失）
- [ ] 没有发明新的 `scenario.status` 值；拒答/阻断复用 `brief_blocked`，确需新增时已同步 pipeline 前缀匹配、can_return_materials、前端状态分组三处
- [ ] 服务返回的 dict 只增键不改键不删键（facts 三元组、brief_item、adequacy 的现有键形状不动）
- [ ] 后端响应新增字段已同步 `frontend/src/types/scenario.ts`（手写镜像、无 codegen，删键改键必炸 vue-tsc），并跑过前端 build

## 4. 阈值语义

- [ ] tier / 匹配度阈值是 **0–100 分制**（默认 70，权威口径见 `docs/match_tier_and_gate.md`）
- [ ] grounding 阈值是 **0–1 比率**（0.55 / 0.65 一类）
- [ ] 两种量纲没有出现在同一个比较或算式里；变量命名可区分分制（`*_score` / `*_threshold` vs `*_rate` / `*_ratio`），没有裸数字跨语义比较
- [ ] 阈值来源可追溯（config 默认 → 用户偏好 → per-code 调整 → manifest gate 块），没有在函数体里新埋魔法数字
