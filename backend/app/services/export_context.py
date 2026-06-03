from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.models.scenario import InvestigationScenario


def export_context(scenario: InvestigationScenario) -> dict[str, Any]:
    payload = scenario.checklist.payload
    return {
        "scenario": scenario,
        "payload": payload,
        "brief": payload.get("brief") or {},
        "review": payload.get("review") or {},
        "sections_legal": payload.get("sections_with_legal") or payload.get("sections", []),
    }


def format_export_datetime(value: Any, *, date_only: bool = True) -> str:
    """将 review.finalized_at 等 ISO 字符串格式化为中文日期。"""
    if not value:
        return "—"
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value[:10] if date_only and len(value) >= 10 else value
    else:
        return str(value)
    if date_only:
        return dt.strftime("%Y年%m月%d日")
    return dt.strftime("%Y年%m月%d日 %H:%M")


def safe_export_filename(name: str, suffix: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name)
    return f"{cleaned[:80] or 'vela_export'}_{suffix}"
