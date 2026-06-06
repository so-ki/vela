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
    """自动检测：给定协查维度下的必填字段缺项（字段级存储，可按维度聚合展示）。"""
    if not compliance_dimensions:
        raise ValueError("请至少选择一个合规审查维度")

    pack_id = _scenario_pack_id(scenario)
    field_defs = _field_def_map(pack_id)
    required_fields = sorted(get_required_material_field_keys(compliance_dimensions, pack_id))
    dim_reqs = get_dimension_field_requirements(pack_id)
    auto_missing: list[str] = []
    missing_by_dimension: dict[str, list[str]] = {}

    for dim in compliance_dimensions:
        dim_missing: list[str] = []
        for key in dim_reqs.get(dim, []):
            value = _field_value_from_scenario(scenario, key)
            if is_material_field_empty(key, value, field_defs.get(key)):
                if key not in auto_missing:
                    auto_missing.append(key)
                dim_missing.append(key)
        if dim_missing:
            missing_by_dimension[dim] = dim_missing

    for key in required_fields:
        if key in auto_missing:
            continue
        value = _field_value_from_scenario(scenario, key)
        if is_material_field_empty(key, value, field_defs.get(key)):
            auto_missing.append(key)

    field_values = {
        key: _serialize_field_value(_field_value_from_scenario(scenario, key))
        for key in required_fields
    }

    return {
        "compliance_dimensions": compliance_dimensions,
        "required_fields": required_fields,
        "auto_missing_fields": auto_missing,
        "missing_by_dimension": missing_by_dimension,
        "field_values": field_values,
        "field_labels": get_material_field_labels(pack_id),
        "material_fields": get_material_field_defs(pack_id),
    }


def build_material_return_record(
    scenario: InvestigationScenario,
    user: User,
    *,
    compliance_dimensions: list[str],
    missing_fields: list[str],
    note: Optional[str] = None,
    auto_missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    assessment = assess_material_completeness(scenario, compliance_dimensions)
    required = set(assessment["required_fields"])
    invalid = [key for key in missing_fields if key not in required]
    if invalid:
        raise ValueError(f"缺项字段不在当前协查范围内：{', '.join(invalid)}")

    if not missing_fields:
        raise ValueError("请至少标记一项需业务补充的字段")

    labels = get_material_field_labels(_scenario_pack_id(scenario))
    missing_by_dimension: dict[str, list[str]] = {}
    dim_reqs = get_dimension_field_requirements(_scenario_pack_id(scenario))
    for dim in compliance_dimensions:
        dim_keys = [key for key in dim_reqs.get(dim, []) if key in missing_fields]
        if dim_keys:
            missing_by_dimension[dim] = dim_keys
    for key in missing_fields:
        if key not in {k for keys in missing_by_dimension.values() for k in keys}:
            missing_by_dimension.setdefault("_general", []).append(key)

    now = _utcnow().isoformat()
    return {
        "return_kind": "materials",
        "status": "returned",
        "selected_dimensions": compliance_dimensions,
        "missing_fields": missing_fields,
        "missing_by_dimension": missing_by_dimension,
        "auto_missing_fields": auto_missing_fields or assessment["auto_missing_fields"],
        "legal_confirmed_fields": missing_fields,
        "return_note": note.strip() if note else None,
        "returned_at": now,
        "returned_by": user.full_name,
        "returned_by_id": user.id,
        "submitted_snapshot": scenario_field_snapshot(scenario),
        "field_labels": labels,
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
    missing_by_dimension = material_review.get("missing_by_dimension") or {}
    labels = material_review.get("field_labels") or get_material_field_labels()
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

    summary = (
        f"法务已驳回提交表，需补充 {len(missing_fields)} 项字段。"
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
        "missing_by_dimension": missing_by_dimension,
        "field_labels": labels,
        "items": field_items,
    }
