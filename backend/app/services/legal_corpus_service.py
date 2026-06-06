from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, status

from app.services.legal_ingest import CORPUS_PATH, ingest_corpus, load_corpus
from app.services.rules_registry import load_rules

VALID_SOURCES = {"lexml", "stf", "stj", "jusbrasil"}
VALID_LEVELS = {"federal", "state", "municipal", "case_law"}
VALID_DIMENSIONS = {"labor", "foreign_investment", "tax", "industry_access"}


def _save_corpus(corpus: dict[str, Any]) -> None:
    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _bump_version(version: str) -> str:
    parts = str(version).split(".")
    if len(parts) >= 2 and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    return version


def _slug_id(prefix: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"{prefix}-{slug or 'entry'}"


def _validate_document(doc: dict[str, Any], *, existing_ids: set[str], doc_id: Optional[str] = None) -> dict[str, Any]:
    required = [
        "id",
        "source",
        "urn",
        "url",
        "title_pt",
        "title_zh",
        "dimension",
        "level",
        "validity",
        "published_at",
        "text_pt",
        "text_zh",
    ]
    missing = [k for k in required if not str(doc.get(k, "")).strip()]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"缺少必填字段: {', '.join(missing)}",
        )

    if doc["source"] not in VALID_SOURCES:
        raise HTTPException(status_code=422, detail=f"source 须为: {', '.join(sorted(VALID_SOURCES))}")
    if doc["dimension"] not in VALID_DIMENSIONS:
        raise HTTPException(status_code=422, detail=f"dimension 须为: {', '.join(sorted(VALID_DIMENSIONS))}")
    if doc["level"] not in VALID_LEVELS:
        raise HTTPException(status_code=422, detail=f"level 须为: {', '.join(sorted(VALID_LEVELS))}")

    entry_id = doc["id"].strip()
    if doc_id and entry_id != doc_id:
        raise HTTPException(status_code=422, detail="条目 id 不可修改")
    if entry_id in existing_ids and entry_id != doc_id:
        raise HTTPException(status_code=409, detail=f"条目 id 已存在: {entry_id}")

    tags = doc.get("tags") or []
    codes = doc.get("checklist_codes") or []
    if not isinstance(tags, list) or not isinstance(codes, list):
        raise HTTPException(status_code=422, detail="tags 与 checklist_codes 须为数组")

    return {
        "id": entry_id,
        "source": doc["source"].strip(),
        "urn": doc["urn"].strip(),
        "url": doc["url"].strip(),
        "title_pt": doc["title_pt"].strip(),
        "title_zh": doc["title_zh"].strip(),
        "dimension": doc["dimension"].strip(),
        "level": doc["level"].strip(),
        "validity": doc["validity"].strip(),
        "published_at": doc["published_at"].strip(),
        "tags": [str(t).strip() for t in tags if str(t).strip()],
        "checklist_codes": [str(c).strip() for c in codes if str(c).strip()],
        "text_pt": doc["text_pt"].strip(),
        "text_zh": doc["text_zh"].strip(),
    }


def get_corpus_meta() -> dict[str, Any]:
    corpus = load_corpus()
    rules = load_rules()

    dimensions = [
        {"id": d["id"], "name": d["name"]}
        for d in rules.get("dimensions", {}).values()
    ] or [
        {"id": "labor", "name": "劳工用工"},
        {"id": "foreign_investment", "name": "外资准入"},
        {"id": "tax", "name": "税制"},
        {"id": "industry_access", "name": "行业准入"},
    ]

    checklist_codes = [
        {"id": item["id"], "title": item["title"], "dimension": item["dimension"]}
        for item in rules.get("checklist_items", [])
    ]

    return {
        "version": corpus.get("version", "1.0"),
        "jurisdiction": corpus.get("jurisdiction", "brazil"),
        "document_count": len(corpus.get("sources", [])),
        "sources": sorted(VALID_SOURCES),
        "levels": sorted(VALID_LEVELS),
        "dimensions": dimensions,
        "checklist_codes": checklist_codes,
    }


def list_corpus_sources(
    *,
    q: Optional[str] = None,
    dimension: Optional[str] = None,
    source: Optional[str] = None,
) -> dict[str, Any]:
    corpus = load_corpus()
    items = list(corpus.get("sources", []))

    if dimension:
        items = [i for i in items if i.get("dimension") == dimension]
    if source:
        items = [i for i in items if i.get("source") == source]
    if q:
        needle = q.lower()
        items = [
            i
            for i in items
            if needle in (i.get("title_zh") or "").lower()
            or needle in (i.get("title_pt") or "").lower()
            or needle in (i.get("id") or "").lower()
            or any(needle in c.lower() for c in i.get("checklist_codes", []))
        ]

    return {
        "version": corpus.get("version", "1.0"),
        "total": len(items),
        "items": items,
    }


def get_corpus_source(doc_id: str) -> dict[str, Any]:
    corpus = load_corpus()
    for item in corpus.get("sources", []):
        if item.get("id") == doc_id:
            return item
    raise HTTPException(status_code=404, detail="法源条目不存在")


def create_corpus_source(payload: dict[str, Any]) -> dict[str, Any]:
    corpus = load_corpus()
    sources: list[dict[str, Any]] = list(corpus.get("sources", []))
    existing_ids = {s["id"] for s in sources}

    doc = dict(payload)
    if not doc.get("id"):
        doc["id"] = _slug_id(doc.get("source", "lexml"), doc.get("title_pt", "entry"))
        base = doc["id"]
        n = 2
        while doc["id"] in existing_ids:
            doc["id"] = f"{base}-{n}"
            n += 1

    validated = _validate_document(doc, existing_ids=existing_ids)
    sources.append(validated)
    corpus["sources"] = sources
    corpus["version"] = _bump_version(corpus.get("version", "1.0"))
    _save_corpus(corpus)

    return {"item": validated, "version": corpus["version"], "document_count": len(sources)}


def update_corpus_source(doc_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    corpus = load_corpus()
    sources: list[dict[str, Any]] = list(corpus.get("sources", []))
    existing_ids = {s["id"] for s in sources}

    idx = next((i for i, s in enumerate(sources) if s.get("id") == doc_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="法源条目不存在")

    merged = {**sources[idx], **payload, "id": doc_id}
    validated = _validate_document(merged, existing_ids=existing_ids, doc_id=doc_id)
    sources[idx] = validated
    corpus["sources"] = sources
    corpus["version"] = _bump_version(corpus.get("version", "1.0"))
    _save_corpus(corpus)

    return {"item": validated, "version": corpus["version"], "document_count": len(sources)}


def delete_corpus_source(doc_id: str) -> dict[str, Any]:
    corpus = load_corpus()
    sources: list[dict[str, Any]] = list(corpus.get("sources", []))
    new_sources = [s for s in sources if s.get("id") != doc_id]
    if len(new_sources) == len(sources):
        raise HTTPException(status_code=404, detail="法源条目不存在")

    corpus["sources"] = new_sources
    corpus["version"] = _bump_version(corpus.get("version", "1.0"))
    _save_corpus(corpus)

    return {"deleted_id": doc_id, "version": corpus["version"], "document_count": len(new_sources)}


def rebuild_corpus_index(*, force: bool = True) -> dict[str, Any]:
    result = ingest_corpus(force=force)
    return {
        "index": result,
        "version": load_corpus().get("version", "1.0"),
    }
