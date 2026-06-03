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
