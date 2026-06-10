from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.disclaimer import DISCLAIMER_FULL_TEXT

DEFAULT_THRESHOLD = 70

PRIORITY_RISK = {"high": "高", "medium": "中", "low": "低"}
PRIORITY_RISK_PT = {"high": "alta", "medium": "média", "low": "baixa"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _best_hit(hits: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not hits:
        return None
    return max(hits, key=lambda h: float(h.get("match_score", 0)))


def _citation(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": hit.get("id", ""),
        "source_label": hit.get("source_label", ""),
        "title_zh": hit.get("title_zh", ""),
        "title_pt": hit.get("title_pt", ""),
        "url": hit.get("url", ""),
        "match_score": float(hit.get("match_score", 0)),
        "requires_review": bool(hit.get("requires_review", False)),
        "grounding_score": float(hit.get("grounding_score", 0)),
        "citation_status": hit.get("citation_status", "ungrounded"),
        "grounded": bool(hit.get("grounded", False)),
    }


def _gate_item(item: dict[str, Any], *, threshold: int) -> tuple[str, Optional[str], float, bool]:
    if item.get("tier"):
        return (
            item.get("gate_status", "blocked"),
            item.get("block_reason"),
            float(item.get("match_score") or 0),
            bool(item.get("requires_review", item.get("tier") != "S1")),
        )

    hits = item.get("legal_hits") or []
    best = _best_hit(hits)
    score = float(best.get("match_score", 0)) if best else 0.0

    if not hits:
        return "blocked", "未检索到相关法条片段", score, True
    if score < threshold:
        return "blocked", f"最高匹配度 {score:.0f} 低于阈值 {threshold}", score, True
    return "passed", None, score, False


def _risk_text_zh(item: dict[str, Any], best: Optional[dict[str, Any]], gate_status: str, block_reason: Optional[str]) -> str:
    if gate_status == "blocked":
        return (
            f"核查项「{item['title']}」暂未纳入自动简报：{block_reason}。"
            f"建议法务人工补充检索或外聘律所意见。核查要点：{item['description']}"
        )
    assert best is not None
    excerpt = best.get("excerpt_zh") or best.get("text_zh") or best.get("excerpt_pt", "")
    return (
        f"针对「{item['title']}」：{item['description']} "
        f"相关依据为《{best.get('title_zh') or best.get('title_pt', '')}》"
        f"（匹配度 {best.get('match_score', 0):.0f}）。{excerpt}"
    )


def _risk_text_pt(item: dict[str, Any], best: Optional[dict[str, Any]], gate_status: str, block_reason: Optional[str]) -> str:
    if gate_status == "blocked":
        return (
            f"O item «{item['title']}» não foi incluído automaticamente no briefing: {block_reason}. "
            f"Recomenda-se revisão jurídica manual. Ponto de verificação: {item['description']}"
        )
    assert best is not None
    excerpt = best.get("excerpt_pt") or best.get("text_pt", "")
    return (
        f"Quanto a «{item['title']}»: {item['description']} "
        f"Fundamento: {best.get('title_pt', '')} "
        f"(aderência {best.get('match_score', 0):.0f}). {excerpt}"
    )


def _section_risk_level(items: list[dict[str, Any]]) -> str:
    passed = [i for i in items if i["gate_status"] == "passed"]
    if not passed:
        return "high"
    if any(i["priority"] == "high" and i["gate_status"] == "blocked" for i in items):
        return "high"
    if any(i["gate_status"] == "blocked" for i in items):
        return "medium"
    return "low"


def _section_summary_zh(dimension_name: str, items: list[dict[str, Any]]) -> str:
    passed = sum(1 for i in items if i["gate_status"] == "passed")
    blocked = len(items) - passed
    level = _section_risk_level(items)
    level_zh = {"high": "较高", "medium": "中等", "low": "可控"}[level]
    return (
        f"{dimension_name}维度共 {len(items)} 项核查要点，"
        f"其中 {passed} 项已通过法条匹配门控（≥70 分），{blocked} 项需法务复核。"
        f"综合风险水平：{level_zh}。"
    )


def _section_summary_pt(dimension_name_pt: str, items: list[dict[str, Any]]) -> str:
    passed = sum(1 for i in items if i["gate_status"] == "passed")
    blocked = len(items) - passed
    level = _section_risk_level(items)
    level_pt = {"high": "elevado", "medium": "moderado", "low": "controlável"}[level]
    return (
        f"Dimensão {dimension_name_pt}: {len(items)} itens de verificação; "
        f"{passed} aprovados no gate de aderência (≥70), {blocked} exigem revisão jurídica. "
        f"Risco agregado: {level_pt}."
    )


def _executive_summary_zh(scenario: InvestigationScenario, checklist: dict[str, Any], passed: int, blocked: int) -> str:
    sub_sectors = checklist.get("detected_sub_sectors") or []
    sub_label = ""
    if sub_sectors:
        names = "、".join(s.get("name", "") for s in sub_sectors if s.get("name"))
        if names:
            sub_label = f"识别子赛道：{names}。"
    pack = checklist.get("industry_pack_name") or "巴西 · 投资协查"
    return (
        f"本简报针对项目「{scenario.project_name}」（{pack} · "
        f"{checklist.get('detected_action_type_name', scenario.action_type)}），"
        f"{sub_label}"
        f"基于专项核查清单与 LexML/STF/STJ 法源检索结果汇编。"
        f"共 {passed + blocked} 条核查项，{passed} 条已自动纳入风险摘要，{blocked} 条因匹配度不足或未命中法条而标注「需法务复核」。"
        f"本文件为协查底稿，不构成正式法律意见。"
    )


def _executive_summary_pt(scenario: InvestigationScenario, checklist: dict[str, Any], passed: int, blocked: int) -> str:
    return (
        f"Este briefing refere-se ao projeto «{scenario.project_name}» "
        f"({checklist.get('detected_industry_name', scenario.industry)} · "
        f"{checklist.get('detected_action_type_name', scenario.action_type)}), "
        f"compilado a partir da checklist de verificação e fontes LexML/STF/STJ. "
        f"Total de {passed + blocked} itens: {passed} incluídos no resumo automático; "
        f"{blocked} marcados para revisão jurídica por baixa aderência ou ausência de fontes. "
        f"Documento de apoio; não constitui parecer jurídico formal."
    )


def generate_brief(
    scenario: InvestigationScenario,
    checklist_payload: dict[str, Any],
    *,
    sections_with_legal: Optional[list[dict[str, Any]]] = None,
    threshold: int = DEFAULT_THRESHOLD,
    polish: bool = False,
) -> dict[str, Any]:
    sections = sections_with_legal or checklist_payload.get("sections_with_legal") or []
    if not sections:
        raise ValueError("请先完成法源检索（POST /scenarios/{id}/retrieve）")

    brief_sections: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    passed_count = 0
    blocked_count = 0

    for section in sections:
        section_items: list[dict[str, Any]] = []
        for item in section.get("items", []):
            gate_status, block_reason, score, requires_review = _gate_item(item, threshold=threshold)
            hits = item.get("legal_hits") or []
            best = _best_hit(hits)

            brief_item = {
                "code": item["code"],
                "title": item["title"],
                "priority": item.get("priority", "medium"),
                "gate_status": gate_status,
                "match_score": score,
                "requires_review": requires_review,
                "block_reason": block_reason,
                "tier": item.get("tier", "S1" if gate_status == "passed" else "S2"),
                "tier_label": item.get("tier_label", ""),
                "hard_block": bool(item.get("hard_block")),
                "risk_zh": _risk_text_zh(item, best, gate_status, block_reason),
                "risk_pt": _risk_text_pt(item, best, gate_status, block_reason),
                "citations": [_citation(h) for h in hits[:3]],
            }
            section_items.append(brief_item)
            if gate_status == "passed":
                passed_count += 1
            else:
                blocked_count += 1
                blocked_items.append(brief_item)

        brief_sections.append(
            {
                "dimension_id": section["dimension_id"],
                "dimension_name": section["dimension_name"],
                "dimension_name_pt": section.get("dimension_name_pt", ""),
                "risk_level": _section_risk_level(section_items),
                "summary_zh": _section_summary_zh(section["dimension_name"], section_items),
                "summary_pt": _section_summary_pt(section.get("dimension_name_pt", ""), section_items),
                "items": section_items,
            }
        )

    if passed_count == 0:
        status = "blocked"
    elif blocked_count > 0:
        status = "partial"
    else:
        status = "ready"

    title_zh = f"法律风险协查简报 — {scenario.project_name}"
    title_pt = f"Briefing de Riscos Jurídicos — {scenario.project_name}"

    brief = {
        "scenario_id": scenario.id,
        "status": status,
        "threshold": threshold,
        "title_zh": title_zh,
        "title_pt": title_pt,
        "summary_zh": _executive_summary_zh(scenario, checklist_payload, passed_count, blocked_count),
        "summary_pt": _executive_summary_pt(scenario, checklist_payload, passed_count, blocked_count),
        "sections": brief_sections,
        "blocked_items": blocked_items,
        "passed_count": passed_count,
        "blocked_count": blocked_count,
        "disclaimer": DISCLAIMER_FULL_TEXT,
        "generated_at": _utcnow().isoformat(),
        "mode": "template",
    }

    if polish:
        from app.core.config import get_settings
        from app.services.llm_client import polish_brief

        if get_settings().llm_polish_enabled:
            brief, err = polish_brief(brief)
            if err and brief.get("mode") == "template":
                brief["llm_polish_skipped"] = err

    return brief
