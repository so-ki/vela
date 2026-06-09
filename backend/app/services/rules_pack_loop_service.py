"""Rules pack closed-loop: aggregate playbook deviations → change suggestions (approval required)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from app.services.playbook_deviation_service import deviation_stats, list_global_deviations
from app.services.rules_registry import load_rules, resolve_pack_id

IRRELEVANT_MARKERS = (
    "无关",
    "不适用",
    "not applicable",
    "与本项目",
    "out of scope",
    "过度",
    "误触发",
    "不应出现",
)

CORPUS_MARKERS = (
    "法条",
    "依据",
    "引用",
    "urn",
    "lexml",
    "引证",
    "检索",
    "rag",
)


def _item_by_id(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["id"]: i for i in rules.get("checklist_items") or [] if i.get("id")}


def _comments_for_code(deviations: list[dict[str, Any]], code: str) -> str:
    parts = [(d.get("comment") or "").strip() for d in deviations if d.get("code") == code]
    return " ".join(p for p in parts if p).lower()


def _avg_match_score(deviations: list[dict[str, Any]], code: str) -> float:
    scores = [
        float(d.get("match_score") or 0)
        for d in deviations
        if d.get("code") == code and d.get("match_score") is not None
    ]
    return sum(scores) / len(scores) if scores else 0.0


def generate_rules_pack_suggestions(
    pack_id: str | None = None,
    *,
    min_reject_count: int = 2,
) -> dict[str, Any]:
    """Turn deviation logs into read-only rules pack edit proposals (never auto-applies)."""
    resolved = resolve_pack_id(pack_id)
    rules = load_rules(resolved)
    pack = rules.get("pack") or {}
    stats = deviation_stats()
    deviations = list_global_deviations(limit=100)
    items = _item_by_id(rules)

    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in deviations:
        code = d.get("code") or ""
        if code:
            by_code[code].append(d)

    suggestions: list[dict[str, Any]] = []
    for row in stats.get("top_rejected_codes") or []:
        code = row.get("code") or ""
        count = int(row.get("count") or 0)
        if not code or count < min_reject_count:
            continue

        item = items.get(code)
        comments = _comments_for_code(deviations, code)
        avg_score = _avg_match_score(deviations, code)
        title = (item or {}).get("title") or next(
            (d.get("title") for d in by_code.get(code, []) if d.get("title")),
            code,
        )
        sample_comments = [
            (d.get("comment") or "").strip()[:200]
            for d in by_code.get(code, [])[:3]
            if (d.get("comment") or "").strip()
        ]

        if any(m in comments for m in IRRELEVANT_MARKERS):
            suggestions.append(
                {
                    "id": f"suggest-{code}-tighten",
                    "code": code,
                    "title": title,
                    "reject_count": count,
                    "suggestion_type": "tighten_triggers",
                    "priority": "high",
                    "rationale": f"「{code}」累计驳回 {count} 次，评论含「不适用/无关」类表述，疑似 triggers 过宽。",
                    "proposed_changes": [
                        {
                            "field": "triggers",
                            "action": "review_and_narrow",
                            "current": (item or {}).get("triggers") or [],
                            "hint": "收紧关键词或增加 sub_sectors 条件，避免误触发",
                        },
                        {
                            "field": "always_include",
                            "action": "ensure_false",
                            "current": (item or {}).get("always_include", False),
                        },
                    ],
                    "sample_comments": sample_comments,
                    "approval_required": True,
                }
            )
            continue

        if avg_score > 0 and avg_score < 62 and any(m in comments for m in CORPUS_MARKERS):
            suggestions.append(
                {
                    "id": f"suggest-{code}-corpus",
                    "code": code,
                    "title": title,
                    "reject_count": count,
                    "suggestion_type": "expand_corpus_binding",
                    "priority": "medium",
                    "rationale": f"「{code}」驳回 {count} 次且平均匹配度 {avg_score:.0f}，更像引证/语料问题而非清单本身。",
                    "proposed_changes": [
                        {
                            "field": "brazil_legal_corpus.checklist_codes",
                            "action": "add_sources",
                            "target_codes": [code],
                            "hint": "在语料维护页为该核查项补充 URN/Planalto 链接",
                        },
                    ],
                    "sample_comments": sample_comments,
                    "approval_required": True,
                }
            )
            continue

        if count >= 3:
            suggestions.append(
                {
                    "id": f"suggest-{code}-review",
                    "code": code,
                    "title": title,
                    "reject_count": count,
                    "suggestion_type": "review_checklist_item",
                    "priority": "medium",
                    "rationale": f"「{code}」高频驳回（{count} 次），建议组织法务复盘条目描述与 triggers。",
                    "proposed_changes": [
                        {
                            "field": "description",
                            "action": "review",
                            "current": (item or {}).get("description"),
                        },
                        {
                            "field": "triggers",
                            "action": "audit",
                            "current": (item or {}).get("triggers") or [],
                        },
                        {
                            "field": "priority",
                            "action": "consider_adjust",
                            "current": (item or {}).get("priority"),
                        },
                    ],
                    "sample_comments": sample_comments,
                    "approval_required": True,
                }
            )

    # Gate / material patterns from gate_status on deviations
    gate_rejects = [d for d in deviations if (d.get("gate_status") or "").lower() in ("blocked", "missing")]
    if len(gate_rejects) >= 3:
        field_hints = set()
        for d in gate_rejects[:10]:
            c = (d.get("comment") or "") + " " + (d.get("title") or "")
            for key in ("investment_structure", "funding_source", "description", "known_risks"):
                if key in c.lower() or key in c:
                    field_hints.add(key)
        suggestions.append(
            {
                "id": "suggest-gate-material-fields",
                "code": "GATE-A",
                "title": "Gate A 材料要件",
                "reject_count": len(gate_rejects),
                "suggestion_type": "adjust_gate_a_fields",
                "priority": "medium",
                "rationale": "多次 Gate A / 材料打回，建议复核 dimension_field_requirements 是否过严或过松。",
                "proposed_changes": [
                    {
                        "field": "dimension_field_requirements",
                        "action": "review",
                        "hint_fields": sorted(field_hints) or list(
                            (rules.get("dimension_field_requirements") or {}).keys()
                        )[:4],
                    },
                    {
                        "field": "material_intake_policy",
                        "action": "review",
                        "current_philosophy": (rules.get("material_intake_policy") or {}).get("philosophy"),
                    },
                ],
                "sample_comments": [],
                "approval_required": True,
            }
        )

    return {
        "pack_id": pack.get("id") or resolved,
        "pack_version": pack.get("version"),
        "pack_name": pack.get("name"),
        "workflow": "偏差聚合 → 变更建议（只读）→ 法务负责人审批 → 手动发布 rules pack 新版本",
        "auto_apply": False,
        "stats": stats,
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
        "export_hint": f"backend/app/rules/{resolved}.json",
    }


def export_suggestion_draft_markdown(result: dict[str, Any]) -> str:
    """Human-readable draft for legal lead review."""
    lines = [
        f"# 规则包变更建议草案 · {result.get('pack_name')} v{result.get('pack_version')}",
        "",
        f"> {result.get('workflow')} · **不会自动修改 JSON**",
        "",
    ]
    for s in result.get("suggestions") or []:
        lines.append(f"## {s.get('code')} · {s.get('suggestion_type')}")
        lines.append("")
        lines.append(s.get("rationale") or "")
        lines.append("")
        for ch in s.get("proposed_changes") or []:
            lines.append(f"- **{ch.get('field')}** · {ch.get('action')}: {ch.get('hint') or ch.get('current') or ch.get('hint_fields')}")
        if s.get("sample_comments"):
            lines.append("")
            lines.append("样例评论：")
            for c in s["sample_comments"]:
                lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines)
