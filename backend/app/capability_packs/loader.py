from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.capability_packs.schemas import CapabilityPackManifest


class CapabilityPackLoadError(ValueError):
    pass


class CapabilityPackSchemaError(CapabilityPackLoadError):
    pass


class CapabilityPackIntegrityError(CapabilityPackLoadError):
    pass


@dataclass(frozen=True)
class LoadedCapabilityPack:
    manifest: CapabilityPackManifest
    manifest_path: Path
    rules_path: Path
    corpus_path: Path
    rules: dict[str, Any]
    corpus: dict[str, Any]
    is_test_fixture: bool = False

    @property
    def pack_id(self) -> str:
        return self.manifest.pack_id

    def public_summary(self) -> dict[str, Any]:
        return self.manifest.public_summary()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bytes_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_child(root: Path, relative: str) -> Path:
    if not relative or relative.startswith(("/", "\\")):
        raise CapabilityPackLoadError("Capability Pack resource 不得使用绝对路径")
    parts = Path(relative).parts
    if any(part in {"..", "."} for part in parts):
        raise CapabilityPackLoadError("Capability Pack resource 包含路径穿越")
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise CapabilityPackLoadError("Capability Pack resource 越出允许目录")
    if not candidate.is_file():
        raise CapabilityPackLoadError(f"Capability Pack artifact 不存在：{relative}")
    return candidate


def resolve_server_resource(
    resource: str,
    *,
    capability_root: Path,
    pack_dir: Path,
    is_test_fixture: bool,
) -> Path:
    scheme, relative = resource.split("://", 1)
    if scheme == "rules":
        return _safe_child(capability_root.parent / "rules", relative)
    if scheme == "corpus":
        return _safe_child(capability_root.parent / "data", relative)
    if scheme == "fixture" and is_test_fixture:
        return _safe_child(pack_dir, relative)
    raise CapabilityPackLoadError("Capability Pack artifact scheme 未获服务端授权")


def _load_json(path: Path) -> dict[str, Any]:
    _, value = _read_json_bytes(path)
    return value


def _read_json_bytes(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Read once so integrity verification and JSON parsing use identical bytes."""
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CapabilityPackLoadError(f"无法读取 Capability Pack JSON：{path.name}") from exc
    if not isinstance(value, dict):
        raise CapabilityPackSchemaError(f"Capability Pack JSON 顶层必须为对象：{path.name}")
    return content, value


def load_capability_pack(
    manifest_path: Path,
    *,
    capability_root: Path,
    is_test_fixture: bool = False,
) -> LoadedCapabilityPack:
    manifest_path = manifest_path.resolve()
    allowed_manifest_root = (capability_root / "fixtures" if is_test_fixture else capability_root).resolve()
    if allowed_manifest_root not in manifest_path.parents:
        raise CapabilityPackLoadError("manifest 不在允许的 Capability Pack 目录")
    try:
        manifest = CapabilityPackManifest.model_validate(_load_json(manifest_path))
    except ValidationError as exc:
        raise CapabilityPackSchemaError(f"Capability Pack manifest schema 无效：{exc}") from exc
    if manifest.canonical_semantic_hash() != manifest.semantic_hash:
        raise CapabilityPackIntegrityError("Capability Pack manifest semantic hash 不一致")

    pack_dir = manifest_path.parent
    rules_path = resolve_server_resource(
        manifest.rules_artifact.resource,
        capability_root=capability_root,
        pack_dir=pack_dir,
        is_test_fixture=is_test_fixture,
    )
    corpus_path = resolve_server_resource(
        manifest.corpus_artifact.resource,
        capability_root=capability_root,
        pack_dir=pack_dir,
        is_test_fixture=is_test_fixture,
    )
    rules_bytes, rules = _read_json_bytes(rules_path)
    corpus_bytes, corpus = _read_json_bytes(corpus_path)
    if _bytes_sha256(rules_bytes) != manifest.rules_artifact.content_hash:
        raise CapabilityPackIntegrityError("rules artifact content hash 不一致")
    if _bytes_sha256(corpus_bytes) != manifest.corpus_artifact.content_hash:
        raise CapabilityPackIntegrityError("corpus artifact content hash 不一致")
    rules_pack = rules.get("pack") or {}
    if rules_pack.get("id") != manifest.rules_artifact.artifact_id:
        raise CapabilityPackIntegrityError("rules artifact ID 与 manifest 不一致")
    if str(rules_pack.get("version") or "") != manifest.rules_artifact.version:
        raise CapabilityPackIntegrityError("rules artifact version 与 manifest 不一致")
    if str(corpus.get("version") or "") != manifest.corpus_artifact.version:
        raise CapabilityPackIntegrityError("corpus artifact version 与 manifest 不一致")
    binding = manifest.artifact_binding
    if binding.industry not in (rules.get("industries") or {}):
        raise CapabilityPackIntegrityError("artifact binding industry 不存在")
    if binding.action_type not in (rules.get("action_types") or {}):
        raise CapabilityPackIntegrityError("artifact binding action type 不存在")
    if binding.country != str((rules.get("jurisdiction") or {}).get("id") or ""):
        raise CapabilityPackIntegrityError("artifact binding country 不一致")
    if set(manifest.issue_modules) - set((rules.get("dimensions") or {}).keys()):
        raise CapabilityPackIntegrityError("Capability Pack issue modules 不受规则制品支持")
    return LoadedCapabilityPack(
        manifest=manifest,
        manifest_path=manifest_path,
        rules_path=rules_path,
        corpus_path=corpus_path,
        rules=rules,
        corpus=corpus,
        is_test_fixture=is_test_fixture,
    )
