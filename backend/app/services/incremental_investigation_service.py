"""Incremental investigation pack regeneration after material supplement."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.scenario import InvestigationScenario
from app.services.brief_generator import generate_brief
from app.services.dimension_gate_service import get_dimension_elements
from app.services.investigation_adequacy_service import aggregate_investigation_adequacy
from app.services.legal_ingest import ingest_corpus
from app.services.legal_rag import retrieve_for_checklist_incremental
from app.services.material_review_service import scenario_field_snapshot
from app.services.review_service import _flatten_brief_items, _legal_hits_by_code
from app.services.rules_registry import resolve_scenario_pack_id


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def diff_field_snapshots(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    keys = set(baseline.keys()) | set(current.keys())
    for key in sorted(keys):
        if baseline.get(key) != current.get(key):
            changed.append(key)
    return changed


def _elements_cfg_by_id(pack_id: str, compliance_dimensions: list[str]) -> dict[str, dict[str, Any]]:
    cfg: dict[str, dict[str, Any]] = {}
    for dim_id in compliance_dimensions:
        for el in get_dimension_elements(pack_id).get(dim_id) or []:
            cfg[el["id"]] = el
    return cfg


def compute_incremental_targets(
    scenario: InvestigationScenario,
    *,
    compliance_dimensions: list[str],
    baseline_snapshot: dict[str, Any],
    returned_missing_elements: list[str] | None = None,
) -> dict[str, Any]:
    """Determine which fields, elements, and checklist codes need refresh."""
    pack_id = resolve_scenario_pack_id(
        rules_pack_id=scenario.rules_pack_id,
        country=scenario.country,
        checklist_payload=scenario.checklist.payload if scenario.checklist else None,
    )
    current_snapshot = scenario_field_snapshot(scenario)
    changed_fields = diff_field_snapshots(baseline_snapshot, current_snapshot)
    elements_cfg = _elements_cfg_by_id(pack_id, compliance_dimensions)

    target_elements: set[str] = set(returned_missing_elements or [])
    for el_id, el_cfg in elements_cfg.items():
        maps = set(el_cfg.get("maps_to_fields") or [])
        if maps & set(changed_fields):
            target_elements.add(el_id)

    target_codes: set[str] = set()
    for el_id in target_elements:
        el_cfg = elements_cfg.get(el_id) or {}
        target_codes.update(el_cfg.get("feeds_checklist") or [])

    return {
        "pack_id": pack_id,
        "baseline_snapshot": baseline_snapshot,
        "current_snapshot": current_snapshot,
        "changed_fields": changed_fields,
        "target_elements": sorted(target_elements),
        "target_codes": sorted(target_codes),
        "elements_cfg": elements_cfg,
    }


def _items_by_code(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for section in sections or []:
        for item in section.get("items", []):
            code = item.get("code")
            if code:
                mapping[code] = item
    return mapping


def _all_codes(sections: list[dict[str, Any]]) -> set[str]:
    return set(_items_by_code(sections).keys())


def compute_codes_to_refresh(
    new_sections: list[dict[str, Any]],
    previous_sections_with_legal: list[dict[str, Any]],
    target_codes: set[str],
) -> set[str]:
    prev_codes = _all_codes(previous_sections_with_legal)
    new_codes = _all_codes(new_sections)
    new_only = new_codes - prev_codes
    return set(target_codes) | new_only


def merge_investigation_adequacy(
    fresh: dict[str, Any],
    previous_adequacy: dict[str, Any] | None,
    *,
    target_elements: set[str],
    changed_fields: list[str],
    elements_cfg: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not previous_adequacy:
        return fresh

    prev_by_id: dict[str, dict[str, Any]] = {}
    for dim in previous_adequacy.get("dimensions") or []:
        for el in dim.get("elements") or []:
            prev_by_id[el["id"]] = el

    merged_dims: list[dict[str, Any]] = []
    auto_missing: list[str] = []
    carried = 0

    for dim in fresh.get("dimensions") or []:
        merged_elements: list[dict[str, Any]] = []
        dim_missing: list[str] = []
        for el in dim.get("elements") or []:
            el_id = el["id"]
            prev = prev_by_id.get(el_id)
            maps = set((elements_cfg.get(el_id) or {}).get("maps_to_fields") or [])
            can_carry = (
                el_id not in target_elements
                and not (maps & set(changed_fields))
                and prev
                and prev.get("status") in ("covered", "not_applicable")
            )
            if can_carry:
                carried_el = {**prev, "carry_forward": True}
                merged_elements.append(carried_el)
                carried += 1
                if el_id in (dim.get("missing_element_ids") or []):
                    pass
            else:
                merged_el = {**el, "carry_forward": False}
                merged_elements.append(merged_el)
                if merged_el.get("required") and merged_el.get("status") == "missing":
                    auto_missing.append(el_id)
                    dim_missing.append(el_id)

        required_count = sum(1 for e in merged_elements if e.get("required"))
        covered_required = sum(
            1
            for e in merged_elements
            if e.get("required") and e.get("status") in ("covered", "not_applicable")
        )
        merged_dims.append(
            {
                **dim,
                "elements": merged_elements,
                "is_complete": covered_required >= required_count if required_count else True,
                "missing_element_ids": dim_missing,
            }
        )

    material_only_missing = list(fresh.get("material_precheck_missing") or [])
    suggest_return = sorted(set(auto_missing) | set(material_only_missing))

    return {
        **fresh,
        "dimensions": merged_dims,
        "auto_missing_elements": auto_missing,
        "is_investigation_ready": len(auto_missing) == 0,
        "suggest_material_return": suggest_return,
        "carry_forward_stats": {
            "elements_carried": carried,
            "elements_recomputed": sum(
                len(d.get("elements") or []) for d in fresh.get("dimensions") or []
            )
            - carried,
        },
    }


def merge_review_state(
    previous_review: dict[str, Any] | None,
    brief: dict[str, Any],
    payload: dict[str, Any],
    *,
    refresh_codes: set[str],
    reviewer_name: str,
    reviewer_id: int,
) -> dict[str, Any] | None:
    if not previous_review or not previous_review.get("items"):
        return None

    prev_by_code = {i["code"]: i for i in previous_review.get("items", []) if i.get("code")}
    hits_by_code = _legal_hits_by_code(payload)
    merged_items: list[dict[str, Any]] = []
    carried = 0
    invalidated = 0

    for item in _flatten_brief_items(brief):
        code = item["code"]
        prev = prev_by_code.get(code)
        if code in refresh_codes:
            if prev and prev.get("decision") == "approved":
                invalidated += 1
            merged_items.append(
                {
                    "code": code,
                    "title": item["title"],
                    "dimension_name": item.get("dimension_name", ""),
                    "gate_status": item.get("gate_status", "unknown"),
                    "match_score": float(item.get("match_score", 0)),
                    "decision": "pending",
                    "comment": (
                        "材料变更后需重新复核"
                        if prev and prev.get("decision") == "approved"
                        else (prev.get("comment") if prev else None)
                    ),
                    "external_counsel_required": bool(prev.get("external_counsel_required")) if prev else False,
                    "legal_hits": hits_by_code.get(code, [])[:3],
                    "reviewed_at": None,
                    "carry_forward": False,
                    "invalidated": bool(prev and prev.get("decision") == "approved"),
                }
            )
        elif prev:
            merged_items.append(
                {
                    **prev,
                    "gate_status": item.get("gate_status", prev.get("gate_status")),
                    "match_score": float(item.get("match_score", prev.get("match_score", 0))),
                    "legal_hits": hits_by_code.get(code, prev.get("legal_hits", []))[:3],
                    "carry_forward": True,
                }
            )
            carried += 1
        else:
            merged_items.append(
                {
                    "code": code,
                    "title": item["title"],
                    "dimension_name": item.get("dimension_name", ""),
                    "gate_status": item.get("gate_status", "unknown"),
                    "match_score": float(item.get("match_score", 0)),
                    "decision": "pending",
                    "comment": None,
                    "external_counsel_required": False,
                    "legal_hits": hits_by_code.get(code, [])[:3],
                    "reviewed_at": None,
                    "carry_forward": False,
                }
            )

    return {
        "status": "in_progress",
        "reviewer_name": reviewer_name,
        "reviewer_id": reviewer_id,
        "started_at": previous_review.get("started_at") or _utcnow_iso(),
        "finalized_at": None,
        "items": merged_items,
        "carry_forward_stats": {
            "items_carried": carried,
            "items_invalidated": invalidated,
            "items_refreshed": len(refresh_codes),
        },
    }


def run_incremental_investigation_attach(
    scenario: InvestigationScenario,
    checklist_payload: dict[str, Any],
    previous_pack: dict[str, Any],
    *,
    compliance_dimensions: list[str],
    baseline_snapshot: dict[str, Any],
    returned_missing_elements: list[str] | None,
    polish: bool,
    match_threshold: int = 70,
    reviewer_name: str,
    reviewer_id: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge previous pack with delta RAG/brief/adequacy/review. Returns (payload, meta)."""
    targets = compute_incremental_targets(
        scenario,
        compliance_dimensions=compliance_dimensions,
        baseline_snapshot=baseline_snapshot,
        returned_missing_elements=returned_missing_elements,
    )
    new_sections = checklist_payload.get("sections") or []
    prev_legal = previous_pack.get("sections_with_legal") or previous_pack.get("sections") or []
    refresh_codes = compute_codes_to_refresh(new_sections, prev_legal, set(targets["target_codes"]))
    frozen_codes = sorted(_all_codes(prev_legal) & _all_codes(new_sections) - refresh_codes)

    from app.services.scenario_pipeline import _expansion_context

    ingest_corpus(force=False)
    rag_result = retrieve_for_checklist_incremental(
        new_sections,
        prev_legal,
        codes_to_refresh=refresh_codes,
        match_threshold=match_threshold,
        expansion_context=_expansion_context(scenario),
    )
    checklist_payload = {
        **checklist_payload,
        "sections_with_legal": rag_result["sections"],
        "legal_retrieved": True,
    }

    brief = generate_brief(
        scenario,
        checklist_payload,
        sections_with_legal=rag_result["sections"],
        polish=polish,
        threshold=match_threshold,
    )
    checklist_payload = {**checklist_payload, "brief": brief}

    from app.services.conflict_detection_service import detect_material_conflicts
    from app.services.quality_reports_service import attach_quality_reports

    checklist_payload = attach_quality_reports(
        checklist_payload,
        sections_with_legal=rag_result["sections"],
        brief=brief,
    )
    checklist_payload["conflict_flags"] = detect_material_conflicts(scenario, checklist_payload)
    checklist_payload["investigation_settings"] = {
        "match_threshold": match_threshold,
        "expansion_enabled": True,
    }

    fresh_adequacy = aggregate_investigation_adequacy(
        scenario, checklist_payload, compliance_dimensions
    )
    adequacy = merge_investigation_adequacy(
        fresh_adequacy,
        previous_pack.get("investigation_adequacy"),
        target_elements=set(targets["target_elements"]),
        changed_fields=targets["changed_fields"],
        elements_cfg=targets["elements_cfg"],
    )
    checklist_payload["investigation_adequacy"] = adequacy

    merged_review = merge_review_state(
        previous_pack.get("review"),
        brief,
        checklist_payload,
        refresh_codes=refresh_codes,
        reviewer_name=reviewer_name,
        reviewer_id=reviewer_id,
    )
    if merged_review:
        checklist_payload["review"] = merged_review

    meta = {
        "mode": "incremental",
        "changed_fields": targets["changed_fields"],
        "target_elements": targets["target_elements"],
        "target_codes": sorted(refresh_codes),
        "frozen_codes": frozen_codes,
        "regenerated_at": _utcnow_iso(),
        "rag_stats": {
            "refreshed": len(refresh_codes),
            "carried": len(frozen_codes),
            "zero_hit_items": rag_result.get("zero_hit_items") or [],
        },
        "adequacy_stats": adequacy.get("carry_forward_stats"),
        "review_stats": merged_review.get("carry_forward_stats") if merged_review else None,
    }
    checklist_payload["incremental_regen"] = meta
    return checklist_payload, meta


def can_run_incremental(
    old_payload: dict[str, Any],
    material_review: dict[str, Any],
) -> bool:
    history = old_payload.get("investigation_draft_history") or []
    if not history:
        return False
    if material_review.get("status") != "resubmitted":
        return False
    baseline = material_review.get("return_baseline_snapshot")
    if not baseline:
        return False
    last = history[-1]
    return bool(last.get("brief") or last.get("sections_with_legal") or last.get("sections"))
