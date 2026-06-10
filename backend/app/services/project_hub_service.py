"""Project hub: investigation + contracts + diligence under one project."""

from __future__ import annotations

from typing import Any, Optional

from app.models.scenario import InvestigationScenario


def empty_project_hub() -> dict[str, Any]:
    return {
        "version": "1.0",
        "modules": {
            "investigation": {
                "label": "投资协查",
                "status": "pending",
                "summary": "场景核查清单、法源检索、双语简报与法务复核",
            },
            "contracts": {
                "label": "合同审查",
                "status": "idle",
                "documents": [],
                "last_analyzed_at": None,
            },
            "diligence": {
                "label": "尽职调查",
                "status": "idle",
                "documents": [],
                "issues": [],
                "last_analyzed_at": None,
            },
            "intelligence": {
                "label": "项目统摄",
                "status": "idle",
                "last_analyzed_at": None,
                "issue_count": 0,
                "high_count": 0,
            },
        },
        "cross_links": [],
    }


def ensure_project_hub(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("project_hub"):
        payload["project_hub"] = empty_project_hub()
    hub = payload["project_hub"]
    hub.setdefault("modules", {})
    for key, default in empty_project_hub()["modules"].items():
        hub["modules"].setdefault(key, default)
    return payload


def sync_investigation_module(payload: dict[str, Any], scenario: InvestigationScenario) -> None:
    ensure_project_hub(payload)
    inv = payload["project_hub"]["modules"]["investigation"]
    status_map = {
        "pending_scope": "awaiting_scope",
        "pending_legal_review": "scope_confirmed",
        "review_in_progress": "in_review",
        "review_approved": "completed",
        "review_partial": "completed",
        "review_rejected": "completed",
        "returned_for_revision": "needs_input",
    }
    inv["status"] = status_map.get(scenario.status, "in_progress")
    inv["checklist_items"] = payload.get("total_items") or sum(
        len(s.get("items") or []) for s in (payload.get("sections") or [])
    )
    inv["has_brief"] = bool(payload.get("brief"))
    inv["has_review"] = bool(payload.get("review"))


def project_context(payload: dict[str, Any], scenario: InvestigationScenario) -> dict[str, Any]:
    """Shared context for contract / diligence modules."""
    ensure_project_hub(payload)
    sections = payload.get("sections_with_legal") or payload.get("sections") or []
    blocked: list[str] = []
    tier = payload.get("tier_report") or {}
    for code in tier.get("s3_codes") or []:
        blocked.append(code)
    return {
        "project_id": scenario.id,
        "project_name": scenario.project_name,
        "country": scenario.country,
        "state": scenario.state,
        "city": scenario.city,
        "industry": scenario.industry,
        "action_type": scenario.action_type,
        "description": scenario.description,
        "known_risks": scenario.known_risks,
        "compliance_dimensions": scenario.compliance_dimensions or [],
        "investigation_summary": {
            "total_checklist_items": payload.get("total_items", 0),
            "s3_blocked_codes": blocked,
            "zero_hit_items": (payload.get("retrieval") or {}).get("zero_hit_items") or [],
            "material_gaps": (payload.get("material_review") or {}).get("missing_field_keys") or [],
        },
        "checklist_titles": [
            {"code": i.get("code"), "title": i.get("title"), "dimension": s.get("dimension_id")}
            for s in sections
            for i in (s.get("items") or [])
        ],
    }


def hub_summary(payload: dict[str, Any], scenario: InvestigationScenario) -> dict[str, Any]:
    ensure_project_hub(payload)
    sync_investigation_module(payload, scenario)
    hub = payload["project_hub"]
    contracts = hub["modules"]["contracts"]
    diligence = hub["modules"]["diligence"]
    ctx = project_context(payload, scenario)
    return {
        "project_id": scenario.id,
        "project_name": scenario.project_name,
        "status": scenario.status,
        "location": {
            "country": scenario.country,
            "state": scenario.state,
            "city": scenario.city,
        },
        "modules": hub["modules"],
        "context_preview": {
            "description_excerpt": (scenario.description or "")[:240],
            "s3_count": len(ctx["investigation_summary"]["s3_blocked_codes"]),
            "contract_count": len(contracts.get("documents") or []),
            "diligence_issue_count": len(diligence.get("issues") or []),
            "intelligence_issue_count": (payload.get("project_hub") or {})
            .get("modules", {})
            .get("intelligence", {})
            .get("issue_count", 0),
        },
        "routes": {
            "investigation": f"/projects/{scenario.id}?tab=investigation",
            "contracts": f"/projects/{scenario.id}?tab=contracts",
            "diligence": f"/projects/{scenario.id}?tab=diligence",
        },
        "contract_investigation_links": _contract_investigation_links(payload, scenario),
    }


def _contract_investigation_links(payload: dict[str, Any], scenario: InvestigationScenario) -> list[dict[str, Any]]:
    ensure_project_hub(payload)
    links: list[dict[str, Any]] = list(payload.get("project_hub", {}).get("cross_links") or [])
    contracts = payload.get("project_hub", {}).get("modules", {}).get("contracts") or {}
    summary_items: list[dict[str, Any]] = []
    for doc in contracts.get("documents") or []:
        analysis = doc.get("analysis") or {}
        if doc.get("status") != "analyzed":
            continue
        findings = doc.get("findings") or []
        red = sum(1 for f in findings if f.get("risk") == "RED")
        yellow = sum(1 for f in findings if f.get("risk") == "YELLOW")
        suggested_codes: list[str] = []
        for f in findings:
            for rule in f.get("matched_rules") or []:
                if rule.get("id") == "lgpd_dpa":
                    suggested_codes.extend(["DAT-001", "DAT-002"])
            inv = f.get("investigation_link")
            if inv:
                suggested_codes.extend(["data_compliance"])
        tier_report = (payload.get("tier_report") or {})
        s3_codes = tier_report.get("s3_codes") or []
        summary_items.append(
            {
                "contract_id": doc.get("id"),
                "filename": doc.get("filename"),
                "red_count": red,
                "yellow_count": yellow,
                "suggested_checklist_codes": sorted(set(suggested_codes)),
                "s3_cross_check": bool(s3_codes),
                "banner": (
                    "协查硬阻断项需与合同条款交叉核对"
                    if s3_codes
                    else None
                ),
                "analyzed_at": analysis.get("analyzed_at"),
            }
        )
    return summary_items or links


def link_contract_to_investigation(payload: dict[str, Any], contract_id: str, note: str) -> None:
    ensure_project_hub(payload)
    links = payload["project_hub"].setdefault("cross_links", [])
    links.append({"type": "contract_investigation", "contract_id": contract_id, "note": note})


def apply_profile_threshold(base: int, profile: dict[str, Any]) -> int:
    adj = int(profile.get("match_threshold_adjustment") or 0)
    return max(50, min(95, base + adj))
