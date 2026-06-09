from __future__ import annotations

import re
from typing import Any

from app.core.chroma_client import _chroma_available
from app.services.legal_ingest import load_corpus

SOURCE_LABELS = {
    "lexml": "LexML Brasil",
    "planalto-legislacao": "Planalto 立法",
    "stf": "STF 最高法院",
    "stj": "STJ 高等司法法院",
    "trabalho": "劳动与就业部 gov.br",
    "previdencia": "社会保障部 gov.br",
    "receita-federal": "联邦税务局 gov.br",
    "ibama": "IBAMA gov.br",
    "jusbrasil": "Jusbrasil 案例索引",
}


def _tokenize(text: str) -> set[str]:
    parts = re.split(r"[\s,、/\.]+", text.lower())
    return {p for p in parts if len(p) >= 2}


def _score_doc(
    doc: dict[str, Any],
    *,
    item_code: str,
    dimension: str,
    query_tokens: set[str],
) -> float:
    score = 0.0
    if doc.get("dimension") == dimension:
        score += 20.0
    if item_code in doc.get("checklist_codes", []):
        score += 45.0
    tags = set(t.lower() for t in doc.get("tags", []))
    title_tokens = _tokenize(doc.get("title_pt", "") + " " + doc.get("title_zh", ""))
    text_tokens = _tokenize(doc.get("text_pt", "") + " " + doc.get("text_zh", ""))
    overlap = len(query_tokens & (tags | title_tokens | text_tokens))
    score += overlap * 8.0
    return score


def _format_hit(doc: dict[str, Any], match_score: float, item_code: str, *, match_threshold: int = 70) -> dict[str, Any]:
    source = doc.get("source", "lexml")
    requires_review = match_score < match_threshold
    return {
        "id": doc["id"],
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "urn": doc.get("urn", ""),
        "url": doc.get("url", ""),
        "title_pt": doc.get("title_pt", ""),
        "title_zh": doc.get("title_zh", ""),
        "excerpt_pt": (doc.get("text_pt") or "")[:600],
        "excerpt_zh": doc.get("text_zh", ""),
        "validity": doc.get("validity", "vigente"),
        "level": doc.get("level", "federal"),
        "published_at": doc.get("published_at", ""),
        "match_score": round(min(100.0, match_score), 1),
        "vector_similarity": 0.0,
        "keyword_overlap": round(match_score / 100, 3),
        "requires_review": requires_review,
    }


def _retrieve_keyword(
    *,
    item_code: str,
    dimension: str,
    title: str,
    description: str,
    top_k: int,
    match_threshold: int = 70,
    min_keyword_score: float = 25.0,
) -> list[dict[str, Any]]:
    corpus = load_corpus()
    query_tokens = _tokenize(f"{title} {description} {dimension} {item_code}")
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in corpus["sources"]:
        if doc.get("validity") in ("revogado", "repealed", "revoked"):
            continue
        s = _score_doc(doc, item_code=item_code, dimension=dimension, query_tokens=query_tokens)
        if s >= min_keyword_score:
            scored.append((s, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_format_hit(doc, score, item_code, match_threshold=match_threshold) for score, doc in scored[:top_k]]


def _retrieve_chroma(
    *,
    item_code: str,
    dimension: str,
    title: str,
    description: str,
    top_k: int,
    match_threshold: int = 70,
) -> list[dict[str, Any]]:
    from app.core.chroma_client import get_legal_collection

    corpus = load_corpus()
    by_id = {d["id"]: d for d in corpus["sources"]}
    query_text = f"{title} {description} {dimension}"
    collection = get_legal_collection()
    if collection.count() == 0:
        return []

    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=min(top_k * 2, collection.count()),
            where={"dimension": dimension},
        )
    except Exception:
        results = collection.query(
            query_texts=[query_text],
            n_results=min(top_k * 2, collection.count()),
        )

    hits: list[dict[str, Any]] = []
    if not results or not results.get("ids") or not results["ids"][0]:
        return hits

    for idx, doc_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][idx]
        distance = results["distances"][0][idx] if results.get("distances") else 1.0
        codes = (meta.get("checklist_codes") or "").split(",")
        base = max(0.0, (1.0 - distance) * 60)
        boost = 35.0 if item_code in codes else 0.0
        full = by_id.get(doc_id, {})
        if full.get("validity") in ("revogado", "repealed", "revoked"):
            continue
        hits.append(
            _format_hit(full or {"id": doc_id, **meta}, base + boost, item_code, match_threshold=match_threshold)
        )

    hits.sort(key=lambda h: h["match_score"], reverse=True)
    return hits[:top_k]


