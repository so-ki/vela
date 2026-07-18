"""Expanded RAG retrieval when first pass fails threshold (PDF 功能三 ↔ 功能二回路)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.legal_rag import retrieve_for_checklist_item


def _best_score(hits: list[dict[str, Any]]) -> float:
    if not hits:
        return 0.0
    return max(float(h.get("match_score") or 0) for h in hits)


def retrieve_item_with_expansion(
    db: Session,
    *,
    item_code: str,
    dimension: str,
    title: str,
    description: str,
    match_threshold: int,
    expansion_context: str = "",
    top_k: int = 3,
    generation_config: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """First pass + frozen expansion; final output is always capped by snapshot top-k."""
    from app.services.generation_guard import require_generation_config

    config = require_generation_config(db, generation_config)
    if (
        top_k != config.retrieval_top_k
        or match_threshold != config.match_threshold
        or expansion_context != str(config.generation_input.get("expansion_context") or "")
    ):
        raise ValueError("expansion 输入与冻结配置不一致")
    if top_k == 0:
        return [], {"passes": 0, "expanded": False, "best_score": 0.0}
    hits = retrieve_for_checklist_item(
        db,
        item_code=item_code,
        dimension=dimension,
        title=title,
        description=description,
        top_k=top_k,
        match_threshold=match_threshold,
        generation_config=generation_config,
    )
    meta: dict[str, Any] = {
        "passes": 1,
        "expanded": False,
        "best_score": _best_score(hits),
    }

    if not config.expansion_enabled or (_best_score(hits) >= match_threshold and hits):
        return hits[:top_k], meta

    expanded_description = " ".join(
        filter(None, [description, expansion_context[: config.expansion_context_limit], title])
    ).strip()
    hits2 = retrieve_for_checklist_item(
        db,
        item_code=item_code,
        dimension=dimension,
        title=title,
        description=expanded_description,
        top_k=config.expansion_candidate_top_k,
        match_threshold=match_threshold,
        min_keyword_score=config.expansion_min_keyword_score,
        expansion_pass=True,
        generation_config=generation_config,
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
    return merged[:top_k], meta
