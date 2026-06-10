"""Enrich pending-scope checklist payload with B1/B2 previews."""

from __future__ import annotations

from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.conflict_detection_service import detect_material_conflicts
from app.services.issue_identification_service import run_issue_identification
from app.services.material_scope_review_service import run_material_scope_review


def enrich_pending_scope_payload(
    scenario: InvestigationScenario,
    payload: dict[str, Any],
    *,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    payload = dict(payload)
    payload["material_scope_findings"] = run_material_scope_review(scenario, payload)
    issue_result = run_issue_identification(scenario, payload, user_id=user_id)
    payload["issue_suggestions"] = issue_result.get("suggestions") or []
    payload["issue_identification"] = issue_result
    payload["conflict_flags"] = detect_material_conflicts(scenario, payload)
    doc = dict(payload.get("document_extract") or {})
    unverified = [
        {
            "field": f.get("field"),
            "snippet": f.get("source_snippet"),
            "score": f.get("grounding_score"),
            "status": f.get("verification_status", "unverified"),
        }
        for f in doc.get("facts") or []
        if f.get("verification_status") in ("unverified", "weak_grounding", None)
        and f.get("source_snippet")
    ]
    payload["unverified_facts"] = unverified
    agent_steps = list(payload.get("agent_steps") or [])
    agent_steps.append(issue_result.get("agent_step") or {"step": "issue_identification", "status": "skipped"})
    payload["agent_steps"] = agent_steps
    return payload
