from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.chroma_client import chroma_health
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import HealthResponse, SystemStatusResponse
from app.services.llm_client import llm_status

router = APIRouter(tags=["系统"])


class LlmStatusResponse(BaseModel):
    available: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    message: str


@router.get("/health", response_model=HealthResponse)
def health():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version="0.1.0",
        environment=settings.app_env,
    )


@router.get("/status", response_model=SystemStatusResponse)
def system_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    return SystemStatusResponse(database=db_status, chroma=chroma_health())


@router.get("/llm/status", response_model=LlmStatusResponse)
def llm_service_status(_: User = Depends(get_current_user)):
    return LlmStatusResponse(**llm_status())


class ExportConfigResponse(BaseModel):
    template: str
    docx_label: str
    org_name: str


@router.get("/export/config", response_model=ExportConfigResponse)
def export_config():
    settings = get_settings()
    label = "法律研究意见书" if settings.export_template == "law_school" else "协查底稿"
    return ExportConfigResponse(
        template=settings.export_template,
        docx_label=label,
        org_name=settings.export_org_name,
    )


class PackSummary(BaseModel):
    pack_id: str
    manifest_version: Optional[str] = None
    display_name: Optional[str] = None
    certification_status: Optional[str] = None
    jurisdiction: Optional[dict] = None
    supported_issues: list[str] = []
    exclusions: list[str] = []
    rule_card_count: int = 0


@router.get("/packs", response_model=list[PackSummary])
def list_packs(_: User = Depends(get_current_user)):
    """已安装能力包清单（manifest v0.1-draft 投影）。"""
    from app.packs.loader import list_installed_packs, load_rule_cards

    out: list[PackSummary] = []
    for manifest in list_installed_packs():
        pack_id = str(manifest.get("pack_id") or "")
        if not pack_id:
            continue
        out.append(
            PackSummary(
                pack_id=pack_id,
                manifest_version=manifest.get("manifest_version"),
                display_name=manifest.get("display_name"),
                certification_status=manifest.get("certification_status"),
                jurisdiction=manifest.get("jurisdiction"),
                supported_issues=list(manifest.get("supported_issues") or []),
                exclusions=list(manifest.get("exclusions") or []),
                rule_card_count=len(load_rule_cards(pack_id)),
            )
        )
    return out
