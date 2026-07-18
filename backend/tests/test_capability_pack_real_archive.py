"""WS-1C/C2: byte-identity regression for the real brazil 1.3.1 archive bundle.

长期回归只依赖归档自身的冻结常量(EV-0022),不依赖"当前 active 文件永远与
归档相同"——后续 active 升级后本文件不得失败。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from app.capability_packs.loader import CapabilityPackLoadError
from app.capability_packs.registry import (
    CAPABILITY_PACKS_ROOT,
    CapabilityPackNotFoundError,
    CapabilityPackRegistry,
    CapabilityPackUnsupportedError,
)
from app.capability_packs.version_index import (
    discover_archived_versions,
    load_archived_pack,
)


PACK_ID = "brazil_new_energy_greenfield"
PACK_VERSION = "1.3.1"
PACK_SEMANTIC_HASH = "dd26e226ea600fd05e23d6141dab8a051881b3ed3723abcf718ddf3bc81e808b"
MANIFEST_RAW_SHA256 = "dd69255f56e9b4589f27987f11d7e3cf2b471de0c8293b25867aa4257dbba108"
RULES_ARTIFACT_ID = "brazil_new_energy"
RULES_VERSION = "2.9"
RULES_SHA256 = "351c7d6f6f71a5d1cedd3527a10a8b89f1cd72d3079d4b41d42b827aeba62c9c"
CORPUS_ARTIFACT_ID = "brazil_legal_corpus"
CORPUS_VERSION = "1.13"
CORPUS_SHA256 = "b91783bc354d57a84453b7c064d8bb413939a2693109835fbcc5b20ce54c787f"

ARCHIVE_ROOT = CAPABILITY_PACKS_ROOT / "archive"
BUNDLE = ARCHIVE_ROOT / PACK_ID / PACK_VERSION / "bundle"
ARCHIVED_MANIFEST = BUNDLE / "capability_packs" / PACK_ID / "manifest.json"
ARCHIVED_RULES = BUNDLE / "rules" / "brazil_new_energy.json"
ARCHIVED_CORPUS = BUNDLE / "data" / "brazil_legal_corpus.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _production_registry() -> CapabilityPackRegistry:
    return CapabilityPackRegistry(root=CAPABILITY_PACKS_ROOT)


def _find_real_entry(entries):
    return next(
        (e for e in entries if e.pack_id == PACK_ID and e.version == PACK_VERSION), None
    )


def test_archived_raw_bytes_match_frozen_constants() -> None:
    assert _sha256(ARCHIVED_MANIFEST) == MANIFEST_RAW_SHA256
    assert _sha256(ARCHIVED_RULES) == RULES_SHA256
    assert _sha256(ARCHIVED_CORPUS) == CORPUS_SHA256


def test_archived_manifest_identity_matches_frozen_constants() -> None:
    entry = _find_real_entry(discover_archived_versions(ARCHIVE_ROOT))
    assert entry is not None
    pack = load_archived_pack(entry)
    manifest = pack.manifest
    assert manifest.pack_id == PACK_ID
    assert manifest.version == PACK_VERSION
    assert manifest.semantic_hash == PACK_SEMANTIC_HASH
    assert manifest.rules_artifact.artifact_id == RULES_ARTIFACT_ID
    assert manifest.rules_artifact.version == RULES_VERSION
    assert manifest.rules_artifact.content_hash == RULES_SHA256
    assert manifest.corpus_artifact.artifact_id == CORPUS_ARTIFACT_ID
    assert manifest.corpus_artifact.version == CORPUS_VERSION
    assert manifest.corpus_artifact.content_hash == CORPUS_SHA256


def test_discovery_and_load_paths_stay_inside_bundle() -> None:
    entry = _find_real_entry(discover_archived_versions(ARCHIVE_ROOT))
    assert entry is not None
    assert entry.manifest_path == ARCHIVED_MANIFEST
    pack = load_archived_pack(entry)
    assert BUNDLE in pack.rules_path.parents
    assert BUNDLE in pack.corpus_path.parents
    assert pack.rules_path == ARCHIVED_RULES
    assert pack.corpus_path == ARCHIVED_CORPUS


def test_registry_index_and_exact_lookup_with_real_archive() -> None:
    registry = _production_registry()
    # active(当前 1.3.1)与 archive 同一身份:不得 collision。
    index = registry.build_version_index()
    identity = index.lookup(PACK_ID, PACK_VERSION)
    assert identity is not None
    assert identity.semantic_hash == PACK_SEMANTIC_HASH
    versions = registry.list_versions(PACK_ID)
    assert versions == [
        {
            "pack_id": PACK_ID,
            "version": PACK_VERSION,
            "semantic_hash": PACK_SEMANTIC_HASH,
            "rules_content_hash": RULES_SHA256,
            "corpus_content_hash": CORPUS_SHA256,
        }
    ]
    pack = registry.get_exact(PACK_ID, PACK_VERSION, PACK_SEMANTIC_HASH)
    assert pack.manifest.semantic_hash == PACK_SEMANTIC_HASH


def test_real_archive_not_in_public_active_or_routing() -> None:
    registry = _production_registry()
    active = registry.list_active()
    assert len(active) == 1
    assert all(pack.manifest.status == "active" for pack in active)
    summaries = registry.list_public_active()
    assert len(summaries) == 1
    # routing 只经 active 清单;归档目录不注入额外路由候选(多候选会抛错)。
    matched = registry.match(
        country=active[0].manifest.country,
        state=active[0].manifest.state,
        industry=active[0].manifest.industry,
        action_type=active[0].manifest.action_type,
    )
    assert matched.manifest.status == "active"


@pytest.fixture()
def isolated_archive_root(tmp_path: Path) -> Path:
    """真实 archive 复制到无 active Pack 的临时 capability root。"""
    root = tmp_path / "capability_packs"
    shutil.copytree(ARCHIVE_ROOT / PACK_ID, root / "archive" / PACK_ID)
    return root


def test_real_archive_readable_without_active_pack(isolated_archive_root: Path) -> None:
    registry = CapabilityPackRegistry(root=isolated_archive_root)
    pack = registry.get_exact(PACK_ID, PACK_VERSION, PACK_SEMANTIC_HASH)
    assert pack.manifest.version == PACK_VERSION
    with pytest.raises(CapabilityPackNotFoundError):
        registry.get(PACK_ID)
    with pytest.raises(CapabilityPackUnsupportedError):
        registry.match(
            country=pack.manifest.country,
            state=pack.manifest.state,
            industry=pack.manifest.industry,
            action_type=pack.manifest.action_type,
        )


def test_single_byte_tamper_fails_closed(isolated_archive_root: Path) -> None:
    registry = CapabilityPackRegistry(root=isolated_archive_root)
    rules_copy = (
        isolated_archive_root
        / "archive"
        / PACK_ID
        / PACK_VERSION
        / "bundle"
        / "rules"
        / "brazil_new_energy.json"
    )
    content = rules_copy.read_bytes()
    # 单字节替换且保持 JSON 合法,确保命中的是内容哈希校验而非解析错误。
    tampered = content.replace(b"brazil", b"brazjl", 1)
    assert tampered != content and len(tampered) == len(content)
    rules_copy.write_bytes(tampered)
    with pytest.raises(CapabilityPackLoadError, match="rules artifact content hash"):
        registry.get_exact(PACK_ID, PACK_VERSION, PACK_SEMANTIC_HASH)


def test_missing_archive_artifacts_fail_closed(isolated_archive_root: Path) -> None:
    registry = CapabilityPackRegistry(root=isolated_archive_root)
    bundle = isolated_archive_root / "archive" / PACK_ID / PACK_VERSION / "bundle"
    (bundle / "rules" / "brazil_new_energy.json").unlink()
    with pytest.raises(CapabilityPackLoadError, match="不存在"):
        registry.get_exact(PACK_ID, PACK_VERSION, PACK_SEMANTIC_HASH)

    restored = CapabilityPackRegistry(root=isolated_archive_root)
    shutil.copyfile(ARCHIVED_RULES, bundle / "rules" / "brazil_new_energy.json")
    (bundle / "data" / "brazil_legal_corpus.json").unlink()
    with pytest.raises(CapabilityPackLoadError, match="不存在"):
        restored.get_exact(PACK_ID, PACK_VERSION, PACK_SEMANTIC_HASH)
