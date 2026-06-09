"""Brazil legal connector: corpus + LexML live fallback with citation tiers."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote

from app.services.brazil_official_portals import build_portal_hits
from app.services.legal_ingest import load_corpus
from app.services.legal_rag import retrieve_for_checklist_item, SOURCE_LABELS
from app.services.lexml_fetch_service import fetch_lexml_by_urn

CITATION_TIERS = {
    "corpus_verified": "语料库已索引（可 grounding）",
    "lexml_live": "LexML 实时拉取官方文本",
    "portal_link": "官方法源门户（LexML · Planalto · STF · gov.br，须律师核对）",
}


def _tokenize(text: str) -> set[str]:
    parts = re.split(r"[\s,、/\.]+", (text or "").lower())
    return {p for p in parts if len(p) >= 2}


def _state_boost(doc: dict[str, Any], state: Optional[str]) -> float:
    if not state:
        return 0.0
    st = state.lower().replace(" ", "_")
    tags = " ".join(doc.get("tags") or []).lower()
    level = (doc.get("level") or "").lower()
    if st in tags or st.replace("_", " ") in tags:
        return 12.0
    if level == "state" and st.startswith("sao"):
        return 8.0
    if level == "federal":
        return 4.0
    return 0.0


def _format_live_hit(
    doc: dict[str, Any],
    *,
    text_pt: str,
    match_score: float,
    citation_tier: str,
    item_code: str,
) -> dict[str, Any]:
    return {
        "id": doc.get("id") or f"live-{hash(doc.get('urn', ''))}",
        "source": doc.get("source", "lexml"),
        "source_label": SOURCE_LABELS.get(doc.get("source", "lexml"), "LexML Brasil"),
        "urn": doc.get("urn", ""),
        "url": doc.get("url", ""),
        "title_pt": doc.get("title_pt", ""),
        "title_zh": doc.get("title_zh", ""),
        "excerpt_pt": (text_pt or "")[:600],
        "excerpt_zh": doc.get("text_zh", ""),
        "validity": doc.get("validity", "vigente"),
        "level": doc.get("level", "federal"),
        "match_score": round(min(100.0, match_score), 1),
        "requires_review": citation_tier != "corpus_verified",
        "citation_tier": citation_tier,
        "citation_tier_label": CITATION_TIERS.get(citation_tier, citation_tier),
        "checklist_code": item_code,
        "connector": "brazil_legal",
    }


def _lexml_portal_hit(query: str, dimension: str, item_code: str) -> dict[str, Any]:
    """Legacy single-hit wrapper; prefer build_portal_hits."""
    hits = build_portal_hits(query, dimension, item_code, limit=1)
    if hits:
        return hits[0]
    q = quote(query[:200])
    url = f"https://www.lexml.gov.br/busca/search?keyword={q}"
    return {
        "id": f"lexml-portal-{item_code}",
        "source": "lexml",
        "source_label": "LexML Brasil · 检索",
        "urn": "",
        "url": url,
        "title_pt": f"LexML 检索：{query[:80]}",
        "title_zh": f"LexML 在线检索（{dimension}）",
        "excerpt_pt": "未在本地语料命中时，请通过 LexML 官方检索核对最新立法文本。",
        "excerpt_zh": "Connector 降级：提供官方检索入口，须法务人工确认具体法条。",
        "match_score": 35.0,
        "requires_review": True,
        "citation_tier": "portal_link",
        "citation_tier_label": CITATION_TIERS["portal_link"],
        "checklist_code": item_code,
        "connector": "brazil_legal",
    }


def connector_retrieve_for_item(
    *,
    item_code: str,
    dimension: str,
    title: str,
    description: str,
    state: Optional[str] = None,
    match_threshold: int = 70,
    top_k: int = 3,
    allow_live: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Corpus first → relaxed local → LexML URN live → portal link."""
    query = f"{title} {description} {dimension} {state or ''}"
    meta: dict[str, Any] = {"passes": [], "connector": "brazil_legal"}

    hits = retrieve_for_checklist_item(
        item_code=item_code,
        dimension=dimension,
        title=title,
        description=description,
        top_k=top_k,
        match_threshold=match_threshold,
    )
    for h in hits:
        h["citation_tier"] = "corpus_verified"
        h["citation_tier_label"] = CITATION_TIERS["corpus_verified"]
        h["connector"] = "brazil_legal"
    meta["passes"].append({"phase": "corpus_strict", "count": len(hits)})

    best = max((float(h.get("match_score") or 0) for h in hits), default=0.0)
    if hits and best >= match_threshold - 5:
        meta["best_score"] = best
        meta["live_used"] = False
        return hits[:top_k], meta

    if not allow_live:
        meta["best_score"] = best
        return hits[:top_k], meta

    relaxed = retrieve_for_checklist_item(
        item_code=item_code,
        dimension=dimension,
        title=title,
        description=description,
        top_k=top_k + 2,
        match_threshold=match_threshold,
        min_keyword_score=15.0,
    )
    corpus = load_corpus()
    by_id = {d["id"]: d for d in corpus.get("sources", []) if d.get("id")}
    query_tokens = _tokenize(query)
    enriched: list[dict[str, Any]] = []
    seen: set[str] = set()

    for h in relaxed:
        doc = by_id.get(h.get("id", ""), h)
        boost = _state_boost(doc, state) + len(query_tokens & _tokenize(doc.get("text_pt", "") + doc.get("title_pt", ""))) * 3
        score = float(h.get("match_score") or 0) + boost
        hid = h.get("id", "")
        if hid in seen:
            continue
        seen.add(hid)
        tier = "corpus_verified"
        text_pt = doc.get("text_pt") or h.get("excerpt_pt") or ""
        if score < match_threshold and doc.get("urn") and doc.get("source") == "lexml":
            fetched = fetch_lexml_by_urn(doc["urn"], timeout=15.0)
            if fetched.get("status") == "ok":
                text_pt = fetched.get("text_pt") or text_pt
                tier = "lexml_live"
                score = max(score, match_threshold - 8)
        enriched.append(_format_live_hit(doc, text_pt=text_pt, match_score=score, citation_tier=tier, item_code=item_code))

    enriched.sort(key=lambda x: float(x.get("match_score") or 0), reverse=True)
    meta["passes"].append({"phase": "relaxed_live", "count": len(enriched)})

    if enriched:
        meta["best_score"] = float(enriched[0].get("match_score") or 0)
        meta["live_used"] = any(e.get("citation_tier") == "lexml_live" for e in enriched)
        return enriched[:top_k], meta

    portal = build_portal_hits(query, dimension, item_code, limit=top_k)
    meta["passes"].append({"phase": "portal_fallback", "count": len(portal)})
    meta["best_score"] = float(portal[0].get("match_score") or 35.0) if portal else 35.0
    meta["live_used"] = True
    meta["official_portals"] = [h.get("source") for h in portal]
    return portal[:top_k], meta


