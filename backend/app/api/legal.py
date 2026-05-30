from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.legal import LegalIndexResponse, LegalStatusResponse
from app.services.legal_ingest import get_index_status, ingest_corpus

router = APIRouter(prefix="/legal", tags=["法源 RAG"])


@router.get("/status", response_model=LegalStatusResponse)
def legal_status(_: User = Depends(get_current_user)):
    idx = get_index_status()
    from app.core.chroma_client import COLLECTION_NAME, _chroma_available

    return LegalStatusResponse(
        chroma_installed=_chroma_available,
        document_count=idx.get("document_count", 0),
        collection=COLLECTION_NAME,
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
