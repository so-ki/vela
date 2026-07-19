# Vela RC0 UI Research Ledger

研究日期：2026-07-19  
范围：仅研究成熟的公共信息架构、可访问性交互和高风险状态表达；不复制品牌、版式或组件源码。Vela 的视觉语言、信息层级、文案与实现均为原创。

| 来源 | 可借鉴模式 | 解决的问题 | Vela 采用方式 | 原创化处理 | 明确拒绝 |
|---|---|---|---|---|---|
| [W3C WAI-ARIA APG — Tabs](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) | 键盘焦点与选中状态必须可辨，并与视觉样式分离 | 法律研究三栏内容切换仍需可被键盘和辅助技术理解 | 参考其状态分离原则；最终采用原生 `button` + `aria-pressed` 的调查事项选择列表，不冒充 `tablist` | 使用 Vela 自有“证据工作台”标签、中文状态、原生焦点顺序与审计焦点环 | 拒绝以无语义容器模拟按钮；拒绝把线性流程塞进 tabs |
| [USWDS — Step indicator](https://designsystem.digital.gov/components/step-indicator/) | 当前、已完成、待处理步骤必须同时依靠文字和差异化处理 | 展示 Compiler → Release 的长交付链，避免只看颜色 | RC0 使用紧凑证据管线，当前/阻断/待开始均有文字、图标和状态说明 | 将政府表单步骤改造为 Vela 的不可逆证据 checkpoint，并显示版本/hash 身份 | 拒绝用百分比暗示法律正确性；拒绝将未完成显示为禁用态而无解释 |
| [USWDS — Alert](https://designsystem.digital.gov/components/alert/) | 重要且时效性强的状态应有结构化标题和正文 | 让 blocked、stale、unknown-version 与 synthetic 警示不被卡片噪声淹没 | 页面级只保留一个最高优先级 alert；字段级错误留在本地 | Vela alert 结合 reason code、影响面、下一责任方和证据来源 | 拒绝同页堆叠多条横幅；拒绝以成功色表达仅“工程通过” |
| [GOV.UK — Warning text](https://design-system.service.gov.uk/components/warning-text/) | 法律后果或重大限制必须直接、稀疏、持续可见 | synthetic demo 可能被误认成真实客户或法律证据 | 全局与交付页持续显示“拟制演示 / SYNTHETIC DEMO”及正式发布禁止说明 | 采用紫色纹理边框、双语标签、机器字段四元组，不复用 GOV.UK 视觉 | 拒绝把警示藏进 tooltip/modal；拒绝仅用灰色免责声明 |
| [GOV.UK — Tag](https://design-system.service.gov.uk/components/tag/) | tag 只表达状态，不伪装成可点击动作 | 高密度表格中的 pass/review/blocked/not started/synthetic 状态一致 | 状态 pill 均为不可交互文本，动作单独使用按钮/链接 | Vela 固定绿/琥珀/红/蓝/灰/紫语义并配文字/图形，不只靠颜色 | 拒绝动词型 tag；拒绝把筛选器画成状态 tag |
| [GOV.UK — Table](https://design-system.service.gov.uk/components/table/) | 表格用于可比较、可扫描的信息 | Claim、CoverageProof、审计记录需要稳定列语义 | 使用原生 table、caption、列标题、移动端分组；长 hash 等宽显示 | 设计 Vela 高密度证据表，加入来源、版本、完整性与阻断原因列 | 拒绝用卡片墙替代大量可比记录；拒绝截断 hash 而无完整值入口 |
| [Carbon — Tabs usage](https://carbondesignsystem.com/components/tabs/usage/) | 内容选择与线性 progress indicator 不应混用 | 防止“研究选择”和“交付过程”信息架构混淆 | 法律研究使用原生选择列表；交付中心使用线性 evidence pipeline | 仅采纳用途区分，组件布局、尺度、色彩和动效全部自研 | 拒绝直接引入 Carbon 依赖或模仿 IBM 产品外观 |

## 形成的 Vela 原则

1. 法律与工程状态分层：工程测试通过不能把外部法律/客户/生产状态变绿。
2. 版本身份一等显示：pack、rules、corpus、compiler、proof、snapshot、release 均在上下文中可见。
3. 阻断可操作：每个 blocked/stale/unknown 状态同时给出稳定 reason code、影响和下一责任方。
4. 拟制演示不可误认：紫色纹理、双语警示与四个机器字段在全局、对象详情和导出三处重复出现。
5. 高密度但可扫描：数据用表格对齐，解释用窄摘要，流程用 checkpoint，不用装饰性仪表盘。
6. 可访问性不是事后修补：原生语义、清晰焦点、非颜色单一编码、200% 缩放和窄屏均进入验收。
