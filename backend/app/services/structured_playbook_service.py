"""Shared structured playbook evaluation (contract + material scope)."""

from __future__ import annotations

import re
from typing import Any, Optional

from app.services.contract_house_rules_service import phrase_hits, rule_detected
from app.services.grounding_utils import verify_snippet_in_source


def evaluate_text_rule(
    text: str,
    rule: dict[str, Any],
    *,
    full_text: str | None = None,
) -> Optional[dict[str, Any]]:
    """Evaluate must_have / must_not on a text span; optional grounding to full_text."""
    if not rule_detected(text, rule):
        return None

    must_not_hits = phrase_hits(text, rule.get("must_not") or [])
    must_have_hits = phrase_hits(text, rule.get("must_have") or [])
    exception_hits = phrase_hits(text, rule.get("exceptions") or [])

    issues: list[dict[str, Any]] = []
    risk = "YELLOW"
    risk_label = "命中材料 Playbook · 须法务确认"
    tier = "S2"

    if must_not_hits and not exception_hits:
        risk = "RED"
        risk_label = "违反 must_not 底线"
        tier = "S3"
        issues.append({"type": "must_not_violation", "phrases": must_not_hits})
        anchor = must_not_hits[0]
    elif must_not_hits and exception_hits:
        risk = "YELLOW"
        risk_label = "命中禁止表述但有例外线索 · 须确认"
        issues.append({"type": "exception_may_apply", "phrases": exception_hits})
        anchor = must_not_hits[0]
    elif rule.get("must_have") and not must_have_hits:
        risk = "YELLOW"
        risk_label = "缺少 must_have 必备要件"
        issues.append({"type": "must_have_missing", "expected": rule.get("must_have") or []})
        anchor = text[:120]
    else:
        issues.append({"type": "keyword_hit_only", "note": "仅关键词命中，需结合上下文"})
        anchor = text[:120]

    grounding_source = full_text if full_text is not None else text
    grounding = verify_snippet_in_source(anchor, grounding_source)
    if risk == "RED" and not grounding.get("grounded"):
        risk = "YELLOW"
        risk_label = "疑似红线但未 grounding · 降级为须确认"
        tier = "S2"
        issues.append({"type": "red_downgrade_no_grounding"})

    return {
        "rule_id": rule["id"],
        "label": rule["label"],
        "severity": rule.get("severity", "medium"),
        "risk": risk,
        "risk_label": risk_label,
        "tier": tier,
        "issues": issues,
        "must_have_satisfied": bool(must_have_hits) if rule.get("must_have") else None,
        "must_not_hits": must_not_hits,
        "guidance": rule.get("guidance", ""),
        "grounded": bool(grounding.get("grounded")),
        "grounding_score": grounding.get("grounding_score"),
        "grounding_span": anchor[:200],
        "feeds_checklist": list(rule.get("feeds_checklist") or []),
        "dimension": rule.get("dimension"),
    }
