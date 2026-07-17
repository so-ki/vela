from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.core.chroma_client import COLLECTION_NAME, _chroma_available
from app.core.secure_json_store import atomic_write_json

CORPUS_PATH = Path(__file__).resolve().parents[1] / "data" / "brazil_legal_corpus.json"
INDEX_FLAG = Path(__file__).resolve().parents[2] / "data" / "legal_index.json"
RETRIEVABLE_REVIEW_STATUSES = frozenset({"expert_verified", "provisional"})


def load_corpus(corpus_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(corpus_path) if corpus_path is not None else CORPUS_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def corpus_review_status(corpus: dict[str, Any], doc: dict[str, Any]) -> str:
    """Resolve explicit evidence status; undeclared corpora fail closed."""

    explicit = str(doc.get("review_status") or "").strip().lower()
    if explicit:
        return explicit
    declared_default = str(corpus.get("default_review_status") or "").strip().lower()
    if declared_default in RETRIEVABLE_REVIEW_STATUSES:
        return declared_default
    return "pending"


def retrievable_corpus_sources(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        doc
        for doc in corpus.get("sources", [])
        if corpus_review_status(corpus, doc) in RETRIEVABLE_REVIEW_STATUSES
    ]


def _save_index_flag(payload: dict[str, Any]) -> None:
    atomic_write_json(INDEX_FLAG, payload)


def _load_index_flag() -> Optional[dict[str, Any]]:
    if not INDEX_FLAG.exists():
        return None
    with open(INDEX_FLAG, encoding="utf-8") as f:
        return json.load(f)


def ingest_corpus(
    force: bool = False,
    *,
    corpus_path: Path | str | None = None,
) -> dict[str, Any]:
    corpus = load_corpus(corpus_path)
    sources = retrievable_corpus_sources(corpus)
    breakdown = _count_by_source(sources)

    flag = _load_index_flag()
    if flag and not force and flag.get("document_count", 0) > 0:
        return {
            "status": "ok",
            "mode": flag.get("mode", "keyword"),
            "message": "索引已存在，跳过重复导入（force=true 可重建）",
            "indexed": flag["document_count"],
            "collection": COLLECTION_NAME,
            "sources_breakdown": breakdown,
        }

    mode = "keyword"
    chroma_count = 0

    if _chroma_available:
        try:
            from app.core.chroma_client import get_chroma_client, get_legal_collection

            collection = get_legal_collection()
            if force and collection.count() > 0:
                client = get_chroma_client()
                client.delete_collection(COLLECTION_NAME)
                collection = get_legal_collection()

            if force or collection.count() == 0:
                from app.services.corpus_text_cleaner import text_for_retrieval

                ids, documents, metadatas = [], [], []
                for doc in sources:
                    ids.append(doc["id"])
                    documents.append(text_for_retrieval(doc))
                    metadatas.append(_doc_metadata(doc))
                collection.add(ids=ids, documents=documents, metadatas=metadatas)

            chroma_count = get_legal_collection().count()
            if chroma_count > 0:
                mode = "chroma"
        except Exception as exc:
            mode = "keyword"
            chroma_count = 0
            breakdown["chroma_error"] = str(exc)[:120]

    payload = {
        "mode": mode,
        "document_count": len(sources),
        "excluded_document_count": len(corpus.get("sources", [])) - len(sources),
        "chroma_count": chroma_count,
        "sources_breakdown": breakdown,
    }
    _save_index_flag(payload)

    return {
        "status": "ok",
        "mode": mode,
        "message": (
            f"已索引 {len(sources)} 条可检索法源片段（模式: {mode}）；"
            f"隔离/待审 {len(corpus.get('sources', [])) - len(sources)} 条"
        ),
        "indexed": len(sources),
        "collection": COLLECTION_NAME,
        "sources_breakdown": breakdown,
    }


def _doc_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": doc["source"],
        "urn": doc.get("urn") or f"urn:vela:doc:{doc['id']}",
        "url": doc["url"],
        "title_pt": doc["title_pt"],
        "title_zh": doc.get("title_zh", ""),
        "dimension": doc["dimension"],
        "level": doc["level"],
        "validity": doc["validity"],
        "published_at": doc["published_at"],
        "tags": ",".join(doc.get("tags", [])),
        "checklist_codes": ",".join(doc.get("checklist_codes", [])),
    }


def _count_by_source(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in sources:
        src = s.get("source", "unknown")
        counts[src] = counts.get(src, 0) + 1
    return counts


def get_index_status() -> dict[str, Any]:
    flag = _load_index_flag()
    corpus = load_corpus()
    base = {
        "installed": _chroma_available,
        "document_count": len(retrievable_corpus_sources(corpus)),
        "excluded_document_count": (
            len(corpus.get("sources", [])) - len(retrievable_corpus_sources(corpus))
        ),
        "collection": COLLECTION_NAME,
        "mode": flag.get("mode", "keyword") if flag else "pending",
    }
    if flag:
        base["chroma_count"] = flag.get("chroma_count", 0)
    return base
