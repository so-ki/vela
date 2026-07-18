"""能力包薄加载器：发现、读取、缓存 manifest 与规则卡。

刻意保持薄：没有注册机制、没有插件系统、没有签核工作流。
"加载"就是读目录下的 JSON 文件。等第二个能力包真实存在、
两个实例证明了共性之后，才允许把这里长厚（三次法则）。

法域中立：本模块不得出现任何具体法域内容。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

PACKS_ROOT = Path(__file__).resolve().parent

_manifest_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class PackNotInstalledError(Exception):
    """请求的能力包不存在。调用方应转化为结构化拒答，而非静默回退。"""


def _packs_root() -> Path:
    return PACKS_ROOT


def list_installed_packs(root: Optional[Path] = None) -> list[dict[str, Any]]:
    """扫描 packs 目录，返回全部已安装包的 manifest。空目录返回空列表，不抛错。"""
    base = root or _packs_root()
    manifests: list[dict[str, Any]] = []
    if not base.is_dir():
        return manifests
    for manifest_path in sorted(base.glob("*/manifest.json")):
        try:
            manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return manifests


def load_manifest(pack_id: str, root: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """按 pack_id 读 manifest（mtime 缓存）。未安装返回 None。"""
    base = root or _packs_root()
    path = base / pack_id / "manifest.json"
    if not path.is_file():
        return None
    mtime = path.stat().st_mtime
    cached = _manifest_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    _manifest_cache[str(path)] = (mtime, data)
    return data


def require_manifest(pack_id: str, root: Optional[Path] = None) -> dict[str, Any]:
    manifest = load_manifest(pack_id, root=root)
    if manifest is None:
        raise PackNotInstalledError(f"capability pack not installed: {pack_id}")
    return manifest


def load_rule_cards(pack_id: str, root: Optional[Path] = None) -> list[dict[str, Any]]:
    """读包内 rule_cards/ 目录下全部规则卡。没有目录返回空列表。"""
    base = root or _packs_root()
    cards_dir = base / pack_id / "rule_cards"
    cards: list[dict[str, Any]] = []
    if not cards_dir.is_dir():
        return cards
    for card_path in sorted(cards_dir.glob("*.json")):
        try:
            cards.append(json.loads(card_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return cards


def coverage_denominators(pack_id: str, root: Optional[Path] = None) -> dict[str, Any]:
    """包声明的官方分母来源。只有列在这里的来源允许"目录穷举后未见"。"""
    manifest = load_manifest(pack_id, root=root)
    if not manifest:
        return {}
    return dict(manifest.get("coverage_denominators") or {})


def clear_caches() -> None:
    _manifest_cache.clear()
