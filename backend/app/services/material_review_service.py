from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.services.rule_engine import (
    get_dimension_field_requirements,
    get_material_field_defs,
    get_material_field_labels,
    get_required_material_field_keys,
)
from app.services.rules_registry import resolve_scenario_pack_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _field_value_from_scenario(scenario: InvestigationScenario, key: str) -> Any:
    mapping = {
        "project_name": scenario.project_name,
        "investment_destination": scenario.investment_destination,
        "investment_structure": scenario.investment_structure,
        "funding_source": scenario.funding_source,
        "project_content_scale": scenario.project_content_scale,
        "employee_count": scenario.employee_count,
        "capacity_notes": scenario.capacity_notes,
        "facility_notes": scenario.facility_notes,
        "description": scenario.description,
        "known_risks": scenario.known_risks,
        "remarks": scenario.remarks,
        "board_date": scenario.board_date,
        "start_date": scenario.start_date,
        "production_date": scenario.production_date,
    }
    return mapping.get(key)


def _serialize_field_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _field_def_map(pack_id: str | None = None) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in get_material_field_defs(pack_id) if item.get("key")}


def is_material_field_empty(key: str, value: Any, field_def: dict[str, Any] | None = None) -> bool:
    field_def = field_def or _field_def_map().get(key, {})
    if value is None:
        return True
    if key == "employee_count":
        return value is None or (isinstance(value, int) and value < 1)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        min_length = field_def.get("min_length")
        if min_length and len(stripped) < int(min_length):
            return True
        return False
    return False


def scenario_field_snapshot(scenario: InvestigationScenario) -> dict[str, Any]:
    pack_id = resolve_scenario_pack_id(
        rules_pack_id=scenario.rules_pack_id,
        country=scenario.country,
        checklist_payload=scenario.checklist.payload if scenario.checklist else None,
    )
    keys = [item["key"] for item in get_material_field_defs(pack_id) if item.get("key")]
    return {key: _serialize_field_value(_field_value_from_scenario(scenario, key)) for key in keys}


def _scenario_pack_id(scenario: InvestigationScenario) -> str:
    return resolve_scenario_pack_id(
        rules_pack_id=scenario.rules_pack_id,
        country=scenario.country,
        checklist_payload=scenario.checklist.payload if scenario.checklist else None,
    )


def assess_material_completeness(
    scenario: InvestigationScenario,
    compliance_dimensions: list[str],
) -> dict[str, Any]:
    """Gate A：按维度构成要件检测材料完备性，并附带法规预览。"""
    from app.services.dimension_gate_service import assess_gate_a_preview

    return assess_gate_a_preview(scenario, compliance_dimensions)


