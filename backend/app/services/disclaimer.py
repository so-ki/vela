"""Platform disclaimer — aligned with design doc compliance requirements."""

DISCLAIMER_TITLE = "免责声明与数据使用条款"
DISCLAIMER_VERSION = "1.0"

DISCLAIMER_SECTIONS = [
    {
        "title": "产品定位",
        "content": (
            "Vela 出海法务平台提供的是法律信息检索摘要与结构化风险线索，附法条溯源与匹配度评分，"
            "不构成正式法律意见。重大投资决策须由持证律师复核或出具正式法律意见。"
        ),
    },
    {
        "title": "AI 输出限制",
        "content": (
            "系统采用 RAG 检索增强生成架构，禁止在无检索片段支撑的情况下生成法律结论。"
            "匹配度低于阈值的条目将强制标注「需法务复核」，不得自动定稿。"
        ),
    },
    {
        "title": "数据使用与隐私",
        "content": (
            "您提交的业务场景描述将仅用于本次协查任务处理，默认不用于对外模型训练。"
            "请避免上传不必要的个人身份信息或商业机密；平台遵循最小必要采集原则，支持敏感字段脱敏输入。"
        ),
    },
    {
        "title": "责任边界",
        "content": (
            "企业法务人员对最终对外使用的报告内容承担专业判断与复核责任。"
            "因依赖未经人工复核的 AI 输出而导致的损失，平台不承担法律责任。"
        ),
    },
]

DISCLAIMER_FULL_TEXT = "\n\n".join(
    f"【{s['title']}】\n{s['content']}" for s in DISCLAIMER_SECTIONS
)
