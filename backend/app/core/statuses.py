"""平台机制层状态枚举：材料账本六态、覆盖任务状态、Claim 判定、拒答原因。

法域中立：本模块不得出现任何具体法域/语言的内容（见 docs/design/CODE_REVIEW_CHECKLIST.md）。
"""

from __future__ import annotations

from enum import Enum


class MaterialBlockState(str, Enum):
    """材料账本六态：材料处理完没有，账本必须能回答。"""

    RAW_ARCHIVED = "raw_archived"    # 已归档，未抽取
    EXTRACTED = "extracted"          # 已抽取，事实未验证
    VERIFIED = "verified"            # 抽取事实全部通过 grounding 验证
    UNVERIFIED = "unverified"        # 抽取完成但存在未验证事实
    IN_USE = "in_use"                # 已被协查包/简报消费
    RETURNED = "returned"            # 法务打回待补充
    SUPERSEDED = "superseded"        # 已被新版本材料取代


MATERIAL_TRANSITIONS: dict[MaterialBlockState, set[MaterialBlockState]] = {
    MaterialBlockState.RAW_ARCHIVED: {
        MaterialBlockState.EXTRACTED,
        MaterialBlockState.VERIFIED,
        MaterialBlockState.UNVERIFIED,
        MaterialBlockState.RETURNED,
        MaterialBlockState.SUPERSEDED,
    },
    MaterialBlockState.EXTRACTED: {
        MaterialBlockState.VERIFIED,
        MaterialBlockState.UNVERIFIED,
        MaterialBlockState.IN_USE,
        MaterialBlockState.RETURNED,
        MaterialBlockState.SUPERSEDED,
    },
    MaterialBlockState.VERIFIED: {
        MaterialBlockState.IN_USE,
        MaterialBlockState.RETURNED,
        MaterialBlockState.SUPERSEDED,
    },
    MaterialBlockState.UNVERIFIED: {
        MaterialBlockState.VERIFIED,
        MaterialBlockState.IN_USE,
        MaterialBlockState.RETURNED,
        MaterialBlockState.SUPERSEDED,
    },
    MaterialBlockState.IN_USE: {
        MaterialBlockState.RETURNED,
        MaterialBlockState.SUPERSEDED,
    },
    MaterialBlockState.RETURNED: {
        MaterialBlockState.SUPERSEDED,
        MaterialBlockState.EXTRACTED,
    },
    MaterialBlockState.SUPERSEDED: set(),
}


class CoverageTaskStatus(str, Enum):
    """覆盖任务状态。ENUMERATED_ABSENT（目录穷举后未见）仅允许用于
    manifest coverage_denominators 声明了官方分母的来源。"""

    OPEN = "open"
    SATISFIED = "satisfied"
    ENUMERATED_ABSENT = "enumerated_absent"
    WAIVED = "waived"
    UNANSWERABLE = "unanswerable"


class ClaimVerdict(str, Enum):
    """简报结论的编译判定：有证据、被门控阻断、或明确不可答。"""

    SUPPORTED = "supported"          # 证据链完整（法源命中 + grounding 通过）
    NEEDS_REVIEW = "needs_review"    # 证据存在但低于阈值，须人工复核
    BLOCKED = "blocked"              # 门控硬阻断，不得作为已核实结论
    UNANSWERABLE = "unanswerable"    # 无证据可支撑，明确拒答


class AnswerabilityReason(str, Enum):
    """拒答原因。区分「没有包」「材料不足」「无证据」「工具不可用」四类，
    不允许把它们混成一个笼统的失败。"""

    PACK_NOT_INSTALLED = "pack_not_installed"
    INSUFFICIENT_MATERIAL = "insufficient_material"
    NO_GROUNDED_EVIDENCE = "no_grounded_evidence"
    LLM_UNAVAILABLE = "llm_unavailable"
