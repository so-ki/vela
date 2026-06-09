"""Aggregate material/legal adequacy from a generated investigation pack (one-pass model)."""

from __future__ import annotations

from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.dimension_gate_service import assess_gate_a_preview, get_dimension_elements
from app.services.rules_registry import load_rules as load_rules_pack


def _brief_items_by_code(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    brief = payload.get("brief") or {}
    for section in brief.get("sections", []):
        for item in section.get("items", []):
            code = item.get("code")
            if code:
                mapping[code] = item
    return mapping


def _material_block_by_dimension(
    material_preview: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        block["dimension_id"]: block
        for block in material_preview.get("dimensions") or []
    }


def _evaluate_element_from_investigation(
    element_cfg: dict[str, Any],
    material_element: dict[str, Any] | None,
    linked_brief_items: list[dict[str, Any]],
) -> dict[str, Any]:
    el_id = element_cfg["id"]
    label = element_cfg.get("label", el_id)
    required = bool(element_cfg.get("required", True))
    feeds = list(element_cfg.get("feeds_checklist") or [])

    mat_status = (material_element or {}).get("status", "missing")
    mat_excerpt = (material_element or {}).get("excerpt", "")
    mat_source = (material_element or {}).get("source_label", "")

    passed_items = [i for i in linked_brief_items if i.get("gate_status") == "passed"]
    blocked_items = [i for i in linked_brief_items if i.get("gate_status") != "passed"]

    avg_score = 0.0
    if linked_brief_items:
        avg_score = sum(float(i.get("match_score") or 0) for i in linked_brief_items) / len(
            linked_brief_items
        )

    block_reasons = [i.get("block_reason") or "" for i in blocked_items]

    if passed_items:
        status = "covered"
        rationale = f"关联核查项 {', '.join(i['code'] for i in passed_items)} 已通过匹配度门控"
    elif mat_status == "filled" and blocked_items:
        status = "at_risk"
        rationale = (
            f"材料有线索，但关联核查项检索/匹配不足（{'; '.join(block_reasons[:2])}）"
            if block_reasons
            else "材料有线索，关联核查项尚未通过门控"
        )
    elif mat_status == "missing" or (required and mat_status != "filled" and not linked_brief_items):
        status = "missing"
        rationale = "材料未覆盖该构成要件，且协查检索支撑不足"
    elif blocked_items and any("未检索" in r for r in block_reasons):
        status = "missing"
        rationale = "未检索到相关法条片段，可能因材料事实不足或描述过简"
    elif blocked_items:
        status = "at_risk"
        rationale = f"协查条目未过线：{block_reasons[0] if block_reasons else '需法务核对'}"
    elif mat_status == "not_applicable":
        status = "not_applicable"
        rationale = "非必填要件，当前未识别到相关线索"
    else:
        status = "at_risk" if required else "not_applicable"
        rationale = "需结合下方核查条目与材料一并判断"

    excerpt = mat_excerpt
    if not excerpt and passed_items:
        excerpt = (passed_items[0].get("risk_zh") or "")[:220]
    elif not excerpt and blocked_items:
        excerpt = (blocked_items[0].get("risk_zh") or "")[:220]

    return {
        "id": el_id,
        "label": label,
        "required": required,
        "status": status,
        "rationale": rationale,
        "excerpt": excerpt,
        "source_label": mat_source,
        "feeds_checklist": feeds,
        "linked_codes": [i["code"] for i in linked_brief_items],
        "avg_match_score": round(avg_score, 1),
        "passed_count": len(passed_items),
        "blocked_count": len(blocked_items),
    }


def aggregate_investigation_adequacy(
    scenario: InvestigationScenario,
    checklist_payload: dict[str, Any],
    compliance_dimensions: list[str],
) -> dict[str, Any]:
    """Build dimension-level adequacy view from generated brief + material pre-scan."""
    pack_id = scenario.rules_pack_id
    rules = load_rules_pack(pack_id)
    dim_meta = rules.get("dimensions") or {}
    dim_elements_cfg = rules.get("dimension_elements") or {}

    material_preview = assess_gate_a_preview(scenario, compliance_dimensions)
    mat_blocks = _material_block_by_dimension(material_preview)
    brief_by_code = _brief_items_by_code(checklist_payload)

    auto_missing_elements: list[str] = []
    dimension_blocks: list[dict[str, Any]] = []

    for dim_id in compliance_dimensions:
        if dim_id not in dim_meta:
            continue
        meta = dim_meta[dim_id]
        mat_block = mat_blocks.get(dim_id) or {}
        mat_elements = {
            el["id"]: el for el in mat_block.get("elements") or [] if el.get("id")
        }

        evaluated: list[dict[str, Any]] = []
        dim_missing: list[str] = []
        for el_cfg in dim_elements_cfg.get(dim_id) or []:
            codes = el_cfg.get("feeds_checklist") or []
            linked = [brief_by_code[c] for c in codes if c in brief_by_code]
            ev = _evaluate_element_from_investigation(
                el_cfg,
                mat_elements.get(el_cfg["id"]),
                linked,
            )
            evaluated.append(ev)
            if ev["required"] and ev["status"] in ("missing", "at_risk"):
                if ev["status"] == "missing":
                    auto_missing_elements.append(ev["id"])
                    dim_missing.append(ev["id"])

        required_count = sum(1 for e in evaluated if e["required"])
        covered_required = sum(
            1
            for e in evaluated
            if e["required"] and e["status"] in ("covered", "not_applicable")
        )

        dimension_blocks.append(
            {
                "dimension_id": dim_id,
                "dimension_name": meta.get("name", dim_id),
                "dimension_name_pt": meta.get("name_pt", ""),
                "is_complete": covered_required >= required_count if required_count else True,
                "elements": evaluated,
                "law_preview": mat_block.get("law_preview") or [],
                "missing_element_ids": dim_missing,
            }
        )

    brief = checklist_payload.get("brief") or {}
    element_labels = material_preview.get("element_labels") or {}

    material_only_missing = list(material_preview.get("auto_missing_elements") or [])
    suggest_material_return = sorted(
        set(auto_missing_elements) | set(material_only_missing)
    )

    tier_report = checklist_payload.get("tier_report") or {}
    if not tier_report and checklist_payload.get("sections_with_legal"):
        from app.services.match_tier_service import classify_sections

        tiered = classify_sections(
            checklist_payload.get("sections_with_legal") or [],
            base_threshold=int(
                (checklist_payload.get("investigation_settings") or {}).get("match_threshold") or 70
            ),
            grounding_report=checklist_payload.get("grounding_report"),
        )
        tier_report = tiered.get("tier_summary") or {}

    return {
        "mode": "investigation_aggregate",
        "compliance_dimensions": compliance_dimensions,
        "is_material_complete": len(material_only_missing) == 0,
        "is_investigation_ready": len(auto_missing_elements) == 0,
        "suggest_material_return": suggest_material_return,
        "auto_missing_elements": auto_missing_elements,
        "material_precheck_missing": material_only_missing,
        "element_labels": element_labels,
        "dimensions": dimension_blocks,
        "tier_report": tier_report,
        "brief_summary": {
            "passed_count": int(brief.get("passed_count") or 0),
            "blocked_count": int(brief.get("blocked_count") or 0),
            "status": brief.get("status"),
        },
    }


def gate_a_allows_checklist_review(adequacy: dict[str, Any] | None) -> bool:
    """Gate A 构成要件未齐备时不得进入清单条目复核（S3 在定稿阶段硬阻断）。"""
    if not adequacy:
        return True
    return bool(adequacy.get("is_investigation_ready"))


def gate_a_blocking_review_message(adequacy: dict[str, Any] | None) -> Optional[str]:
    if gate_a_allows_checklist_review(adequacy):
        return None
    labels = (adequacy or {}).get("element_labels") or {}
    missing = (adequacy or {}).get("auto_missing_elements") or []
    missing_labels = [labels.get(mid, mid) for mid in missing]
    return (
        f"构成要件尚未完备（{', '.join(missing_labels)}），请先打回业务补充材料，"
        "通过 Gate A 后再进入清单复核。"
    )


def recompute_investigation_adequacy(
    scenario: InvestigationScenario,
    compliance_dimensions: Optional[list[str]] = None,
) -> dict[str, Any] | None:
    if not scenario.checklist:
        return None
    payload = scenario.checklist.payload or {}
    if not payload.get("brief"):
        return None
    dims = compliance_dimensions or list(scenario.compliance_dimensions or [])
    if not dims:
        dims = list((payload.get("material_review") or {}).get("selected_dimensions") or [])
    if not dims:
        dims = list(payload.get("selected_dimensions") or [])
    if not dims:
        return None
    return aggregate_investigation_adequacy(scenario, payload, dims)
