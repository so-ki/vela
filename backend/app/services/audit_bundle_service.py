"""Audit bundle for export (Lavern audit trail + retrieval provenance)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.scenario import InvestigationScenario
from app.services.legal_ingest import load_corpus


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_audit_bundle(
    scenario: InvestigationScenario,
    *,
    payload_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload_override or (scenario.checklist.payload if scenario.checklist else {})
    review = payload.get("review") or {}
    brief = payload.get("brief") or {}
    items_review = review.get("items") or []

    hits_summary: list[dict[str, Any]] = []
    for section in payload.get("sections_with_legal") or payload.get("sections") or []:
        for item in section.get("items", []):
            for hit in (item.get("legal_hits") or [])[:3]:
                hits_summary.append(
                    {
                        "checklist_code": item.get("code"),
                        "hit_id": hit.get("id"),
                        "source": hit.get("source_label"),
                        "urn": hit.get("urn"),
                        "url": hit.get("url"),
                        "match_score": hit.get("match_score"),
                        "requires_review": hit.get("requires_review"),
                        "validity": hit.get("validity"),
                    }
                )

    corpus = load_corpus()
    return {
        "bundle_version": "1.0",
        "generated_at": _utcnow_iso(),
        "scenario": {
            "id": scenario.id,
            "project_name": scenario.project_name,
            "status": scenario.status,
            "compliance_dimensions": scenario.compliance_dimensions,
        },
        "investigation_settings": payload.get("investigation_settings"),
        "retrieval_meta": payload.get("retrieval_meta"),
        "corpus_version": corpus.get("version"),
        "grounding_report": payload.get("grounding_report"),
        "verification_report": payload.get("verification_report"),
        "conflict_flags": payload.get("conflict_flags") or [],
        "investigation_adequacy_summary": {
            "is_investigation_ready": (payload.get("investigation_adequacy") or {}).get(
                "is_investigation_ready"
            ),
            "blocked_count": (payload.get("investigation_adequacy") or {})
            .get("brief_summary", {})
            .get("blocked_count"),
        },
        "brief_summary": {
            "status": brief.get("status"),
            "threshold": brief.get("threshold"),
            "passed_count": brief.get("passed_count"),
            "blocked_count": brief.get("blocked_count"),
        },
        "review_summary": {
            "status": review.get("status"),
            "version_label": review.get("version_label"),
            "finalized_at": review.get("finalized_at"),
            "approved_count": review.get("approved_count"),
            "rejected_count": review.get("rejected_count"),
        },
        "legal_hits": hits_summary,
        "review_items": [
            {
                "code": i.get("code"),
                "decision": i.get("decision"),
                "gate_status": i.get("gate_status"),
                "match_score": i.get("match_score"),
                "comment": i.get("comment"),
                "external_counsel_required": i.get("external_counsel_required"),
            }
            for i in items_review
        ],
        "finalize_history": payload.get("finalize_history") or [],
        "incremental_regen": payload.get("incremental_regen"),
        "disclaimer": "本 bundle 为协查过程审计快照，不构成法律意见。",
    }
