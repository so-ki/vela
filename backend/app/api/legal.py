from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.legal import (
    LegalIndexResponse,
    LegalMonitorResponse,
    LegalMonitorScanResponse,
    LegalStatusResponse,
)
from app.services.legal_ingest import get_index_status, ingest_corpus, load_corpus
from app.services.legal_monitor import get_monitor_status, scan_regulatory_updates

router = APIRouter(prefix="/legal", tags=["法源 RAG"])


@router.get("/status", response_model=LegalStatusResponse)
def legal_status(_: User = Depends(get_current_user)):
    idx = get_index_status()
    from app.core.chroma_client import COLLECTION_NAME, _chroma_available

    corpus = load_corpus()
    breakdown: dict[str, int] = {}
    for s in corpus.get("sources", []):
        src = s.get("source", "unknown")
        breakdown[src] = breakdown.get(src, 0) + 1

    return LegalStatusResponse(
        chroma_installed=_chroma_available,
        document_count=idx.get("document_count", 0),
        collection=COLLECTION_NAME,
        mode=idx.get("mode", "pending"),
        corpus_version=corpus.get("version", "1.0"),
        sources_breakdown=breakdown,
    )


@router.post("/index", response_model=LegalIndexResponse)
def build_index(
    force: bool = Query(default=False, description="强制重建索引"),
    _: User = Depends(get_current_user),
):
    result = ingest_corpus(force=force)
    return LegalIndexResponse(
        status=result["status"],
        message=result.get("message", ""),
        indexed=result.get("indexed", 0),
        collection=result.get("collection"),
        sources_breakdown=result.get("sources_breakdown"),
    )


@router.get("/monitor", response_model=LegalMonitorResponse)
def legal_monitor_status(_: User = Depends(get_current_user)):
    return LegalMonitorResponse(**get_monitor_status())


@router.post("/monitor/scan", response_model=LegalMonitorScanResponse)
def legal_monitor_scan(
    force_reindex: bool = Query(default=False, description="扫描同时强制重建索引"),
    _: User = Depends(get_current_user),
):
    result = scan_regulatory_updates(force_reindex=force_reindex)
    return LegalMonitorScanResponse(
        scanned_at=result["scanned_at"],
        corpus_fingerprint=result["corpus_fingerprint"],
        new_alerts=result["new_alerts"],
        alerts=result["alerts"],
        index=LegalIndexResponse(
            status=result["index"]["status"],
            message=result["index"].get("message", ""),
            indexed=result["index"].get("indexed", 0),
            collection=result["index"].get("collection"),
            sources_breakdown=result["index"].get("sources_breakdown"),
        ),
    )
