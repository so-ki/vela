from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.core.chroma_client import COLLECTION_NAME, _chroma_available

CORPUS_PATH = Path(__file__).resolve().parents[1] / "data" / "brazil_legal_corpus.json"
INDEX_FLAG = Path(__file__).resolve().parents[2] / "data" / "legal_index.json"


def load_corpus() -> dict[str, Any]:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_index_flag(payload: dict[str, Any]) -> None:
    INDEX_FLAG.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FLAG, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_index_flag() -> Optional[dict[str, Any]]:
    if not INDEX_FLAG.exists():
        return None
    with open(INDEX_FLAG, encoding="utf-8") as f:
        return json.load(f)


def ingest_corpus(force: bool = False) -> dict[str, Any]:
    corpus = load_corpus()
    sources = corpus["sources"]
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
                ids, documents, metadatas = [], [], []
                for doc in sources:
                    ids.append(doc["id"])
                    combined = f"{doc['title_pt']}\n{doc['text_pt']}\n{doc.get('text_zh', '')}"
                    documents.append(combined)
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
        "chroma_count": chroma_count,
        "sources_breakdown": breakdown,
    }
    _save_index_flag(payload)

    return {
        "status": "ok",
        "mode": mode,
        "message": f"已索引 {len(sources)} 条法源片段（模式: {mode}）",
        "indexed": len(sources),
        "collection": COLLECTION_NAME,
        "sources_breakdown": breakdown,
    }


def _doc_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": doc["source"],
        "urn": doc["urn"],
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
        "document_count": len(corpus.get("sources", [])),
        "collection": COLLECTION_NAME,
        "mode": flag.get("mode", "keyword") if flag else "pending",
    }
    if flag:
        base["chroma_count"] = flag.get("chroma_count", 0)
    return base
