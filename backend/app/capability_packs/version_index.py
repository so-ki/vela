"""Exact-version index for archived Capability Pack bundles (WS-1C/C1).

Archive layout (server-owned, immutable):

    capability_packs/archive/
    └── <pack_id>/
        └── <pack_version>/
            └── bundle/
                ├── capability_packs/<pack_id>/manifest.json
                ├── rules/<rules-file>
                └── data/<corpus-file>

A bundle is self-contained: its ``capability_packs`` directory is passed to the
existing loader as ``capability_root`` so ``rules://`` and ``corpus://`` resolve
inside the bundle with unchanged semantics. Archived versions never participate
in active listing, public listing or routing; they are only reachable through
an exact ``(pack_id, version, semantic_hash)`` lookup. Every load re-verifies
all content hashes via the loader; nothing here weakens integrity checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.capability_packs.loader import (
    CapabilityPackLoadError,
    LoadedCapabilityPack,
    load_capability_pack,
)


ARCHIVE_DIR_NAME = "archive"
_BUNDLE_DIR_NAME = "bundle"
_BUNDLE_PACKS_DIR_NAME = "capability_packs"


class CapabilityPackArchiveError(CapabilityPackLoadError):
    pass


class CapabilityPackArchiveLayoutError(CapabilityPackArchiveError):
    pass


class CapabilityPackVersionCollisionError(CapabilityPackArchiveError):
    pass


@dataclass(frozen=True)
class ArchivedPackVersion:
    """A structurally discovered archived version (not yet hash-verified)."""

    pack_id: str
    version: str
    manifest_path: Path
    capability_root: Path


@dataclass(frozen=True)
class PackVersionIdentity:
    """The immutable identity one ``(pack_id, version)`` must resolve to."""

    semantic_hash: str
    rules_content_hash: str
    corpus_content_hash: str


def identity_of(pack: LoadedCapabilityPack) -> PackVersionIdentity:
    return PackVersionIdentity(
        semantic_hash=pack.manifest.semantic_hash,
        rules_content_hash=pack.manifest.rules_artifact.content_hash,
        corpus_content_hash=pack.manifest.corpus_artifact.content_hash,
    )


def discover_archived_versions(archive_root: Path) -> list[ArchivedPackVersion]:
    """Scan the archive root and validate directory-name identity structurally."""
    entries: list[ArchivedPackVersion] = []
    if not archive_root.is_dir():
        return entries
    for pack_dir in sorted(archive_root.iterdir()):
        if not pack_dir.is_dir():
            continue
        for version_dir in sorted(pack_dir.iterdir()):
            if not version_dir.is_dir():
                continue
            bundle_packs_root = version_dir / _BUNDLE_DIR_NAME / _BUNDLE_PACKS_DIR_NAME
            manifests = (
                sorted(bundle_packs_root.glob("*/manifest.json"))
                if bundle_packs_root.is_dir()
                else []
            )
            if not manifests:
                raise CapabilityPackArchiveLayoutError(
                    f"archive bundle 缺少 manifest：{pack_dir.name}/{version_dir.name}"
                )
            if len(manifests) != 1:
                raise CapabilityPackArchiveLayoutError(
                    f"archive bundle 只能包含一个 Capability Pack：{pack_dir.name}/{version_dir.name}"
                )
            manifest_path = manifests[0]
            if manifest_path.parent.name != pack_dir.name:
                raise CapabilityPackArchiveLayoutError(
                    f"archive bundle 内目录与归档 pack ID 不一致：{pack_dir.name}/{version_dir.name}"
                )
            entries.append(
                ArchivedPackVersion(
                    pack_id=pack_dir.name,
                    version=version_dir.name,
                    manifest_path=manifest_path,
                    capability_root=bundle_packs_root,
                )
            )
    return entries


def load_archived_pack(entry: ArchivedPackVersion) -> LoadedCapabilityPack:
    """Load one archived bundle through the unchanged loader, then bind identity.

    The loader re-verifies the manifest semantic hash and rules/corpus content
    hashes byte-for-byte; here we additionally require the archive directory
    names to equal the manifest identity, so a bundle cannot masquerade as a
    different pack or version.
    """
    pack = load_capability_pack(
        entry.manifest_path,
        capability_root=entry.capability_root,
        is_test_fixture=False,
    )
    if pack.pack_id != entry.pack_id:
        raise CapabilityPackArchiveLayoutError(
            f"archive 目录 pack ID 与 manifest 不一致：{entry.pack_id} != {pack.pack_id}"
        )
    if pack.manifest.version != entry.version:
        raise CapabilityPackArchiveLayoutError(
            f"archive 目录 version 与 manifest 不一致：{entry.version} != {pack.manifest.version}"
        )
    return pack


class CapabilityPackVersionIndex:
    """Add-only exact index: one ``(pack_id, version)`` -> one immutable identity."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], tuple[PackVersionIdentity, str]] = {}

    def register(
        self,
        *,
        pack_id: str,
        version: str,
        identity: PackVersionIdentity,
        source: str,
    ) -> None:
        key = (pack_id, version)
        existing = self._records.get(key)
        if existing is None:
            self._records[key] = (identity, source)
            return
        if existing[0] != identity:
            raise CapabilityPackVersionCollisionError(
                f"Capability Pack 版本身份冲突：{pack_id}@{version}"
                f"（{existing[1]} 与 {source} 的 semantic/rules/corpus hash 不一致）"
            )

    def lookup(self, pack_id: str, version: str) -> PackVersionIdentity | None:
        record = self._records.get((pack_id, version))
        return record[0] if record else None

    def as_mapping(self) -> dict[tuple[str, str], PackVersionIdentity]:
        return {key: record[0] for key, record in self._records.items()}
