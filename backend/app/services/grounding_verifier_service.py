"""Lavern-inspired grounding: verify RAG excerpts against corpus source text."""

from __future__ import annotations

import re
from typing import Any

from app.services.legal_ingest import load_corpus


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _overlap_ratio(needle: str, haystack: str) -> float:
    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0
    n_words = set(needle.split())
    h_words = set(haystack.split())
    if not n_words:
        return 0.0
    return len(n_words & h_words) / len(n_words)


def verify_hit_grounding(hit: dict[str, Any], doc: dict[str, Any] | None) -> dict[str, Any]:
    excerpt = _normalize(hit.get("excerpt_pt") or hit.get("text_pt") or "")
    source = _normalize((doc or {}).get("text_pt") or "")
    if not doc:
        return {
            "hit_id": hit.get("id"),
            "grounded": False,
            "grounding_score": 0.0,
            "reason": "语料条目不存在",
        }
    if not excerpt:
        return {
            "hit_id": hit.get("id"),
            "grounded": False,
            "grounding_score": 0.0,
            "reason": "摘录为空",
        }
    ratio = _overlap_ratio(excerpt[:400], source)
    grounded = ratio >= 0.55 or excerpt[:80] in source
    return {
        "hit_id": hit.get("id"),
        "grounded": grounded,
        "grounding_score": round(ratio, 3),
        "reason": None if grounded else "摘录与语料原文匹配度不足，须法务核对",
    }


def verify_sections_grounding(sections: list[dict[str, Any]]) -> dict[str, Any]:
    corpus = load_corpus()
    by_id = {d["id"]: d for d in corpus.get("sources", []) if d.get("id")}
    item_results: list[dict[str, Any]] = []
    total_hits = 0
    grounded_hits = 0

    for section in sections:
        for item in section.get("items", []):
            code = item.get("code")
            hit_checks: list[dict[str, Any]] = []
            for hit in item.get("legal_hits") or []:
                total_hits += 1
                check = verify_hit_grounding(hit, by_id.get(hit.get("id", "")))
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

    ungrounded_codes = [r["code"] for r in item_results if not r["all_grounded"]]
    return {
        "total_hits": total_hits,
        "grounded_hits": grounded_hits,
        "grounding_rate": round(grounded_hits / total_hits, 3) if total_hits else 1.0,
        "ungrounded_codes": ungrounded_codes,
        "items": item_results,
        "requires_legal_check": bool(ungrounded_codes),
    }