def retrieve_for_checklist_item(
    *,
    item_code: str,
    dimension: str,
    title: str,
    description: str,
    top_k: int = 3,
    match_threshold: int = 70,
    min_keyword_score: float = 25.0,
) -> list[dict[str, Any]]:
    hits = _retrieve_keyword(
        item_code=item_code,
        dimension=dimension,
        title=title,
        description=description,
        top_k=top_k,
        match_threshold=match_threshold,
        min_keyword_score=min_keyword_score,
    )

    if _chroma_available and len(hits) < top_k:
        try:
            chroma_hits = _retrieve_chroma(
                item_code=item_code,
                dimension=dimension,
                title=title,
                description=description,
                top_k=top_k,
                match_threshold=match_threshold,
            )
            seen = {h["id"] for h in hits}
            for h in chroma_hits:
                if h["id"] not in seen:
                    hits.append(h)
                    seen.add(h["id"])
            hits.sort(key=lambda x: x["match_score"], reverse=True)
        except Exception:
            pass

    return hits[:top_k]


def retrieve_for_checklist_incremental(
    new_sections: list[dict[str, Any]],
    previous_sections_with_legal: list[dict[str, Any]],
    *,
    codes_to_refresh: set[str],
    top_k: int = 3,
    match_threshold: int = 70,
    expansion_context: str = "",
) -> dict[str, Any]:
    from app.services.retrieval_expansion import retrieve_item_with_expansion

    prev_by_code: dict[str, dict[str, Any]] = {}
    for section in previous_sections_with_legal:
        for item in section.get("items", []):
            code = item.get("code")
            if code:
                prev_by_code[code] = item

    enriched_sections: list[dict[str, Any]] = []
    total_hits = 0
    zero_hit_items: list[str] = []
    refreshed = 0
    carried = 0

    for section in new_sections:
        items_out: list[dict[str, Any]] = []
        for item in section.get("items", []):
            code = item["code"]
            if code not in codes_to_refresh and code in prev_by_code:
                prev_item = prev_by_code[code]
                hits = list(prev_item.get("legal_hits") or [])
                carried += 1
                items_out.append(
                    {
                        **item,
                        "legal_hits": hits,
                        "retrieval_status": prev_item.get("retrieval_status", "ok" if hits else "no_match"),
                        "carry_forward": True,
                    }
                )
                total_hits += len(hits)
                if not hits:
                    zero_hit_items.append(code)
            else:
                hits, rmeta = retrieve_item_with_expansion(
                    item_code=code,
                    dimension=section["dimension_id"],
                    title=item["title"],
                    description=item["description"],
                    match_threshold=match_threshold,
                    expansion_context=expansion_context,
                    top_k=top_k,
                )
                status = "ok" if hits else "no_match"
                if rmeta.get("expanded") and rmeta.get("best_score", 0) < match_threshold:
                    status = "expanded_below_threshold"
                refreshed += 1
                if not hits:
                    zero_hit_items.append(code)
                total_hits += len(hits)
                items_out.append(
                    {
                        **item,
                        "legal_hits": hits,
                        "retrieval_status": status,
                        "retrieval_meta": rmeta,
                        "carry_forward": False,
                    }
                )
        enriched_sections.append({**section, "items": items_out})

    return {
        "sections": enriched_sections,
        "total_hits": total_hits,
        "zero_hit_items": zero_hit_items,
        "incremental_stats": {"refreshed": refreshed, "carried": carried},
        "disclaimer": (
            "以下法条片段来自 LexML / STF / STJ 开放法源索引，仅供协查参考，不构成正式法律意见。"
            f"匹配度低于 {match_threshold} 分的条目须标注「需法务复核」。"
        ),
    }


def retrieve_for_checklist(
    sections: list[dict[str, Any]],
    top_k: int = 3,
    *,
    match_threshold: int = 70,
    expansion_context: str = "",
) -> dict[str, Any]:
    from app.services.retrieval_expansion import retrieve_item_with_expansion

    enriched_sections: list[dict[str, Any]] = []
    total_hits = 0
    zero_hit_items: list[str] = []
    expanded_count = 0

    for section in sections:
        items_out: list[dict[str, Any]] = []
        for item in section.get("items", []):
            hits, rmeta = retrieve_item_with_expansion(
                item_code=item["code"],
                dimension=section["dimension_id"],
                title=item["title"],
                description=item["description"],
                match_threshold=match_threshold,
                expansion_context=expansion_context,
                top_k=top_k,
            )
            if rmeta.get("expanded"):
                expanded_count += 1
            if not hits:
                zero_hit_items.append(item["code"])
            total_hits += len(hits)
            status = "ok" if hits else "no_match"
            if rmeta.get("expanded") and rmeta.get("best_score", 0) < match_threshold:
                status = "expanded_below_threshold"
            items_out.append(
                {
                    **item,
                    "legal_hits": hits,
                    "retrieval_status": status,
                    "retrieval_meta": rmeta,
                }
            )
        enriched_sections.append({**section, "items": items_out})

    return {
        "sections": enriched_sections,
        "total_hits": total_hits,
        "zero_hit_items": zero_hit_items,
        "retrieval_meta": {
            "match_threshold": match_threshold,
            "expanded_item_count": expanded_count,
            "expansion_enabled": bool(expansion_context.strip()),
        },
        "disclaimer": (
            "以下法条片段来自 LexML / STF / STJ 开放法源索引，仅供协查参考，不构成正式法律意见。"
            f"匹配度低于 {match_threshold} 分的条目须标注「需法务复核」。"
        ),
    }
