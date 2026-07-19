from __future__ import annotations

import re
import uuid
import hashlib
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "data" / "scenario_materials"
# Compatibility hook retained for existing deployments and tests that bind a
# process-local material directory. Competition mode can override it by env.
UPLOAD_ROOT = DEFAULT_UPLOAD_ROOT
MAX_SCENARIO_ARCHIVED_FILES = 30
MAX_SCENARIO_ARCHIVED_BYTES = 250 * 1024 * 1024
MAX_INSTANCE_ARCHIVED_BYTES = 5 * 1024 * 1024 * 1024
_STORAGE_LOCK = threading.RLock()

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-()\u4e00-\u9fff]+")
_STORED_NAME = re.compile(r"^[0-9a-f]{32}__[A-Za-z0-9._\-()\u4e00-\u9fff]+$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "upload.bin"
    cleaned = _SAFE_NAME.sub("_", base)
    return cleaned[:180]


def scenario_material_dir(scenario_id: int) -> Path:
    return material_upload_root() / str(scenario_id)


def material_upload_root() -> Path:
    configured = os.environ.get("VELA_SCENARIO_MATERIALS_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else UPLOAD_ROOT


def _regular_file_usage(root: Path) -> tuple[int, int]:
    if not root.is_dir():
        return 0, 0
    count = 0
    size = 0
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        dirnames[:] = [name for name in dirnames if not (directory_path / name).is_symlink()]
        for filename in filenames:
            path = directory_path / filename
            if path.is_symlink() or not path.is_file():
                continue
            count += 1
            size += path.stat().st_size
    return count, size


def save_scenario_material_files(
    scenario_id: int,
    uploads: list[tuple[str, bytes, str | None]],
) -> list[dict[str, Any]]:
    """Persist original proposal files for a scenario. Returns archived_files metadata."""
    if not uploads:
        return []

    with _STORAGE_LOCK:
        target_dir = scenario_material_dir(scenario_id)
        scenario_count, scenario_bytes = _regular_file_usage(target_dir)
        _, instance_bytes = _regular_file_usage(material_upload_root())
        incoming_bytes = sum(len(content) for _, content, _ in uploads)
        if scenario_count + len(uploads) > MAX_SCENARIO_ARCHIVED_FILES:
            raise ValueError(f"单个项目最多归档 {MAX_SCENARIO_ARCHIVED_FILES} 个原始文件")
        if scenario_bytes + incoming_bytes > MAX_SCENARIO_ARCHIVED_BYTES:
            raise ValueError("单个项目归档原始文件合计不能超过 250MB")
        if instance_bytes + incoming_bytes > MAX_INSTANCE_ARCHIVED_BYTES:
            raise ValueError("当前实例的原始材料归档容量已达 5GB 上限，请联系部署管理员")

        target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        target_dir.chmod(0o700)

        archived: list[dict[str, Any]] = []
        created_paths: list[Path] = []
        try:
            for original_name, content, content_type in uploads:
                file_id = uuid.uuid4().hex
                safe_name = _safe_filename(original_name)
                stored_name = f"{file_id}__{safe_name}"
                path = target_dir / stored_name
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(path, flags, 0o600)
                created_paths.append(path)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                archived.append(
                    {
                        "id": file_id,
                        "filename": original_name,
                        "stored_name": stored_name,
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "content_type": content_type or "application/octet-stream",
                        "content_screening": "active_content_screened_not_antivirus",
                        "archived_at": _utcnow().isoformat(),
                    }
                )
        except Exception:
            for path in created_paths:
                path.unlink(missing_ok=True)
            raise
        return archived


def list_archived_files(scenario_id: int) -> list[dict[str, Any]]:
    """Read archived_files from disk layout (fallback when payload missing entries)."""
    target_dir = scenario_material_dir(scenario_id)
    if not target_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(target_dir.iterdir()):
        if path.is_symlink() or not path.is_file():
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
                "content_screening": "unknown_legacy_file_not_antivirus_scanned",
            }
        )
    return results


def resolve_archived_file_path(scenario_id: int, stored_name: str) -> Path | None:
    target_dir = scenario_material_dir(scenario_id)
    if Path(stored_name).name != stored_name or not _STORED_NAME.fullmatch(stored_name):
        return None
    unresolved = target_dir / stored_name
    if unresolved.is_symlink():
        return None
    path = unresolved.resolve()
    try:
        path.relative_to(target_dir.resolve())
    except ValueError:
        return None
    if path.is_file():
        return path
    return None
