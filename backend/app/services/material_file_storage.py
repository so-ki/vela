from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "data" / "scenario_materials"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-()\u4e00-\u9fff]+")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "upload.bin"
    cleaned = _SAFE_NAME.sub("_", base)
    return cleaned[:180]


def scenario_material_dir(scenario_id: int) -> Path:
    return UPLOAD_ROOT / str(scenario_id)


def save_scenario_material_files(
    scenario_id: int,
    uploads: list[tuple[str, bytes, str | None]],
) -> list[dict[str, Any]]:
    """Persist original proposal files for a scenario. Returns archived_files metadata."""
    if not uploads:
        return []

    target_dir = scenario_material_dir(scenario_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    archived: list[dict[str, Any]] = []
    for original_name, content, content_type in uploads:
        file_id = uuid.uuid4().hex
        safe_name = _safe_filename(original_name)
        stored_name = f"{file_id}__{safe_name}"
        path = target_dir / stored_name
        path.write_bytes(content)
        archived.append(
            {
                "id": file_id,
                "filename": original_name,
                "stored_name": stored_name,
                "size": len(content),
                "content_type": content_type or "application/octet-stream",
                "archived_at": _utcnow().isoformat(),
            }
        )
    return archived


def list_archived_files(scenario_id: int) -> list[dict[str, Any]]:
    """Read archived_files from disk layout (fallback when payload missing entries)."""
    target_dir = scenario_material_dir(scenario_id)
    if not target_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(target_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        file_id = name.split("__", 1)[0] if "__" in name else name
        display = name.split("__", 1)[1] if "__" in name else name
        results.append(
            {
                "id": file_id,
                "filename": display,
                "stored_name": name,
                "size": path.stat().st_size,
                "content_type": "application/octet-stream",
            }
        )
    return results


def resolve_archived_file_path(scenario_id: int, stored_name: str) -> Path | None:
    target_dir = scenario_material_dir(scenario_id)
    path = (target_dir / Path(stored_name).name).resolve()
    if not str(path).startswith(str(target_dir.resolve())):
        return None
    if path.is_file():
        return path
    return None
