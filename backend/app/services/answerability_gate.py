"""拒答门（Answerability Gate）：叠加在既有 70 分门控之上的场景级可答性判定。

不知道时敢不敢说不知道——这道门回答这个问题。
四类拒答原因必须区分，不允许混成笼统失败：
  pack_not_installed / insufficient_material / no_grounded_evidence / llm_unavailable

注意阈值语义：tier 是 0-100 分制，grounding 是 0-1 比率，不得混算。
本模块是纯函数层，不写库；决策的持久化由调用方负责。

法域中立：本模块不得出现任何具体法域/语言内容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.statuses import AnswerabilityReason

GROUNDING_RATE_FLOOR = 0.3  # 全场景 grounding 比率低于此值时整体拒答（0-1 比率制）


@dataclass
class AnswerabilityDecision:
    answerable: bool
    reason_code: Optional[str] = None
    message: Optional[str] = None
    degraded_mode: bool = False
    signals: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "answerable": self.answerable,
            "reason_code": self.reason_code,
            "message": self.message,
            "degraded_mode": self.degraded_mode,
            "signals": self.signals,
        }


def assess_answerability(
    *,
    pack_resolved: bool,
    grounding_report: Optional[dict[str, Any]] = None,
    tier_report: Optional[dict[str, Any]] = None,
    adequacy: Optional[dict[str, Any]] = None,
    llm_required: bool = False,
    llm_available: bool = True,
) -> AnswerabilityDecision:
    """场景级可答性判定。

    叠加而非替换：条目级 S1/S2/S3 门控保持不变，本判定只回答
    "整份底稿可不可以作为协查产出交付"。
    """
    grounding_report = grounding_report or {}
    tier_report = tier_report or {}
    adequacy = adequacy or {}

    signals = {
        "grounding_rate": grounding_report.get("grounding_rate"),
        "hard_blocked_codes": tier_report.get("hard_blocked_codes") or tier_report.get("blocked_codes"),
        "is_investigation_ready": adequacy.get("is_investigation_ready"),
    }

    if not pack_resolved:
        return AnswerabilityDecision(
            answerable=False,
            reason_code=AnswerabilityReason.PACK_NOT_INSTALLED.value,
            message="目标法域尚无已安装的能力包，平台明确拒答而非猜测。",
            signals=signals,
        )

    if llm_required and not llm_available:
        return AnswerabilityDecision(
            answerable=False,
            reason_code=AnswerabilityReason.LLM_UNAVAILABLE.value,
            message="所需模型服务不可用；这不等于材料不足，恢复后可重试。",
            signals=signals,
        )

    if adequacy and adequacy.get("is_investigation_ready") is False:
        return AnswerabilityDecision(
            answerable=False,
            reason_code=AnswerabilityReason.INSUFFICIENT_MATERIAL.value,
            message="必备材料要件缺口未闭环，请先补充材料再生成可交付底稿。",
            degraded_mode=True,
            signals=signals,
        )

    rate = grounding_report.get("grounding_rate")
    total_hits = grounding_report.get("total_hits")
    if total_hits == 0 or (rate is not None and float(rate) < GROUNDING_RATE_FLOOR):
        return AnswerabilityDecision(
            answerable=False,
            reason_code=AnswerabilityReason.NO_GROUNDED_EVIDENCE.value,
            message="检索结果无法在语料中锚定到足够证据，结论不可交付。",
            degraded_mode=True,
            signals=signals,
        )

    return AnswerabilityDecision(answerable=True, signals=signals)