def build_material_return_record(
    scenario: InvestigationScenario,
    user: User,
    *,
    compliance_dimensions: list[str],
    missing_fields: list[str] | None = None,
    missing_elements: list[str] | None = None,
    note: Optional[str] = None,
    auto_missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    from app.services.dimension_gate_service import assess_gate_a_preview

    assessment = assess_gate_a_preview(scenario, compliance_dimensions)
    element_labels = assessment.get("element_labels") or {}
    elements_cfg_by_id: dict[str, dict[str, Any]] = {}
    pack_id = _scenario_pack_id(scenario)
    from app.services.dimension_gate_service import get_dimension_elements

    for dim_id in compliance_dimensions:
        for el in get_dimension_elements(pack_id).get(dim_id) or []:
            elements_cfg_by_id[el["id"]] = el

    resolved_elements = list(missing_elements or [])
    if not resolved_elements and missing_fields:
        for el_id, el_cfg in elements_cfg_by_id.items():
            maps = set(el_cfg.get("maps_to_fields") or [])
            if maps & set(missing_fields):
                resolved_elements.append(el_id)
    if not resolved_elements:
        resolved_elements = list(assessment.get("auto_missing_elements") or [])

    if not resolved_elements and not (missing_fields or []):
        raise ValueError("请至少标记一项需业务补充的构成要件")

    resolved_fields = list(missing_fields or [])
    for el_id in resolved_elements:
        el_cfg = elements_cfg_by_id.get(el_id) or {}
        for fk in el_cfg.get("maps_to_fields") or []:
            if fk not in resolved_fields:
                resolved_fields.append(fk)

    labels = get_material_field_labels(pack_id)
    missing_elements_by_dimension: dict[str, list[str]] = {}
    for eid in resolved_elements:
        placed = False
        for dim in compliance_dimensions:
            if any(item["id"] == eid for item in get_dimension_elements(pack_id).get(dim) or []):
                missing_elements_by_dimension.setdefault(dim, []).append(eid)
                placed = True
                break
        if not placed:
            missing_elements_by_dimension.setdefault("_general", []).append(eid)

    missing_by_dimension: dict[str, list[str]] = {}
    dim_reqs = get_dimension_field_requirements(pack_id)
    for dim in compliance_dimensions:
        dim_keys = [key for key in resolved_fields if key in dim_reqs.get(dim, [])]
        if dim_keys:
            missing_by_dimension[dim] = dim_keys
    for key in resolved_fields:
        if key not in {k for keys in missing_by_dimension.values() for k in keys}:
            missing_by_dimension.setdefault("_general", []).append(key)

    now = _utcnow().isoformat()
    element_note_parts = [element_labels.get(eid, eid) for eid in resolved_elements]
    return {
        "return_kind": "materials",
        "status": "returned",
        "selected_dimensions": compliance_dimensions,
        "missing_fields": resolved_fields,
        "missing_elements": resolved_elements,
        "missing_by_dimension": missing_by_dimension,
        "missing_elements_by_dimension": missing_elements_by_dimension,
        "auto_missing_fields": auto_missing_fields or assessment.get("auto_missing_fields") or [],
        "auto_missing_elements": assessment.get("auto_missing_elements") or [],
        "legal_confirmed_fields": resolved_fields,
        "legal_confirmed_elements": resolved_elements,
        "return_note": note.strip() if note else None,
        "returned_at": now,
        "returned_by": user.full_name,
        "returned_by_id": user.id,
        "submitted_snapshot": scenario_field_snapshot(scenario),
        "field_labels": labels,
        "element_labels": element_labels,
        "return_summary_elements": element_note_parts,
    }


def business_feedback_from_material_review(
    material_review: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not material_review:
        return None

    status = material_review.get("status")
    if status != "returned":
        return None

    missing_fields = list(material_review.get("missing_fields") or [])
    missing_elements = list(material_review.get("missing_elements") or [])
    missing_by_dimension = material_review.get("missing_by_dimension") or {}
    missing_elements_by_dimension = material_review.get("missing_elements_by_dimension") or {}
    labels = material_review.get("field_labels") or get_material_field_labels()
    element_labels = material_review.get("element_labels") or {}
    selected_dimensions = list(material_review.get("selected_dimensions") or [])
    return_note = material_review.get("return_note")

    field_items = [
        {
            "field_key": key,
            "label": labels.get(key, key),
            "dimensions": [
                dim
                for dim, keys in missing_by_dimension.items()
                if dim != "_general" and key in keys
            ],
        }
        for key in missing_fields
    ]

    element_items = [
        {
            "element_id": eid,
            "label": element_labels.get(eid, eid),
            "dimensions": [
                dim
                for dim, eids in missing_elements_by_dimension.items()
                if dim != "_general" and eid in eids
            ],
        }
        for eid in missing_elements
    ]

    count = len(missing_elements) or len(missing_fields)
    summary = (
        f"法务已驳回材料，需补充 {count} 项构成要件/字段。"
        + (f" 说明：{return_note}" if return_note else "")
        + " 请在本项目核对表中修改后重新提交，无需重新上传文件（除非法务另有要求）。"
    )

    return {
        "return_kind": "materials",
        "is_returned": True,
        "action_required": True,
        "summary": summary,
        "return_note": return_note,
        "selected_dimensions": selected_dimensions,
        "missing_fields": missing_fields,
        "missing_elements": missing_elements,
        "missing_by_dimension": missing_by_dimension,
        "missing_elements_by_dimension": missing_elements_by_dimension,
        "field_labels": labels,
        "element_labels": element_labels,
        "items": field_items,
        "element_items": element_items,
    }
