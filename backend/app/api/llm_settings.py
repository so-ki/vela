"""LLM settings API — per-user provider / model / test connection."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.services.llm_client import (
    LlmSecurityError,
    clear_user_api_key,
    get_bound_user_api_key,
    test_llm_connection,
)
from app.services.user_preference_service import (
    get_llm_settings_response,
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
    clear_api_key: bool = False
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
    if get_settings().is_production:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="生产受控试点不接收 LLM 设置或 API Key",
        )
    updates: dict[str, Any] = body.model_dump(exclude_unset=True)
    if body.task_models is not None:
        updates["task_models"] = body.task_models.model_dump()
    try:
        return update_user_llm_settings(current_user.id, updates)
    except LlmSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/settings/api-key")
def delete_llm_api_key(current_user: User = Depends(get_current_user)):
    clear_user_api_key(current_user.id)
    return get_llm_settings_response(current_user.id)


@router.post("/test")
def test_llm(body: LlmTestRequest, current_user: User = Depends(get_current_user)):
    if get_settings().is_production:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="生产受控试点已禁用第三方 LLM 外发",
        )
    api_key = (body.api_key or "").strip()
    if not api_key:
        try:
            api_key = get_bound_user_api_key(
                current_user.id,
                provider=body.provider,
                base_url=body.base_url,
            ) or ""
        except LlmSecurityError as exc:
            return {"ok": False, "error": str(exc)}
    if not api_key:
        return {"ok": False, "error": "请提供短期 API Key 或先在当前进程中保存"}
    try:
        result = test_llm_connection(
            provider=body.provider,
            base_url=body.base_url,
            api_key=api_key,
            model=body.model,
        )
        return result
    except LlmSecurityError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "LLM 连接失败；未跟随重定向，也未回显凭据"}
