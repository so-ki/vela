"""Playbook deviation log (Claude for Legal playbook monitor pattern)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEVIATIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "playbook_deviations.json"
MAX_GLOBAL = 200


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_global() -> list[dict[str, Any]]:
    if not DEVIATIONS_PATH.exists():
        return []
    with open(DEVIATIONS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("deviations") or [])


def _save_global(deviations: list[dict[str, Any]]) -> None:
    DEVIATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEVIATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({"deviations": deviations[:MAX_GLOBAL]}, f, ensure_ascii=False, indent=2)


def record_deviation(
    *,
    scenario_id: int,
    project_name: str,
    code: str,
    title: str,
    comment: Optional[str],
    reviewer_name: str,
    match_score: float = 0.0,
    gate_status: str = "",
) -> dict[str, Any]:
    entry = {
        "id": f"{scenario_id}-{code}-{_utcnow_iso()[:19]}",
        "scenario_id": scenario_id,
        "project_name": project_name,
        "code": code,
        "title": title,
        "comment": comment,
        "reviewer_name": reviewer_name,
        "match_score": match_score,
        "gate_status": gate_status,
        "recorded_at": _utcnow_iso(),
        "playbook_hint": "累计驳回可反馈至规则包 checklist 或法源 binding 调整",
    }
    global_list = _load_global()
    global_list.insert(0, entry)
    _save_global(global_list)
    return entry


def append_scenario_deviation(payload: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    deviations = list(payload.get("playbook_deviations") or [])
    deviations.insert(0, entry)
    payload["playbook_deviations"] = deviations[:50]
    return payload


def list_global_deviations(*, limit: int = 30) -> list[dict[str, Any]]:
    return _load_global()[:limit]


def deviation_stats() -> dict[str, Any]:
    items = _load_global()
    by_code: dict[str, int] = {}
    for d in items:
        code = d.get("code") or "unknown"
        by_code[code] = by_code.get(code, 0) + 1
    top = sorted(by_code.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "total": len(items),
        "top_rejected_codes": [{"code": c, "count": n} for c, n in top],
    }
