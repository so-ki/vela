from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_legal_user, get_current_user
from app.models.user import User
from app.schemas.legal import (
    LegalCorpusDeleteResponse,
    LegalCorpusDocument,
    LegalCorpusDocumentCreate,
    LegalCorpusDocumentUpdate,
    LegalCorpusListResponse,
    LegalCorpusMetaResponse,
    LegalCorpusMutationResponse,
    LegalCorpusReindexResponse,
    LegalIndexResponse,
    LegalMonitorResponse,
    LegalMonitorScanResponse,
    LegalStatusResponse,
)
from app.services.audit import write_audit_log
from app.services.legal_corpus_service import (
    create_corpus_source,
    delete_corpus_source,
    get_corpus_meta,
    get_corpus_source,
    list_corpus_sources,
    rebuild_corpus_index,
    update_corpus_source,
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


@router.get("/corpus/meta", response_model=LegalCorpusMetaResponse)
def legal_corpus_meta(_: User = Depends(get_current_legal_user)):
    return LegalCorpusMetaResponse(**get_corpus_meta())


@router.get("/corpus", response_model=LegalCorpusListResponse)
def legal_corpus_list(
    q: Optional[str] = Query(default=None, description="搜索标题、id 或 checklist_code"),
    dimension: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    _: User = Depends(get_current_legal_user),
):
    result = list_corpus_sources(q=q, dimension=dimension, source=source)
    return LegalCorpusListResponse(**result)


@router.get("/corpus/{doc_id}", response_model=LegalCorpusDocument)
def legal_corpus_get(doc_id: str, _: User = Depends(get_current_legal_user)):
    return LegalCorpusDocument(**get_corpus_source(doc_id))


@router.post("/corpus", response_model=LegalCorpusMutationResponse)
def legal_corpus_create(
    payload: LegalCorpusDocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = create_corpus_source(payload.model_dump(exclude_none=True))
    write_audit_log(
        db,
        user=user,
        action="corpus.create",
        resource_type="legal_corpus",
        resource_id=result["item"]["id"],
        detail=f"version={result['version']}",
    )
    return LegalCorpusMutationResponse(
        item=LegalCorpusDocument(**result["item"]),
        version=result["version"],
        document_count=result["document_count"],
    )


@router.put("/corpus/{doc_id}", response_model=LegalCorpusMutationResponse)
def legal_corpus_update(
    doc_id: str,
    payload: LegalCorpusDocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = update_corpus_source(doc_id, payload.model_dump(exclude_none=True))
    write_audit_log(
        db,
        user=user,
        action="corpus.update",
        resource_type="legal_corpus",
        resource_id=doc_id,
        detail=f"version={result['version']}",
    )
    return LegalCorpusMutationResponse(
        item=LegalCorpusDocument(**result["item"]),
        version=result["version"],
        document_count=result["document_count"],
    )


@router.delete("/corpus/{doc_id}", response_model=LegalCorpusDeleteResponse)
def legal_corpus_delete(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = delete_corpus_source(doc_id)
    write_audit_log(
        db,
        user=user,
        action="corpus.delete",
        resource_type="legal_corpus",
        resource_id=doc_id,
        detail=f"version={result['version']}",
    )
    return LegalCorpusDeleteResponse(**result)


@router.post("/corpus/reindex", response_model=LegalCorpusReindexResponse)
def legal_corpus_reindex(
    force: bool = Query(default=True, description="强制重建索引"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = rebuild_corpus_index(force=force)
    write_audit_log(
        db,
        user=user,
        action="corpus.reindex",
        resource_type="legal_corpus",
        detail=result["index"].get("message"),
    )
    scan_regulatory_updates(force_reindex=False)
    return LegalCorpusReindexResponse(
        version=result["version"],
        index=LegalIndexResponse(
            status=result["index"]["status"],
            message=result["index"].get("message", ""),
            indexed=result["index"].get("indexed", 0),
            collection=result["index"].get("collection"),
            sources_breakdown=result["index"].get("sources_breakdown"),
        ),
    )
