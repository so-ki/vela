"""Material scope House Rules review (B2) — rule-only, no LLM."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.structured_playbook_service import evaluate_text_rule
from app.services.contract_house_rules_service import rule_detected

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "material_house_rules.json"


def load_material_house_rules() -> list[dict[str, Any]]:
    with open(RULES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("rules") or [])


def _build_corpus(scenario: InvestigationScenario, payload: dict[str, Any]) -> str:
    parts = [
        scenario.description or "",
        scenario.project_name or "",
        scenario.investment_structure or "",
        scenario.investment_destination or "",
        scenario.project_content_scale or "",
        scenario.facility_notes or "",
        scenario.capacity_notes or "",
        scenario.known_risks or "",
        scenario.remarks or "",
        str(scenario.employee_count or ""),
    ]
    doc = payload.get("document_extract") or {}
    for key in ("description", "known_risks", "facility_notes", "capacity_notes", "project_content_scale"):
        val = doc.get(key)
        if val:
            parts.append(str(val))
    texts = payload.get("_material_full_texts") or {}
    if isinstance(texts, dict):
        parts.extend(str(v) for v in texts.values() if v)
    return "\n".join(p for p in parts if p)


def _evaluate_special_rule(
    rule: dict[str, Any],
    corpus: str,
    scenario: InvestigationScenario,
) -> Optional[dict[str, Any]]:
    rule_id = rule.get("id")
    if rule_id == "missing_destination":
        if not rule_detected(corpus, rule):
            return None
        dest = (scenario.investment_destination or "").strip()
        doc_dest = ((scenario.checklist.payload or {}).get("document_extract") or {}).get(
            "investment_destination"
        ) if scenario.checklist else None
        if dest or (doc_dest and str(doc_dest).strip()):
            return None
        if re.search(r"未说明具体城市|目的地不明|location TBD|destino não informado", corpus, re.I):
            pass
        elif (scenario.city or "").strip() and scenario.city not in ("待定", "TBD"):
            return None
        return {
            "rule_id": rule_id,
            "label": rule["label"],
            "severity": rule.get("severity", "medium"),
            "risk": "YELLOW",
            "risk_label": "设厂/厂房描述但投资目的地不完整",
            "tier": "S2",
            "issues": [{"type": "missing_destination", "note": "缺 investment_destination 或城市线索"}],
            "guidance": rule.get("guidance", ""),
            "grounded": True,
            "grounding_span": corpus[:200],
            "feeds_checklist": list(rule.get("feeds_checklist") or []),
            "dimension": rule.get("dimension"),
        }

    if rule_id == "env_claim_vs_new_build":
        if not rule_detected(corpus, rule):
            return None
        build_patterns = [r"新建", r"扩建", r"产线", r"m²", r"平方米", r"MW", r"GWh", r"greenfield", r"expans"]
        if not any(re.search(p, corpus, re.I) for p in build_patterns):
            return None
        return {
            "rule_id": rule_id,
            "label": rule["label"],
            "severity": rule.get("severity", "medium"),
            "risk": "YELLOW",
            "risk_label": "宣称无需环评但含新建/扩建线索 · 冲突",
            "tier": "S2",
            "issues": [{"type": "env_claim_conflict", "note": "环评主张与建设规模线索不一致"}],
            "guidance": rule.get("guidance", ""),
            "grounded": True,
            "grounding_span": corpus[:200],
            "feeds_checklist": list(rule.get("feeds_checklist") or []),
            "dimension": rule.get("environment"),
        }

    if rule_id == "lgpd_dimension_hint":
        if not rule_detected(corpus, rule):
            return None
        if re.search(r"LGPD|data_compliance|proteção de dados|protecao de dados", corpus, re.I):
            return None
        return evaluate_text_rule(corpus, rule, full_text=corpus)

    return evaluate_text_rule(corpus, rule, full_text=corpus)


def run_material_scope_review(
    scenario: InvestigationScenario,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return material scope findings grounded to corpus text."""
    corpus = _build_corpus(scenario, payload)
    if not corpus.strip():
        return []

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rule in load_material_house_rules():
        result = _evaluate_special_rule(rule, corpus, scenario)
        if not result or result["rule_id"] in seen:
            continue
        seen.add(result["rule_id"])
        findings.append(
            {
                "rule_id": result["rule_id"],
                "label": result["label"],
                "risk": result["risk"],
                "risk_label": result["risk_label"],
                "severity": result.get("severity", "medium"),
                "guidance": result.get("guidance", ""),
                "issues": result.get("issues") or [],
                "grounded": result.get("grounded", False),
                "grounding_span": result.get("grounding_span"),
                "feeds_checklist": result.get("feeds_checklist") or [],
                "dimension": result.get("dimension"),
            }
        )
    return findings
