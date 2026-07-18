"""Claim 编译器：把简报里的每条结论编译为带证据链的 Claim。

原则：无证据的结论只能是 blocked 或 unanswerable，不允许
"看起来有道理"的结论绕过证据链进入定稿。

法域中立：本模块不得出现任何具体法域/语言内容；
简报条目里的双语文本按数据透传，不在此处生成。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.statuses import ClaimVerdict
from app.models.claim import Claim, ClaimEvidence
from app.services.fact_service import active_facts

_GROUNDED_STATUSES = {"corpus_verified"}
_WEAK_STATUSES = {"weak_grounding"}


def _verdict_for_item(item: dict[str, Any]) -> tuple[ClaimVerdict, str | None]:
    gate_status = str(item.get("gate_status") or "")
    citations = item.get("citations") or []
    if gate_status == "blocked":
        return ClaimVerdict.BLOCKED, item.get("block_reason") or "gate blocked"
    if not citations:
        return ClaimVerdict.UNANSWERABLE, "no citation evidence"
    statuses = {str(c.get("citation_status") or "ungrounded") for c in citations}
    if statuses & _GROUNDED_STATUSES and not item.get("requires_review"):
        return ClaimVerdict.SUPPORTED, None
    if statuses & (_GROUNDED_STATUSES | _WEAK_STATUSES):
        return ClaimVerdict.NEEDS_REVIEW, "evidence below auto-pass threshold"
    return ClaimVerdict.UNANSWERABLE, "citations present but none grounded"


def compile_claims(db: Session, scenario_id: int, brief: dict[str, Any]) -> list[dict[str, Any]]:
    """编译（或重编译）场景的全部 Claim；表为真源，返回只读投影。

    重编译会替换旧 Claim（Claim 是当前简报的投影；历史证明责任由
    CoverageProof 与审计包承担，见 coverage_service）。
    """
    db.query(Claim).filter(Claim.scenario_id == scenario_id).delete(synchronize_session=False)
    db.flush()

    fact_ids = [f.id for f in active_facts(db, scenario_id) if f.verification_status == "verified"]

    projections: list[dict[str, Any]] = []
    for section in brief.get("sections") or []:
        for item in section.get("items") or []:
            code = str(item.get("code") or "")
            if not code:
                continue
            verdict, reason = _verdict_for_item(item)
            claim = Claim(
                scenario_id=scenario_id,
                checklist_code=code,
                statement_primary=str(item.get("risk_zh") or item.get("title") or ""),
                statement_secondary=item.get("risk_pt") or None,
                verdict=verdict.value,
                verdict_reason=reason,
                gate_snapshot={
                    "gate_status": item.get("gate_status"),
                    "match_score": item.get("match_score"),
                    "requires_review": item.get("requires_review"),
                    "verified_fact_ids": fact_ids,
                },
            )
            db.add(claim)
            db.flush()
            evidence_count = 0
            for citation in item.get("citations") or []:
                db.add(
                    ClaimEvidence(
                        claim_id=claim.id,
                        kind="legal_hit",
                        hit_ref={
                            "citation_id": citation.get("id"),
                            "url": citation.get("url"),
                            "source_label": citation.get("source_label"),
                        },
                        grounding_score=citation.get("grounding_score"),
                        citation_status=citation.get("citation_status"),
                    )
                )
                evidence_count += 1
            projections.append(
                {
                    "claim_id": claim.id,
                    "code": code,
                    "verdict": verdict.value,
                    "verdict_reason": reason,
                    "evidence_count": evidence_count,
                    "verified_fact_count": len(fact_ids),
                }
            )
    db.flush()
    return projections


def claims_summary(projections: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for p in projections:
        counts[p["verdict"]] = counts.get(p["verdict"], 0) + 1
    return {
        "total": len(projections),
        "by_verdict": counts,
        "unsupported": counts.get(ClaimVerdict.UNANSWERABLE.value, 0)
        + counts.get(ClaimVerdict.BLOCKED.value, 0),
    }
