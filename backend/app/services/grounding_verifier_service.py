"""Lavern-inspired grounding: verify RAG excerpts against corpus source text."""

from __future__ import annotations

from typing import Any

from app.services.corpus_text_cleaner import text_for_retrieval
from app.services.grounding_utils import (
    GROUNDED_THRESHOLD,
    GROUNDED_THRESHOLD_HIGH,
    normalize_text,
    verify_snippet_in_source,
)
from app.services.legal_ingest import load_corpus


def verify_hit_grounding(
    hit: dict[str, Any],
    doc: dict[str, Any] | None,
    *,
    priority: str = "medium",
) -> dict[str, Any]:
    excerpt_raw = hit.get("excerpt_pt") or hit.get("text_pt") or hit.get("excerpt_zh") or ""
    if not doc:
        return {
            "hit_id": hit.get("id"),
            "grounded": False,
            "grounding_score": 0.0,
            "citation_status": "ungrounded",
            "reason": "语料条目不存在",
        }

    source = (doc.get("text_pt_clean") or doc.get("text_pt") or text_for_retrieval(doc) or "")
    threshold = GROUNDED_THRESHOLD_HIGH if priority == "high" else GROUNDED_THRESHOLD
    check = verify_snippet_in_source(
        excerpt_raw,
        source,
        grounded_threshold=threshold,
    )

    return {
        "hit_id": hit.get("id"),
        "grounded": check["grounded"],
        "grounding_score": check["grounding_score"],
        "citation_status": check["citation_status"],
        "reason": check["reason"],
    }


def apply_hit_grounding(
    hit: dict[str, Any],
    doc: dict[str, Any] | None,
    *,
    priority: str = "medium",
) -> dict[str, Any]:
    """Return hit dict with grounding_score and citation_status attached."""
    check = verify_hit_grounding(hit, doc, priority=priority)
    out = dict(hit)
    out["grounding_score"] = check["grounding_score"]
    out["grounded"] = check["grounded"]
    out["citation_status"] = check["citation_status"]
    if check.get("reason"):
        out["grounding_note"] = check["reason"]
    return out


def verify_sections_grounding(sections: list[dict[str, Any]]) -> dict[str, Any]:
    corpus = load_corpus()
    by_id = {d["id"]: d for d in corpus.get("sources", []) if d.get("id")}
    item_results: list[dict[str, Any]] = []
    total_hits = 0
    grounded_hits = 0

    enriched_sections: list[dict[str, Any]] = []

    for section in sections:
        items_out: list[dict[str, Any]] = []
        for item in section.get("items", []):
            code = item.get("code")
            priority = item.get("priority", "medium")
            hit_checks: list[dict[str, Any]] = []
            hits_out: list[dict[str, Any]] = []
            for hit in item.get("legal_hits") or []:
                total_hits += 1
                doc = by_id.get(hit.get("id", ""))
                enriched = apply_hit_grounding(hit, doc, priority=priority)
                hits_out.append(enriched)
                check = verify_hit_grounding(hit, doc, priority=priority)
                if check["grounded"]:
                    grounded_hits += 1
                hit_checks.append(check)
            if hit_checks:
                item_results.append(
                    {
                        "code": code,
                        "title": item.get("title"),
                        "hits": hit_checks,
                        "all_grounded": all(h["grounded"] for h in hit_checks),
                    }
                )
            items_out.append({**item, "legal_hits": hits_out})
        enriched_sections.append({**section, "items": items_out})

    ungrounded_codes = [r["code"] for r in item_results if not r["all_grounded"]]
    return {
        "sections": enriched_sections,
        "total_hits": total_hits,
        "grounded_hits": grounded_hits,
        "grounding_rate": round(grounded_hits / total_hits, 3) if total_hits else 1.0,
        "ungrounded_codes": ungrounded_codes,
        "items": item_results,
        "requires_legal_check": bool(ungrounded_codes),
    }
