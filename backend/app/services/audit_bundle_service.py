"""Audit bundle for export (Lavern audit trail + retrieval provenance)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.scenario import InvestigationScenario
from app.services.legal_ingest import corpus_review_status
from app.services.legal_rag import SOURCE_LABELS


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_audit_bundle(
    scenario: InvestigationScenario,
    *,
    payload_override: dict[str, Any] | None = None,
    generation_config: Any = None,
    scenario_status_override: str | None = None,
) -> dict[str, Any]:
    if scenario.is_demo:
        raise ValueError("演示项目不得生成正式 audit bundle")
    if generation_config is None:
        raise ValueError("正式 audit bundle 缺少冻结 Capability Pack 上下文")
    payload = payload_override or (scenario.checklist.payload if scenario.checklist else {})
    review = payload.get("review") or {}
    brief = payload.get("brief") or {}
    items_review = review.get("items") or []
    corpus = generation_config.corpus_data
    corpus_by_id = {
        str(source.get("id")): source
        for source in corpus.get("sources", [])
        if source.get("id")
    }

    hits_summary: list[dict[str, Any]] = []
    for section in payload.get("sections_with_legal") or payload.get("sections") or []:
        for item in section.get("items", []):
            for hit in (item.get("legal_hits") or [])[:3]:
                source_doc = corpus_by_id.get(str(hit.get("id") or ""), {})
                source_key = hit.get("source") or source_doc.get("source")
                review_status = hit.get("review_status") or (
                    corpus_review_status(corpus, source_doc) if source_doc else None
                )
                requires_review = hit.get("requires_review")
                if requires_review is None:
                    requires_review = review_status != "expert_verified"
                verification_scope = (
                    hit.get("verification_scope")
                    or source_doc.get("verification_scope")
                    or (
                        "expert-reviewed source metadata"
                        if review_status == "expert_verified"
                        else "provisional corpus entry"
                    )
                )
                hits_summary.append(
                    {
                        "checklist_code": item.get("code"),
                        "hit_id": hit.get("id"),
                        "source_key": source_key,
                        "source": hit.get("source_label")
                        or SOURCE_LABELS.get(str(source_key), str(source_key or "")),
                        "urn": hit.get("urn") or source_doc.get("urn"),
                        "url": hit.get("url") or source_doc.get("url"),
                        "official_url": hit.get("official_url")
                        or source_doc.get("official_url")
                        or hit.get("url")
                        or source_doc.get("url"),
                        "title_pt": hit.get("title_pt") or source_doc.get("title_pt"),
                        "title_zh": hit.get("title_zh") or source_doc.get("title_zh"),
                        "match_score": hit.get("match_score"),
                        "requires_review": bool(requires_review),
                        "review_status": review_status,
                        "verification_scope": verification_scope,
                        "authority": hit.get("authority") or source_doc.get("authority"),
                        "instrument_type": hit.get("instrument_type")
                        or source_doc.get("instrument_type"),
                        "pinpoint": hit.get("pinpoint") or source_doc.get("pinpoint"),
                        "status_as_of": hit.get("status_as_of")
                        or source_doc.get("status_as_of"),
                        "last_verified_at": hit.get("last_verified_at")
                        or source_doc.get("last_verified_at"),
                        "validity": hit.get("validity") or source_doc.get("validity"),
                    }
                )

    return {
        "bundle_version": "1.2",
        "generated_at": _utcnow_iso(),
        "scenario": {
            "id": scenario.id,
            "project_name": scenario.project_name,
            "status": scenario_status_override or scenario.status,
            "compliance_dimensions": scenario.compliance_dimensions,
            "scenario_scope": scenario.scenario_scope,
        },
        "investigation_settings": payload.get("investigation_settings"),
        "capability_pack": {
            "pack_id": generation_config.capability_pack_id,
            "version": generation_config.capability_pack_version,
            "pack_hash": generation_config.capability_pack_hash,
            "rules_artifact_id": generation_config.rules_artifact_id,
            "rules_artifact_version": generation_config.rules_artifact_version,
            "rules_artifact_hash": generation_config.rules_artifact_hash,
            "corpus_artifact_id": generation_config.corpus_artifact_id,
            "corpus_artifact_version": generation_config.corpus_artifact_version,
            "corpus_artifact_hash": generation_config.corpus_artifact_hash,
        },
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
            "reviewer_id": review.get("reviewer_id"),
            "reviewer_name": review.get("reviewer_name"),
            "finalized_by_id": review.get("finalized_by_id"),
            "finalized_by_name": review.get("finalized_by_name"),
            "revision": review.get("revision", 0),
        },
        "legal_hits": hits_summary,
        "review_items": [
            {
                "code": i.get("code"),
                "decision": i.get("decision"),
                "gate_status": i.get("gate_status"),
                "match_score": i.get("match_score"),
                "comment": i.get("comment"),
                "override": bool(i.get("manual_override")),
                "manual_override": bool(i.get("manual_override")),
                "reviewer_id": i.get("reviewer_id"),
                "reviewer_name": i.get("reviewer_name"),
                "reviewed_at": i.get("reviewed_at"),
                "review_revision": i.get("review_revision"),
                "external_counsel_required": i.get("external_counsel_required"),
            }
            for i in items_review
        ],
        "finalize_history": payload.get("finalize_history") or [],
        "review_change_history": review.get("change_history") or [],
        "incremental_regen": payload.get("incremental_regen"),
        "disclaimer": "本 bundle 为协查过程审计快照，不构成法律意见。",
    }
