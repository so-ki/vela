"""Per-user preference loop: learn from review/playbook edits, apply to later runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.core.secure_json_store import atomic_write_json, synchronized_json_store

PREFS_DIR = Path(__file__).resolve().parents[2] / "data" / "user_preferences"
MAX_EVENTS = 300


def _prefs_path(user_id: int) -> Path:
    return PREFS_DIR / f"user_{user_id}.json"


def _default_prefs(user_id: int) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "match_threshold": None,
        "retrieval_top_k": None,
        "code_adjustments": {},
        "contract_rule_adjustments": {},
        "reject_counts": {},
        "approve_counts": {},
        "preferred_dimensions": [],
        "llm_settings": {
            "enabled": None,
            "provider": "",
            "base_url": "",
            "default_model": "",
            "task_models": {
                "extract": "",
                "issue_id": "",
                "gap": "",
                "red_team": "",
                "polish": "",
            },
        },
        "events": [],
        "updated_at": None,
    }


@synchronized_json_store
def load_user_preferences(user_id: int) -> dict[str, Any]:
    path = _prefs_path(user_id)
    if not path.exists():
        return _default_prefs(user_id)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # One-way scrub for files written by versions that persisted API keys.
    # Legacy plaintext credentials are discarded, never imported into memory.
    llm_settings = dict(data.get("llm_settings") or {})
    had_legacy_secret = "api_key" in llm_settings
    llm_settings.pop("api_key", None)
    data["llm_settings"] = {
        **_default_prefs(user_id)["llm_settings"],
        **llm_settings,
    }
    merged = {**_default_prefs(user_id), **data}
    if had_legacy_secret:
        save_user_preferences(user_id, merged)
    return merged


@synchronized_json_store
def save_user_preferences(user_id: int, prefs: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    prefs["user_id"] = user_id
    prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    llm_settings = dict(prefs.get("llm_settings") or {})
    llm_settings.pop("api_key", None)
    prefs["llm_settings"] = llm_settings
    path = _prefs_path(user_id)
    atomic_write_json(path, prefs)
    return prefs


@synchronized_json_store
def record_review_decision(
    user_id: int,
    *,
    code: str,
    decision: str,
    comment: Optional[str] = None,
    match_score: float = 0.0,
    tier: str = "",
) -> dict[str, Any]:
    prefs = load_user_preferences(user_id)
    event = {
        "type": "review_decision",
        "code": code,
        "decision": decision,
        "comment": (comment or "")[:500],
        "match_score": match_score,
        "tier": tier,
    }
    events = [event] + list(prefs.get("events") or [])
    prefs["events"] = events[:MAX_EVENTS]

    if decision == "rejected":
        rejects = dict(prefs.get("reject_counts") or {})
        rejects[code] = rejects.get(code, 0) + 1
        prefs["reject_counts"] = rejects
        adj = dict(prefs.get("code_adjustments") or {})
        adj[code] = min(10, adj.get(code, 0) + 2)
        prefs["code_adjustments"] = adj
    elif decision == "approved":
        approves = dict(prefs.get("approve_counts") or {})
        approves[code] = approves.get(code, 0) + 1
        prefs["approve_counts"] = approves
        adj = dict(prefs.get("code_adjustments") or {})
        if code in adj and adj[code] > 0:
            adj[code] = max(0, adj[code] - 1)
        prefs["code_adjustments"] = adj

    return save_user_preferences(user_id, prefs)


@synchronized_json_store
def record_match_threshold_choice(user_id: int, threshold: int) -> dict[str, Any]:
    prefs = load_user_preferences(user_id)
    prefs["match_threshold"] = threshold
    events = [{"type": "threshold", "value": threshold}] + list(prefs.get("events") or [])
    prefs["events"] = events[:MAX_EVENTS]
    return save_user_preferences(user_id, prefs)


@synchronized_json_store
def record_retrieval_top_k_choice(user_id: int, top_k: int) -> dict[str, Any]:
    prefs = load_user_preferences(user_id)
    prefs["retrieval_top_k"] = top_k
    events = [{"type": "retrieval_top_k", "value": top_k}] + list(prefs.get("events") or [])
    prefs["events"] = events[:MAX_EVENTS]
    return save_user_preferences(user_id, prefs)


def resolve_retrieval_top_k(user_id: Optional[int], requested: Optional[int] = None) -> int:
    from app.core.config import get_settings

    default = get_settings().retrieval_top_k_default
    if requested is not None:
        return max(1, min(10, int(requested)))
    if user_id:
        prefs = load_user_preferences(user_id)
        saved = prefs.get("retrieval_top_k")
        if saved is not None:
            return max(1, min(10, int(saved)))
    return default


@synchronized_json_store
def record_dimension_selection(user_id: int, dimensions: list[str]) -> dict[str, Any]:
    prefs = load_user_preferences(user_id)
    existing = list(prefs.get("preferred_dimensions") or [])
    for d in dimensions:
        if d not in existing:
            existing.append(d)
    prefs["preferred_dimensions"] = existing[-12:]
    return save_user_preferences(user_id, prefs)


def get_retrieval_preferences(user_id: Optional[int]) -> dict[str, Any]:
    from app.core.config import get_settings

    default_top_k = get_settings().retrieval_top_k_default
    if not user_id:
        return {"match_threshold": None, "retrieval_top_k": default_top_k, "code_adjustments": {}}
    prefs = load_user_preferences(user_id)
    top_k = prefs.get("retrieval_top_k")
    return {
        "match_threshold": prefs.get("match_threshold"),
        "retrieval_top_k": int(top_k) if top_k is not None else default_top_k,
        "code_adjustments": dict(prefs.get("code_adjustments") or {}),
        "reject_counts": dict(prefs.get("reject_counts") or {}),
        "preferred_dimensions": list(prefs.get("preferred_dimensions") or []),
    }


def preference_summary(user_id: int) -> dict[str, Any]:
    prefs = load_user_preferences(user_id)
    top_rejects = sorted(
        (prefs.get("reject_counts") or {}).items(),
        key=lambda x: x[1],
        reverse=True,
    )[:8]
    return {
        "user_id": user_id,
        "match_threshold": prefs.get("match_threshold"),
        "retrieval_top_k": prefs.get("retrieval_top_k"),
        "top_rejected_codes": [{"code": c, "count": n} for c, n in top_rejects],
        "code_adjustments": prefs.get("code_adjustments") or {},
        "contract_rule_adjustments": prefs.get("contract_rule_adjustments") or {},
        "preferred_dimensions": prefs.get("preferred_dimensions") or [],
        "updated_at": prefs.get("updated_at"),
    }


@synchronized_json_store
def record_contract_finding_decision(
    user_id: int,
    *,
    rule_id: str,
    clause_index: int,
    decision: str,
    comment: Optional[str] = None,
    risk: str = "",
) -> dict[str, Any]:
    """Learn from contract review: false positive on RED → relax rule weight next time."""
    prefs = load_user_preferences(user_id)
    event = {
        "type": "contract_finding",
        "rule_id": rule_id,
        "clause_index": clause_index,
        "decision": decision,
        "comment": (comment or "")[:500],
        "risk": risk,
    }
    events = [event] + list(prefs.get("events") or [])
    prefs["events"] = events[:MAX_EVENTS]

    adj = dict(prefs.get("contract_rule_adjustments") or {})
    if decision == "false_positive":
        adj[rule_id] = max(-5, adj.get(rule_id, 0) - 1)
    elif decision == "confirmed":
        adj[rule_id] = min(5, adj.get(rule_id, 0) + 1)
    prefs["contract_rule_adjustments"] = adj
    return save_user_preferences(user_id, prefs)


def get_user_llm_settings(user_id: Optional[int]) -> dict[str, Any]:
    if not user_id:
        return {}
    prefs = load_user_preferences(user_id)
    return dict(prefs.get("llm_settings") or {})


def get_llm_settings_response(user_id: int) -> dict[str, Any]:
    from app.services.llm_client import PROVIDER_DEFAULTS, has_user_api_key
    from app.core.config import get_settings

    if get_settings().is_production:
        return {
            "available": False,
            "disabled_reason": "生产受控试点已禁用第三方 LLM 外发，系统不会接收 API Key。",
            "enabled": False,
            "provider": "",
            "base_url": "",
            "api_key_masked": "",
            "has_api_key": False,
            "api_key_storage": "disabled",
            "default_model": "",
            "task_models": dict(_default_prefs(user_id)["llm_settings"]["task_models"]),
            "provider_defaults": {},
        }

    cfg = get_user_llm_settings(user_id)
    has_key = has_user_api_key(user_id)
    return {
        "available": True,
        "disabled_reason": None,
        "enabled": cfg.get("enabled"),
        "provider": cfg.get("provider") or "qwen",
        "base_url": cfg.get("base_url") or "",
        "api_key_masked": "********" if has_key else "",
        "has_api_key": has_key,
        "api_key_storage": "process_memory_ttl",
        "default_model": cfg.get("default_model") or "",
        "task_models": dict(cfg.get("task_models") or {}),
        "provider_defaults": PROVIDER_DEFAULTS,
    }


@synchronized_json_store
def update_user_llm_settings(user_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.services.llm_client import (
        LlmSecurityError,
        clear_user_api_key,
        store_user_api_key,
        user_api_key_binding,
        validate_provider_base_url,
    )

    if get_settings().is_production:
        raise LlmSecurityError("生产受控试点不接收 LLM 设置或 API Key")

    prefs = load_user_preferences(user_id)
    current = dict(prefs.get("llm_settings") or _default_prefs(user_id)["llm_settings"])

    requested_provider = str(updates.get("provider", current.get("provider") or "qwen")).strip().lower()
    requested_base = str(updates.get("base_url", current.get("base_url") or "")).strip()
    canonical_base = validate_provider_base_url(requested_provider, requested_base)
    binding = user_api_key_binding(user_id)

    for key in ("enabled", "provider", "base_url", "default_model"):
        if key in updates and updates[key] is not None:
            current[key] = updates[key]

    current["provider"] = requested_provider
    current["base_url"] = canonical_base

    if updates.get("clear_api_key") is True:
        clear_user_api_key(user_id)
    elif "api_key" in updates and str(updates.get("api_key") or "").strip():
        store_user_api_key(
            user_id,
            provider=requested_provider,
            base_url=canonical_base,
            api_key=str(updates["api_key"]),
        )
    elif binding and binding != (requested_provider, canonical_base):
        # Never carry an existing secret across a provider/origin change.
        clear_user_api_key(user_id)

    if "task_models" in updates and isinstance(updates["task_models"], dict):
        task_models = dict(current.get("task_models") or {})
        task_models.update(updates["task_models"])
        current["task_models"] = task_models

    prefs["llm_settings"] = current
    save_user_preferences(user_id, prefs)
    return get_llm_settings_response(user_id)
