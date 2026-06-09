"""Per-user preference loop: learn from review/playbook edits, apply to later runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

PREFS_DIR = Path(__file__).resolve().parents[2] / "data" / "user_preferences"
MAX_EVENTS = 300


def _prefs_path(user_id: int) -> Path:
    PREFS_DIR.mkdir(parents=True, exist_ok=True)
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
        "events": [],
        "updated_at": None,
    }


def load_user_preferences(user_id: int) -> dict[str, Any]:
    path = _prefs_path(user_id)
    if not path.exists():
        return _default_prefs(user_id)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {**_default_prefs(user_id), **data}


def save_user_preferences(user_id: int, prefs: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    prefs["user_id"] = user_id
    prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _prefs_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
    return prefs


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


def record_match_threshold_choice(user_id: int, threshold: int) -> dict[str, Any]:
    prefs = load_user_preferences(user_id)
    prefs["match_threshold"] = threshold
    events = [{"type": "threshold", "value": threshold}] + list(prefs.get("events") or [])
    prefs["events"] = events[:MAX_EVENTS]
    return save_user_preferences(user_id, prefs)


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
