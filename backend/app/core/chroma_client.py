"""Chroma vector store client — populated in Step 3 (法源 RAG)."""

from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

COLLECTION_NAME = "brazil_legal_sources"
_chroma_available = False
CHROMA_DISABLED_MESSAGE = (
    "Chroma 向量后端未随本发布提供；当前使用确定性关键词检索。"
)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    _chroma_available = True
except ImportError:
    chromadb = None  # type: ignore[assignment,misc]
    ChromaSettings = None  # type: ignore[assignment,misc]


@lru_cache
def get_chroma_client():
    if not _chroma_available:
        raise RuntimeError(CHROMA_DISABLED_MESSAGE)
    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_legal_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Brazil legal sources (LexML, STF, STJ) — Step 3"},
    )


def chroma_health() -> dict:
    if not _chroma_available:
        return {
            "status": "disabled",
            "message": CHROMA_DISABLED_MESSAGE,
            "collection": COLLECTION_NAME,
            "document_count": 0,
        }
    try:
        collection = get_legal_collection()
        return {"status": "ok", "collection": COLLECTION_NAME, "document_count": collection.count()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