def connector_retrieve_for_sections(
    sections: list[dict[str, Any]],
    *,
    state: Optional[str] = None,
    match_threshold: int = 70,
    top_k: int = 3,
) -> dict[str, Any]:
    enriched_sections: list[dict[str, Any]] = []
    total_hits = 0
    zero_hit_items: list[str] = []
    connector_meta: list[dict[str, Any]] = []

    for section in sections:
        items_out: list[dict[str, Any]] = []
        for item in section.get("items", []):
            hits, meta = connector_retrieve_for_item(
                item_code=item.get("code", ""),
                dimension=section.get("dimension_id") or item.get("dimension", ""),
                title=item.get("title", ""),
                description=item.get("description", ""),
                state=state,
                match_threshold=match_threshold,
                top_k=top_k,
            )
            connector_meta.append({"code": item.get("code"), **meta})
            if not hits or all(h.get("citation_tier") == "portal_link" for h in hits):
                zero_hit_items.append(item.get("code", ""))
            total_hits += len(hits)
            items_out.append({**item, "legal_hits": hits})
        enriched_sections.append({**section, "items": items_out})

    return {
        "sections": enriched_sections,
        "total_hits": total_hits,
        "zero_hit_items": [c for c in zero_hit_items if c],
        "connector_runs": connector_meta,
        "disclaimer": "官方法源链：语料索引 → LexML URN 实时 → Planalto/STF/gov.br 门户；portal_link 须法务核对。",
    }
