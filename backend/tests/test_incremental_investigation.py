"""Unit tests for incremental investigation delta logic."""

from app.services.incremental_investigation_service import (
    compute_codes_to_refresh,
    diff_field_snapshots,
    merge_investigation_adequacy,
)


def test_diff_field_snapshots_detects_changes():
    baseline = {"description": "旧描述", "employee_count": 100}
    current = {"description": "新描述", "employee_count": 100}
    assert diff_field_snapshots(baseline, current) == ["description"]


def test_compute_codes_to_refresh_includes_new_items():
    new_sections = [{"dimension_id": "labor", "items": [{"code": "LAB-001"}, {"code": "LAB-999"}]}]
    prev_sections = [{"dimension_id": "labor", "items": [{"code": "LAB-001", "legal_hits": []}]}]
    codes = compute_codes_to_refresh(new_sections, prev_sections, {"LAB-001"})
    assert "LAB-001" in codes
    assert "LAB-999" in codes


def test_merge_adequacy_carries_forward_covered_elements():
    fresh = {
        "dimensions": [
            {
                "dimension_id": "labor",
                "elements": [
                    {"id": "lab_workforce", "required": True, "status": "missing", "label": "用工"},
                    {"id": "lab_expat", "required": False, "status": "at_risk", "label": "外派"},
                ],
                "missing_element_ids": ["lab_workforce"],
            }
        ],
        "material_precheck_missing": [],
    }
    previous = {
        "dimensions": [
            {
                "elements": [
                    {"id": "lab_expat", "status": "covered", "label": "外派", "rationale": "ok"},
                ]
            }
        ]
    }
    elements_cfg = {
        "lab_expat": {"maps_to_fields": ["known_risks"]},
        "lab_workforce": {"maps_to_fields": ["description"]},
    }
    merged = merge_investigation_adequacy(
        fresh,
        previous,
        target_elements={"lab_workforce"},
        changed_fields=["description"],
        elements_cfg=elements_cfg,
    )
    by_id = {e["id"]: e for e in merged["dimensions"][0]["elements"]}
    assert by_id["lab_expat"]["carry_forward"] is True
    assert by_id["lab_expat"]["status"] == "covered"
    assert by_id["lab_workforce"]["carry_forward"] is False
    assert merged["is_investigation_ready"] is False
