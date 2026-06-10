"""LLM settings API — per-user provider / model / test connection."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.models.user import User
from app.services.llm_client import test_llm_connection
from app.services.user_preference_service import (
    get_llm_settings_response,
    get_user_llm_settings,
    update_user_llm_settings,
)

router = APIRouter(prefix="/llm", tags=["llm"])


class LlmTaskModels(BaseModel):
    extract: str = ""
    issue_id: str = ""
    gap: str = ""
    red_team: str = ""
    polish: str = ""


class LlmSettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    task_models: Optional[LlmTaskModels] = None


class LlmTestRequest(BaseModel):
    provider: str = "qwen"
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@router.get("/settings")
def get_llm_settings(current_user: User = Depends(get_current_user)):
    return get_llm_settings_response(current_user.id)


@router.patch("/settings")
def patch_llm_settings(
    body: LlmSettingsPatch,
    current_user: User = Depends(get_current_user),
):
    updates: dict[str, Any] = body.model_dump(exclude_unset=True)
    if body.task_models is not None:
        updates["task_models"] = body.task_models.model_dump()
    return update_user_llm_settings(current_user.id, updates)


@router.post("/test")
def test_llm(body: LlmTestRequest, current_user: User = Depends(get_current_user)):
    api_key = (body.api_key or "").strip()
    if not api_key:
        saved = get_user_llm_settings(current_user.id)
        api_key = (saved.get("api_key") or "").strip()
    if not api_key:
        return {"ok": False, "error": "请提供 API Key 或在设置中保存后再测试"}
    try:
        result = test_llm_connection(
            provider=body.provider,
            base_url=body.base_url,
            api_key=api_key,
            model=body.model,
        )
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
