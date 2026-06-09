"""Red-flag hints when material claims may conflict with public enforcement watch data (PDF 功能四)."""

from __future__ import annotations

import re
from typing import Any

from app.models.scenario import InvestigationScenario

# 材料中的「无问题」表述 → 冲突类型
_CLAIM_PATTERNS: list[tuple[str, str, str]] = [
    (r"无.*环保.*处罚", "environment", "材料称无环保处罚"),
    (r"无.*环境.*违法", "environment", "材料称无环境违法记录"),
    (r"未.*受到.*环保", "environment", "材料称未受环保监管处罚"),
    (r"no\s+environmental\s+penalt", "environment", "材料称无环境处罚（英文）"),
    (r"无.*劳动.*纠纷", "labor", "材料称无劳动争议"),
    (r"无.*反垄断", "foreign_investment", "材料称无反垄断/并购申报问题"),
]

# 演示级公开线索（生产可对接 IBAMA / 裁判文书 API）
_PUBLIC_WATCH: list[dict[str, Any]] = [
    {
        "watch_id": "ibama-enforcement-sample",
        "conflict_type": "environment",
        "title": "IBAMA 环境执法公开信息线索",
        "summary": "巴西联邦环境执法数据库存在同类制造业项目的处罚/许可延迟先例，建议核对材料「无环保处罚」表述。",
        "source_label": "监测辅线 · 公开数据占位",
        "severity": "medium",
        "suggested_action": "建议法务修改对外表述或补充说明，并考虑外聘当地律所核实。",
    },
    {
        "watch_id": "labor-claim-sample",
        "conflict_type": "labor",
        "title": "用工规模与雇佣计划一致性",
        "summary": "公开渠道常披露大型制造项目分阶段用工信息；若材料仅给出总量而无分期计划，可能与协查口径不一致。",
        "source_label": "监测辅线 · 一致性检查",
        "severity": "low",
        "suggested_action": "建议在材料中补充分期用工计划，或在简报中标注待核实。",
    },
]


def _corpus_text(scenario: InvestigationScenario) -> str:
    parts = [
        scenario.description or "",
        scenario.known_risks or "",
        scenario.project_content_scale or "",
        scenario.remarks or "",
    ]
    return " ".join(parts).lower()


def detect_material_conflicts(
    scenario: InvestigationScenario,
    checklist_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return red-flag hints for legal review (non-blocking)."""
    text = _corpus_text(scenario)
    flags: list[dict[str, Any]] = []
    matched_types: set[str] = set()

    for pattern, conflict_type, claim_label in _CLAIM_PATTERNS:
        if conflict_type in matched_types:
            continue
        if re.search(pattern, text, re.IGNORECASE):
            matched_types.add(conflict_type)
            for watch in _PUBLIC_WATCH:
                if watch["conflict_type"] != conflict_type:
                    continue
                flags.append(
                    {
                        "id": watch["watch_id"],
                        "conflict_type": conflict_type,
                        "severity": watch["severity"],
                        "title": watch["title"],
                        "summary": watch["summary"],
                        "material_claim": claim_label,
                        "source_label": watch["source_label"],
                        "suggested_action": watch["suggested_action"],
                        "affected_brief_sections": _sections_for_type(
                            checklist_payload, conflict_type
                        ),
                    }
                )
                break

    # 雇员数与描述不一致（轻量一致性）
    if scenario.employee_count and scenario.description:
        nums = re.findall(r"(\d{2,4})\s*(?:名|人|employees?)", scenario.description, re.I)
        for n in nums[:3]:
            if abs(int(n) - int(scenario.employee_count)) > max(50, int(scenario.employee_count) * 0.3):
                flags.append(
                    {
                        "id": "workforce-number-mismatch",
                        "conflict_type": "labor",
                        "severity": "low",
                        "title": "用工人数表述不一致",
                        "summary": f"表单雇员数 {scenario.employee_count} 与描述中数字 {n} 差异较大。",
                        "material_claim": "雇员规模",
                        "source_label": "材料一致性检查",
                        "suggested_action": "请业务统一雇员规模表述后再定稿。",
                        "affected_brief_sections": _sections_for_type(checklist_payload, "labor"),
                    }
                )
                break

    return flags


def _sections_for_type(payload: dict[str, Any] | None, dimension_id: str) -> list[str]:
    if not payload:
        return []
    names: list[str] = []
    brief = payload.get("brief") or {}
    for section in brief.get("sections") or []:
        if section.get("dimension_id") == dimension_id:
            names.append(section.get("dimension_name") or dimension_id)
    return names
