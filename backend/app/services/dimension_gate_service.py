"""Gate A: per-dimension constitutive elements, completeness, and law preview."""

from __future__ import annotations

import re
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.legal_ingest import load_corpus
from app.services.legal_rag import SOURCE_LABELS
from app.services.material_review_service import (
    _field_value_from_scenario,
    _scenario_pack_id,
    _serialize_field_value,
    is_material_field_empty,
)
from app.services.rule_engine import get_material_field_labels
from app.services.rules_registry import load_rules as load_rules_pack


FIELD_LABELS_ZH = {
    "project_name": "项目名称",
    "investment_destination": "投资目的地",
    "investment_structure": "投资结构",
    "funding_source": "资金来源",
    "project_content_scale": "主要内容",
    "description": "业务描述",
    "known_risks": "已知风险",
    "facility_notes": "厂房/设施",
    "capacity_notes": "产能说明",
}


def get_dimension_elements(pack_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    rules = load_rules_pack(pack_id) if pack_id else load_rules_pack(None)
    return dict(rules.get("dimension_elements") or {})


def _build_corpus(scenario: InvestigationScenario) -> str:
    parts = [
        scenario.project_name or "",
        scenario.description or "",
        scenario.investment_structure or "",
        scenario.investment_destination or "",
        scenario.project_content_scale or "",
        scenario.funding_source or "",
        scenario.known_risks or "",
        scenario.facility_notes or "",
        scenario.capacity_notes or "",
        scenario.remarks or "",
        str(scenario.employee_count or ""),
    ]
    payload = scenario.checklist.payload if scenario.checklist else {}
    extract = payload.get("document_extract") or {}
    if isinstance(extract, dict):
        merged = extract.get("merged") or extract
        if isinstance(merged, dict):
            for key in ("description", "project_content_scale", "investment_structure"):
                val = merged.get(key)
                if val and isinstance(val, str):
                    parts.append(val)
    return " ".join(p for p in parts if p).lower()


def _hint_in_corpus(hint: str, corpus: str) -> bool:
    h = hint.lower().strip()
    if not h:
        return False
    return h in corpus


def _field_excerpt(value: Any, *, max_len: int = 220) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _evaluate_element(
    element: dict[str, Any],
    scenario: InvestigationScenario,
    corpus: str,
    field_defs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    maps_to = list(element.get("maps_to_fields") or [])
    hints = list(element.get("extract_hints") or [])
    required = bool(element.get("required", True))

    filled_fields = [
        key
        for key in maps_to
        if not is_material_field_empty(key, _field_value_from_scenario(scenario, key), field_defs.get(key))
    ]
    matched_hints = [h for h in hints if _hint_in_corpus(h, corpus)]

    has_field = len(filled_fields) > 0
    has_hint = len(matched_hints) > 0

    if has_field or has_hint:
        status = "filled"
    elif required:
        status = "missing"
    else:
        status = "missing"

    excerpt = ""
    source_label = ""
    if filled_fields:
        key = filled_fields[0]
        excerpt = _field_excerpt(_field_value_from_scenario(scenario, key))
        source_label = f"材料核对表 · {FIELD_LABELS_ZH.get(key, key)}"
    elif matched_hints and corpus:
        hint = matched_hints[0]
        idx = corpus.find(hint.lower())
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(corpus), idx + 80)
            excerpt = corpus[start:end].strip()
            if start > 0:
                excerpt = "…" + excerpt
            if end < len(corpus):
                excerpt = excerpt + "…"
        source_label = "方案摘要 · 关键词匹配"
    elif not required:
        status = "not_applicable"

    return {
        "id": element["id"],
        "label": element.get("label", element["id"]),
        "required": required,
        "status": status,
        "excerpt": excerpt,
        "source_label": source_label,
        "matched_hints": matched_hints[:5],
        "filled_fields": filled_fields,
        "feeds_checklist": list(element.get("feeds_checklist") or []),
    }


def _law_preview_for_dimension(
    dimension_id: str,
    elements: list[dict[str, Any]],
    *,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    corpus_data = load_corpus()
    codes: set[str] = set()
    query_parts: list[str] = [dimension_id]
    for el in elements:
        query_parts.append(el.get("label", ""))
        codes.update(el.get("feeds_checklist") or [])

    query = " ".join(query_parts).lower()
    query_tokens = set(re.split(r"[\s,、/\.]+", query))
    query_tokens = {t for t in query_tokens if len(t) >= 2}

    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in corpus_data.get("sources", []):
        if doc.get("dimension") != dimension_id:
            continue
        score = 15.0
        doc_codes = set(doc.get("checklist_codes") or [])
        if codes & doc_codes:
            score += 40.0
        tags = {t.lower() for t in doc.get("tags", [])}
        title = (doc.get("title_zh") or "") + " " + (doc.get("title_pt") or "")
        title_tokens = set(re.split(r"[\s,、/\.]+", title.lower()))
        overlap = len(query_tokens & (tags | title_tokens))
        score += overlap * 6.0
        if score >= 20.0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    hits: list[dict[str, Any]] = []
    for score, doc in scored[:top_k]:
        source = doc.get("source", "lexml")
        hits.append(
            {
                "id": doc["id"],
                "title_zh": doc.get("title_zh", ""),
                "title_pt": doc.get("title_pt", ""),
                "source_label": SOURCE_LABELS.get(source, source),
                "url": doc.get("url", ""),
                "excerpt_zh": (doc.get("text_zh") or "")[:200],
                "preview_score": round(min(100.0, score), 1),
            }
        )
    return hits


def assess_gate_a_preview(
    scenario: InvestigationScenario,
    compliance_dimensions: list[str],
) -> dict[str, Any]:
    if not compliance_dimensions:
        raise ValueError("请至少选择一个合规审查维度")

    pack_id = _scenario_pack_id(scenario)
    rules = load_rules_pack(pack_id)
    dim_elements_cfg = rules.get("dimension_elements") or {}
    dim_meta = rules.get("dimensions") or {}
    field_defs = {item["key"]: item for item in rules.get("material_fields", []) if item.get("key")}

    corpus = _build_corpus(scenario)
    auto_missing_elements: list[str] = []
    missing_by_dimension: dict[str, list[str]] = {}
    auto_missing_fields: list[str] = []
    dimension_blocks: list[dict[str, Any]] = []

    for dim_id in compliance_dimensions:
        if dim_id not in dim_meta:
            continue
        meta = dim_meta[dim_id]
        elements_cfg = dim_elements_cfg.get(dim_id) or []
        evaluated = [
            _evaluate_element(el, scenario, corpus, field_defs) for el in elements_cfg
        ]
        dim_missing: list[str] = []
        for el in evaluated:
            if el["required"] and el["status"] == "missing":
                auto_missing_elements.append(el["id"])
                dim_missing.append(el["id"])
                for fk in el.get("filled_fields") or []:
                    if fk not in auto_missing_fields:
                        pass
                cfg = next((c for c in elements_cfg if c["id"] == el["id"]), {})
                for fk in cfg.get("maps_to_fields") or []:
                    if is_material_field_empty(
                        fk, _field_value_from_scenario(scenario, fk), field_defs.get(fk)
                    ):
                        if fk not in auto_missing_fields:
                            auto_missing_fields.append(fk)

        if dim_missing:
            missing_by_dimension[dim_id] = dim_missing

        required_count = sum(1 for e in evaluated if e["required"])
        filled_required = sum(
            1 for e in evaluated if e["required"] and e["status"] == "filled"
        )
        dimension_blocks.append(
            {
                "dimension_id": dim_id,
                "dimension_name": meta.get("name", dim_id),
                "dimension_name_pt": meta.get("name_pt", ""),
                "is_complete": filled_required >= required_count if required_count else True,
                "elements": evaluated,
                "law_preview": _law_preview_for_dimension(dim_id, evaluated),
            }
        )

    element_labels = {
        el["id"]: el.get("label", el["id"])
        for dim_id in compliance_dimensions
        for el in dim_elements_cfg.get(dim_id) or []
    }

    field_labels = get_material_field_labels(pack_id)
    required_fields = sorted(
        {
            fk
            for dim_id in compliance_dimensions
            for el in dim_elements_cfg.get(dim_id) or []
            if el.get("required")
            for fk in el.get("maps_to_fields") or []
        }
        | {
            item["key"]
            for item in rules.get("material_fields", [])
            if item.get("always_required") and item.get("key")
        }
    )

    return {
        "compliance_dimensions": compliance_dimensions,
        "gate_mode": "dimension_elements",
        "is_complete": len(auto_missing_elements) == 0,
        "dimensions": dimension_blocks,
        "auto_missing_elements": auto_missing_elements,
        "missing_by_dimension": missing_by_dimension,
        "element_labels": element_labels,
        "auto_missing_fields": auto_missing_fields,
        "required_fields": required_fields,
        "field_values": {
            key: _serialize_field_value(_field_value_from_scenario(scenario, key))
            for key in required_fields
        },
        "field_labels": field_labels,
        "material_fields": rules.get("material_fields", []),
    }


def gate_a_blocking_message(preview: dict[str, Any]) -> Optional[str]:
    if preview.get("is_complete"):
        return None
    labels = preview.get("element_labels") or {}
    missing = preview.get("auto_missing_elements") or []
    missing_labels = [labels.get(mid, mid) for mid in missing]
    return f"构成要件仍不完整（{', '.join(missing_labels)}），请驳回业务补充或待材料齐全后再确认。"
