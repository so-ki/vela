"""Expanded RAG retrieval when first pass fails threshold (PDF 功能三 ↔ 功能二回路)."""

from __future__ import annotations

from typing import Any

from app.services.legal_rag import retrieve_for_checklist_item


def _best_score(hits: list[dict[str, Any]]) -> float:
    if not hits:
        return 0.0
    return max(float(h.get("match_score") or 0) for h in hits)


def retrieve_item_with_expansion(
    *,
    item_code: str,
    dimension: str,
    title: str,
    description: str,
    match_threshold: int,
    expansion_context: str = "",
    top_k: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """First pass standard retrieval; second pass widens query if below threshold."""
    hits = retrieve_for_checklist_item(
        item_code=item_code,
        dimension=dimension,
        title=title,
        description=description,
        top_k=top_k,
        match_threshold=match_threshold,
    )
    meta: dict[str, Any] = {
        "passes": 1,
        "expanded": False,
        "best_score": _best_score(hits),
    }

    if _best_score(hits) >= match_threshold and hits:
        return hits, meta

    expanded_description = " ".join(
        filter(None, [description, expansion_context[:800], title])
    ).strip()
    hits2 = retrieve_for_checklist_item(
        item_code=item_code,
        dimension=dimension,
        title=title,
        description=expanded_description,
        top_k=min(top_k + 2, 6),
        match_threshold=match_threshold,
        min_keyword_score=18.0,
    )

    seen = {h["id"] for h in hits}
    merged = list(hits)
    for h in hits2:
        if h["id"] not in seen:
            merged.append(h)
            seen.add(h["id"])
    merged.sort(key=lambda x: float(x.get("match_score") or 0), reverse=True)

    meta.update(
        {
            "passes": 2,
            "expanded": True,
            "best_score": _best_score(merged),
            "expansion_note": "已扩大检索范围并重新匹配" if merged else "扩大检索仍无有效命中",
        }
    )
    return merged[: top_k + 2], meta
