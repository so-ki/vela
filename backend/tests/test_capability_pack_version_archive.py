"""WS-1C/C1: exact archived Capability Pack version lookup (synthetic bundles only).

真实 1.3.1 / rules 2.9 / corpus 1.13 归档属于 C2；本文件只使用临时目录中的合成
archive bundle，不触碰任何生产 manifest / rules / corpus。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.capability_packs.loader import CapabilityPackLoadError
from app.capability_packs.registry import (
    CAPABILITY_PACKS_ROOT,
    CapabilityPackNotFoundError,
    CapabilityPackRegistry,
    CapabilityPackRegistryError,
    CapabilityPackUnsupportedError,
    load_frozen_capability_pack,
)
from app.capability_packs.schemas import CapabilityPackManifest
from app.capability_packs.version_index import (
    CapabilityPackArchiveLayoutError,
    CapabilityPackVersionCollisionError,
    CapabilityPackVersionIndex,
    PackVersionIdentity,
)


PACK_ID = "zz-archive-pack"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _dump(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _rules_doc(rules_version: str, *, marker: str = "baseline") -> dict:
    return {
        "pack": {"id": "zz-archive-rules", "version": rules_version},
        "jurisdiction": {"id": "zz-arch", "name": "ZZ Archive Land"},
        "industries": {"arch_industry": {"keywords": ["arch"], "sub_sector_defs": {}}},
        "action_types": {"arch_action": {"keywords": ["arch-act"]}},
        "dimensions": {
            "dim_a": {"name": "A", "name_pt": "A", "description": "d", "order": 1}
        },
        "checklist_items": [],
        "marker": marker,
    }


def _corpus_doc(corpus_version: str) -> dict:
    return {"version": corpus_version, "documents": []}


def _build_pack(
    *,
    pack_version: str,
    rules_version: str,
    corpus_version: str,
    rules_marker: str = "baseline",
    status: str = "active",
) -> tuple[dict, bytes, bytes]:
    rules_bytes = _dump(_rules_doc(rules_version, marker=rules_marker))
    corpus_bytes = _dump(_corpus_doc(corpus_version))
    manifest = {
        "manifest_schema_version": "1.1",
        "pack_id": PACK_ID,
        "version": pack_version,
        "status": status,
        "content_status": "provisional",
        "display_name": "合成归档测试包",
        "description": "WS-1C/C1 synthetic archive bundle",
        "country": "ZZ-ARCH",
        "state": "zz-state",
        "industry": "arch_industry",
        "action_type": "arch_action",
        "languages": ["test"],
        "issue_modules": ["dim_a"],
        "rules_artifact": {
            "artifact_id": "zz-archive-rules",
            "version": rules_version,
            "content_hash": _sha256(rules_bytes),
            "resource": "rules://zz_archive_rules.json",
        },
        "corpus_artifact": {
            "artifact_id": "zz-archive-corpus",
            "version": corpus_version,
            "content_hash": _sha256(corpus_bytes),
            "resource": "corpus://zz_archive_corpus.json",
        },
        "artifact_binding": {
            "country": "zz-arch",
            "state": "zz-state",
            "industry": "arch_industry",
            "action_type": "arch_action",
        },
        "routing_hints": {
            "country": ["zz-arch-country-token"],
            "state": ["zz-arch-state-token"],
            "industry": ["zz-arch-industry-token"],
            "action_type": ["zz-arch-action-token"],
            "excluded_states": [],
            "excluded_action_types": [],
        },
        "retrieval_config": {
            "match_threshold_default": 70,
            "match_threshold_min": 50,
            "match_threshold_max": 95,
            "top_k_default": 2,
            "top_k_min": 0,
            "top_k_max": 2,
            "expansion_enabled": False,
            "expansion_candidate_extra": 0,
            "expansion_min_keyword_score": 0.0,
            "expansion_context_limit": 0,
        },
        "output_profile": {
            "profile_id": "arch_output",
            "version": "0.1.0",
            "brief_languages": ["test"],
            "brief_title": "归档测试输出",
            "export_template": "legacy",
            "disclaimer": "非真实法律内容。",
        },
        "semantic_hash": "0" * 64,
    }
    model = CapabilityPackManifest.model_validate(manifest)
    manifest["semantic_hash"] = model.canonical_semantic_hash()
    return manifest, rules_bytes, corpus_bytes


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _install_active(root: Path, manifest: dict, rules_bytes: bytes, corpus_bytes: bytes) -> None:
    _write(root / manifest["pack_id"] / "manifest.json", _dump(manifest))
    _write(root.parent / "rules" / "zz_archive_rules.json", rules_bytes)
    _write(root.parent / "data" / "zz_archive_corpus.json", corpus_bytes)


def _install_archive(
    root: Path,
    manifest: dict,
    rules_bytes: bytes,
    corpus_bytes: bytes,
    *,
    dir_pack_id: str | None = None,
    dir_version: str | None = None,
    inner_dir: str | None = None,
) -> Path:
    bundle = (
        root
        / "archive"
        / (dir_pack_id or manifest["pack_id"])
        / (dir_version or manifest["version"])
        / "bundle"
    )
    _write(
        bundle / "capability_packs" / (inner_dir or manifest["pack_id"]) / "manifest.json",
        _dump(manifest),
    )
    _write(bundle / "rules" / "zz_archive_rules.json", rules_bytes)
    _write(bundle / "data" / "zz_archive_corpus.json", corpus_bytes)
    return bundle


@pytest.fixture()
def synthetic_root(tmp_path: Path) -> Path:
    root = tmp_path / "capability_packs"
    root.mkdir()
    return root


def _registry(root: Path) -> CapabilityPackRegistry:
    return CapabilityPackRegistry(root=root)


def test_active_get_and_match_unchanged_with_archive_present(synthetic_root: Path) -> None:
    new_manifest, new_rules, new_corpus = _build_pack(
        pack_version="2.0.0", rules_version="3.0", corpus_version="2.0"
    )
    old_manifest, old_rules, old_corpus = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_active(synthetic_root, new_manifest, new_rules, new_corpus)
    _install_archive(synthetic_root, old_manifest, old_rules, old_corpus)
    registry = _registry(synthetic_root)

    pack = registry.get(PACK_ID)
    assert pack.manifest.version == "2.0.0"
    matched = registry.match(
        country="ZZ-ARCH", state="zz-state", industry="arch_industry", action_type="arch_action"
    )
    assert matched.manifest.version == "2.0.0"
    exact = registry.get_exact(PACK_ID, "2.0.0", new_manifest["semantic_hash"])
    assert exact.manifest.semantic_hash == new_manifest["semantic_hash"]


def test_production_registry_behavior_unchanged() -> None:
    registry = CapabilityPackRegistry(root=CAPABILITY_PACKS_ROOT)
    active = registry.list_active()
    assert len(active) == 1
    pack = active[0]
    assert pack.manifest.version == "1.3.1"
    assert registry.get_exact(
        pack.pack_id, pack.manifest.version, pack.manifest.semantic_hash
    ).pack_id == pack.pack_id
    assert registry.archive_root.name == "archive"


def test_get_exact_reads_archived_old_version_when_active_is_newer(
    synthetic_root: Path,
) -> None:
    new_manifest, new_rules, new_corpus = _build_pack(
        pack_version="2.0.0", rules_version="3.0", corpus_version="2.0"
    )
    old_manifest, old_rules, old_corpus = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_active(synthetic_root, new_manifest, new_rules, new_corpus)
    bundle = _install_archive(synthetic_root, old_manifest, old_rules, old_corpus)
    registry = _registry(synthetic_root)

    pack = registry.get_exact(PACK_ID, "1.0.0", old_manifest["semantic_hash"])
    assert pack.manifest.version == "1.0.0"
    assert pack.manifest.rules_artifact.version == "2.0"
    assert bundle in pack.rules_path.parents
    assert bundle in pack.corpus_path.parents


def test_archive_not_in_active_public_or_routing(synthetic_root: Path) -> None:
    old_manifest, old_rules, old_corpus = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_archive(synthetic_root, old_manifest, old_rules, old_corpus)
    registry = _registry(synthetic_root)

    assert registry.list_active() == []
    assert registry.list_public_active() == []
    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match(
            country="ZZ-ARCH",
            state="zz-state",
            industry="arch_industry",
            action_type="arch_action",
        )


def test_unknown_pack_version_and_hash_fail(synthetic_root: Path) -> None:
    manifest, rules_bytes, corpus_bytes = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_active(synthetic_root, manifest, rules_bytes, corpus_bytes)
    registry = _registry(synthetic_root)

    with pytest.raises(CapabilityPackNotFoundError):
        registry.get_exact("no-such-pack", "1.0.0", manifest["semantic_hash"])
    with pytest.raises(CapabilityPackRegistryError, match="不一致"):
        registry.get_exact(PACK_ID, "9.9.9", manifest["semantic_hash"])
    with pytest.raises(CapabilityPackRegistryError, match="不一致"):
        registry.get_exact(PACK_ID, "1.0.0", "f" * 64)


def test_same_version_different_semantic_hash_is_collision(synthetic_root: Path) -> None:
    active_manifest, active_rules, active_corpus = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0", rules_marker="active"
    )
    archive_manifest, archive_rules, archive_corpus = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0", rules_marker="tampered"
    )
    assert archive_manifest["semantic_hash"] != active_manifest["semantic_hash"]
    _install_active(synthetic_root, active_manifest, active_rules, active_corpus)
    _install_archive(synthetic_root, archive_manifest, archive_rules, archive_corpus)
    registry = _registry(synthetic_root)

    with pytest.raises(CapabilityPackVersionCollisionError):
        registry.get_exact(PACK_ID, "1.0.0", active_manifest["semantic_hash"])
    with pytest.raises(CapabilityPackVersionCollisionError):
        registry.build_version_index()


def test_same_semantic_hash_but_different_rules_hash_fails(synthetic_root: Path) -> None:
    manifest, rules_bytes, corpus_bytes = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    # 声称与原 manifest 相同的 semantic hash，但 rules content hash 被改写。
    forged = dict(manifest)
    forged["rules_artifact"] = dict(manifest["rules_artifact"])
    forged["rules_artifact"]["content_hash"] = "e" * 64
    _install_archive(synthetic_root, forged, rules_bytes, corpus_bytes)
    registry = _registry(synthetic_root)

    with pytest.raises(CapabilityPackLoadError, match="semantic hash"):
        registry.get_exact(PACK_ID, "1.0.0", manifest["semantic_hash"])

    # 变体：manifest 未改，但 bundle 内 rules bytes 被篡改。
    tampered_root = synthetic_root.parent / "capability_packs_tampered"
    tampered_root.mkdir()
    bundle = _install_archive(tampered_root, manifest, rules_bytes + b"\n", corpus_bytes)
    assert bundle.is_dir()
    registry2 = _registry(tampered_root)
    with pytest.raises(CapabilityPackLoadError, match="rules artifact content hash"):
        registry2.get_exact(PACK_ID, "1.0.0", manifest["semantic_hash"])


def test_identical_identity_in_active_and_archive_is_allowed(synthetic_root: Path) -> None:
    manifest, rules_bytes, corpus_bytes = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_active(synthetic_root, manifest, rules_bytes, corpus_bytes)
    _install_archive(synthetic_root, manifest, rules_bytes, corpus_bytes)
    registry = _registry(synthetic_root)

    pack = registry.get_exact(PACK_ID, "1.0.0", manifest["semantic_hash"])
    assert pack.manifest.version == "1.0.0"
    index = registry.build_version_index()
    assert index.lookup(PACK_ID, "1.0.0") is not None
    assert registry.list_versions(PACK_ID) == [
        {
            "pack_id": PACK_ID,
            "version": "1.0.0",
            "semantic_hash": manifest["semantic_hash"],
            "rules_content_hash": manifest["rules_artifact"]["content_hash"],
            "corpus_content_hash": manifest["corpus_artifact"]["content_hash"],
        }
    ]


def test_archive_archive_collision_is_rejected_by_index() -> None:
    index = CapabilityPackVersionIndex()
    index.register(
        pack_id=PACK_ID,
        version="1.0.0",
        identity=PackVersionIdentity("a" * 64, "b" * 64, "c" * 64),
        source="archive",
    )
    with pytest.raises(CapabilityPackVersionCollisionError):
        index.register(
            pack_id=PACK_ID,
            version="1.0.0",
            identity=PackVersionIdentity("a" * 64, "d" * 64, "c" * 64),
            source="archive",
        )


def test_archive_directory_identity_mismatch_fails(synthetic_root: Path) -> None:
    manifest, rules_bytes, corpus_bytes = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_archive(synthetic_root, manifest, rules_bytes, corpus_bytes, dir_version="9.9.9")
    registry = _registry(synthetic_root)
    with pytest.raises(CapabilityPackArchiveLayoutError, match="version 与 manifest 不一致"):
        registry.get_exact(PACK_ID, "9.9.9", manifest["semantic_hash"])

    other_root = synthetic_root.parent / "capability_packs_iddir"
    other_root.mkdir()
    _install_archive(
        other_root, manifest, rules_bytes, corpus_bytes, dir_pack_id="other-pack-id"
    )
    registry2 = _registry(other_root)
    with pytest.raises(CapabilityPackArchiveLayoutError, match="pack ID 不一致"):
        registry2.get_exact("other-pack-id", "1.0.0", manifest["semantic_hash"])

    third_root = synthetic_root.parent / "capability_packs_innerdir"
    third_root.mkdir()
    _install_archive(third_root, manifest, rules_bytes, corpus_bytes, inner_dir="wrong-inner")
    registry3 = _registry(third_root)
    with pytest.raises(CapabilityPackArchiveLayoutError, match="pack ID 不一致"):
        registry3.get_exact(PACK_ID, "1.0.0", manifest["semantic_hash"])


def test_archive_path_traversal_blocked_by_loader(synthetic_root: Path) -> None:
    manifest, rules_bytes, corpus_bytes = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    forged = dict(manifest)
    forged["rules_artifact"] = dict(manifest["rules_artifact"])
    forged["rules_artifact"]["resource"] = "rules://../../outside.json"
    _install_archive(synthetic_root, forged, rules_bytes, corpus_bytes)
    _write(synthetic_root / "archive" / PACK_ID / "1.0.0" / "outside.json", b"{}")
    registry = _registry(synthetic_root)
    with pytest.raises(CapabilityPackLoadError):
        registry.get_exact(PACK_ID, "1.0.0", manifest["semantic_hash"])

    # bundle 之外的文件不可经 rules:// 到达：bundle/rules 缺文件必须失败。
    other_root = synthetic_root.parent / "capability_packs_missing"
    other_root.mkdir()
    bundle = _install_archive(other_root, manifest, rules_bytes, corpus_bytes)
    (bundle / "rules" / "zz_archive_rules.json").unlink()
    registry2 = _registry(other_root)
    with pytest.raises(CapabilityPackLoadError, match="不存在"):
        registry2.get_exact(PACK_ID, "1.0.0", manifest["semantic_hash"])


def test_fixture_behavior_unchanged() -> None:
    registry = CapabilityPackRegistry(
        root=CAPABILITY_PACKS_ROOT, include_test_fixtures=True, app_env="test"
    )
    fixture = registry.get("test_fixture_pack")
    assert fixture.is_test_fixture is True
    assert all(
        summary["pack_id"] != "test_fixture_pack" for summary in registry.list_public_active()
    )


def test_load_frozen_capability_pack_loads_archived_identity(synthetic_root: Path) -> None:
    new_manifest, new_rules, new_corpus = _build_pack(
        pack_version="2.0.0", rules_version="3.0", corpus_version="2.0"
    )
    old_manifest, old_rules, old_corpus = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_active(synthetic_root, new_manifest, new_rules, new_corpus)
    _install_archive(synthetic_root, old_manifest, old_rules, old_corpus)
    registry = _registry(synthetic_root)
    frozen_pack = registry.get_exact(PACK_ID, "1.0.0", old_manifest["semantic_hash"])
    manifest = frozen_pack.manifest
    snapshot = {
        "capability_pack_id": PACK_ID,
        "capability_pack_version": "1.0.0",
        "capability_pack_hash": old_manifest["semantic_hash"],
        "issue_modules": list(manifest.issue_modules),
        "rules_artifact_id": manifest.rules_artifact.artifact_id,
        "rules_artifact_version": manifest.rules_artifact.version,
        "rules_artifact_hash": manifest.rules_artifact.content_hash,
        "corpus_artifact_id": manifest.corpus_artifact.artifact_id,
        "corpus_artifact_version": manifest.corpus_artifact.version,
        "corpus_artifact_hash": manifest.corpus_artifact.content_hash,
        "artifact_binding": manifest.artifact_binding.model_dump(mode="json"),
        "retrieval_config": manifest.retrieval_config.model_dump(mode="json"),
        "output_profile": manifest.output_profile.model_dump(mode="json"),
    }

    pack = load_frozen_capability_pack(snapshot, registry=registry)
    assert pack.manifest.version == "1.0.0"
    assert pack.manifest.semantic_hash == old_manifest["semantic_hash"]

    stale = dict(snapshot)
    stale["rules_artifact_hash"] = "f" * 64
    with pytest.raises(CapabilityPackRegistryError, match="不一致"):
        load_frozen_capability_pack(stale, registry=registry)


def test_archive_readable_without_any_active_pack_but_not_routable(
    synthetic_root: Path,
) -> None:
    old_manifest, old_rules, old_corpus = _build_pack(
        pack_version="1.0.0", rules_version="2.0", corpus_version="1.0"
    )
    _install_archive(synthetic_root, old_manifest, old_rules, old_corpus)
    registry = _registry(synthetic_root)

    pack = registry.get_exact(PACK_ID, "1.0.0", old_manifest["semantic_hash"])
    assert pack.manifest.version == "1.0.0"
    with pytest.raises(CapabilityPackNotFoundError):
        registry.get(PACK_ID)
    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match(
            country="ZZ-ARCH",
            state="zz-state",
            industry="arch_industry",
            action_type="arch_action",
        )
    with pytest.raises(CapabilityPackNotFoundError):
        registry.get_exact(PACK_ID, "8.8.8", old_manifest["semantic_hash"])
