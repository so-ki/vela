from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.capability_packs.loader import LoadedCapabilityPack, load_capability_pack
from app.capability_packs.version_index import (
    ARCHIVE_DIR_NAME,
    ArchivedPackVersion,
    CapabilityPackVersionCollisionError,
    CapabilityPackVersionIndex,
    discover_archived_versions,
    identity_of,
    load_archived_pack,
)


CAPABILITY_PACKS_ROOT = Path(__file__).resolve().parent
_PACK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
# 保守安全格式（非严格 SemVer）：现有 artifact version 不全遵守 SemVer。
_EXACT_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SEMANTIC_HASH = re.compile(r"^[0-9a-f]{64}$")


class CapabilityPackRegistryError(ValueError):
    pass


class CapabilityPackNotFoundError(CapabilityPackRegistryError):
    pass


class CapabilityPackInactiveError(CapabilityPackRegistryError):
    pass


class CapabilityPackUnsupportedError(CapabilityPackRegistryError):
    pass


class CapabilityPackFixtureDisabledError(CapabilityPackRegistryError):
    pass


class CapabilityPackRegistry:
    """Strict server-owned registry. It has no default-pack fallback."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        include_test_fixtures: bool = False,
        app_env: str | None = None,
    ) -> None:
        self.root = (root or CAPABILITY_PACKS_ROOT).resolve()
        self.include_test_fixtures = include_test_fixtures
        self.app_env = (app_env or "development").lower()
        if include_test_fixtures and self.app_env != "test":
            raise CapabilityPackFixtureDisabledError("测试 fixture 只能在 test 环境显式开启")

    @property
    def archive_root(self) -> Path:
        return self.root / ARCHIVE_DIR_NAME

    def _manifest_paths(self) -> list[tuple[Path, bool]]:
        paths = [
            (path, False)
            for path in sorted(self.root.glob("*/manifest.json"))
            if path.parent.name not in {"fixtures", ARCHIVE_DIR_NAME}
        ]
        if self.include_test_fixtures:
            paths.extend((path, True) for path in sorted((self.root / "fixtures").glob("*/manifest.json")))
        return paths

    def _all(self) -> list[LoadedCapabilityPack]:
        packs = [
            load_capability_pack(path, capability_root=self.root, is_test_fixture=is_fixture)
            for path, is_fixture in self._manifest_paths()
        ]
        seen: set[str] = set()
        for pack in packs:
            if pack.pack_id in seen:
                raise CapabilityPackRegistryError(f"Capability Pack ID 重复：{pack.pack_id}")
            seen.add(pack.pack_id)
        return packs

    def list_active(self) -> list[LoadedCapabilityPack]:
        return [pack for pack in self._all() if pack.manifest.status == "active"]

    def list_public_active(self) -> list[dict]:
        return [pack.public_summary() for pack in self.list_active() if not pack.is_test_fixture]

    def get(self, pack_id: str, *, require_active: bool = True) -> LoadedCapabilityPack:
        if not _PACK_ID.fullmatch(pack_id):
            raise CapabilityPackNotFoundError("Capability Pack ID 非法")
        pack = next((item for item in self._all() if item.pack_id == pack_id), None)
        if pack is None:
            raise CapabilityPackNotFoundError(f"Capability Pack 不存在：{pack_id}")
        if require_active and pack.manifest.status != "active":
            raise CapabilityPackInactiveError(f"Capability Pack 未启用：{pack_id}")
        return pack

    def _archived_entries(self) -> list[ArchivedPackVersion]:
        return discover_archived_versions(self.archive_root)

    def _load_archived_exact(self, pack_id: str, version: str) -> LoadedCapabilityPack | None:
        entry = next(
            (
                item
                for item in self._archived_entries()
                if item.pack_id == pack_id and item.version == version
            ),
            None,
        )
        if entry is None:
            return None
        return load_archived_pack(entry)

    def get_exact(self, pack_id: str, version: str, semantic_hash: str) -> LoadedCapabilityPack:
        """Exact (pack_id, version, semantic_hash) lookup: active first, then archive.

        Archived versions are only reachable here; they never join active,
        public or routing results. No fallback to active/current/nearest
        version or any other hash is performed. Exact historical reads are
        deliberately decoupled from routing "active" status: an inactive
        live-root pack stays readable by its exact identity (C1-F1), while
        get()/match() keep requiring active.
        """
        if not _PACK_ID.fullmatch(pack_id):
            raise CapabilityPackNotFoundError("Capability Pack ID 非法")
        if not _EXACT_VERSION.fullmatch(version or ""):
            raise CapabilityPackRegistryError("Capability Pack version 格式非法")
        semantic_hash = (semantic_hash or "").lower()
        if not _SEMANTIC_HASH.fullmatch(semantic_hash):
            raise CapabilityPackRegistryError("Capability Pack semantic hash 格式非法")
        live_pack: LoadedCapabilityPack | None = None
        try:
            live_pack = self.get(pack_id, require_active=False)
        except CapabilityPackNotFoundError:
            live_pack = None
        archived_pack = self._load_archived_exact(pack_id, version)
        if (
            live_pack is not None
            and archived_pack is not None
            and live_pack.manifest.version == version
            and identity_of(live_pack) != identity_of(archived_pack)
        ):
            raise CapabilityPackVersionCollisionError(
                f"Capability Pack 版本身份冲突：{pack_id}@{version}"
                "（live-root 与 archive 的 semantic/rules/corpus hash 不一致）"
            )
        if (
            live_pack is not None
            and live_pack.manifest.version == version
            and live_pack.manifest.semantic_hash == semantic_hash
        ):
            return live_pack
        if archived_pack is not None and archived_pack.manifest.semantic_hash == semantic_hash:
            return archived_pack
        if live_pack is None and archived_pack is None:
            raise CapabilityPackNotFoundError(f"Capability Pack 不存在：{pack_id}")
        raise CapabilityPackRegistryError("Capability Pack version/hash 与冻结身份不一致")

    def build_version_index(self) -> CapabilityPackVersionIndex:
        """Full (pack_id, version) -> immutable identity index with collision checks.

        Registers every live-root pack (any status) and every archived bundle;
        the same key may appear in both only with a byte-identical artifact
        identity, otherwise a version-collision error is raised.
        """
        index = CapabilityPackVersionIndex()
        for pack in self._all():
            index.register(
                pack_id=pack.pack_id,
                version=pack.manifest.version,
                identity=identity_of(pack),
                source="active",
            )
        for entry in self._archived_entries():
            pack = load_archived_pack(entry)
            index.register(
                pack_id=pack.pack_id,
                version=pack.manifest.version,
                identity=identity_of(pack),
                source="archive",
            )
        return index

    def list_versions(self, pack_id: str) -> list[dict]:
        """All known exact versions of one pack (live root + archive), no routing."""
        mapping = self.build_version_index().as_mapping()
        return [
            {
                "pack_id": key[0],
                "version": key[1],
                "semantic_hash": identity.semantic_hash,
                "rules_content_hash": identity.rules_content_hash,
                "corpus_content_hash": identity.corpus_content_hash,
            }
            for key, identity in sorted(mapping.items())
            if key[0] == pack_id
        ]

    def match(
        self,
        *,
        country: str,
        state: str,
        industry: str,
        action_type: str,
    ) -> LoadedCapabilityPack:
        route = (country.upper(), state.lower(), industry.lower(), action_type.lower())
        matches = [
            pack
            for pack in self.list_active()
            if (
                pack.manifest.country.upper(),
                pack.manifest.state.lower(),
                pack.manifest.industry.lower(),
                pack.manifest.action_type.lower(),
            )
            == route
        ]
        if not matches:
            raise CapabilityPackUnsupportedError(
                f"当前没有匹配的受控试点 Capability Pack："
                f"{country}/{state}/{industry}/{action_type}"
            )
        if len(matches) != 1:
            raise CapabilityPackRegistryError("同一路由匹配到多个 active Capability Pack")
        return matches[0]

    def match_material(
        self,
        *,
        material_text: str,
        country_hint: str | None = None,
        state_hint: str | None = None,
        industry_hint: str | None = None,
        action_type_hint: str | None = None,
    ) -> LoadedCapabilityPack:
        """Match from server-owned manifest hints; every route dimension must be evidenced."""
        text = material_text.casefold()

        def accepted_values(canonical: str, aliases: list[str]) -> set[str]:
            return {canonical.casefold(), *(item.casefold() for item in aliases)}

        def contains_alias(alias: str) -> bool:
            alias = alias.strip().casefold()
            if not alias:
                return False
            if alias.isascii():
                # A short route code such as BR must not match inside "sobre".
                return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text))
            return alias in text

        def evidenced(canonical: str, aliases: list[str]) -> bool:
            return any(contains_alias(alias) for alias in accepted_values(canonical, aliases))

        def compatible(explicit: str | None, canonical: str, aliases: list[str]) -> bool:
            if not explicit or not explicit.strip():
                return True
            return explicit.strip().casefold() in accepted_values(canonical, aliases)

        matches: list[LoadedCapabilityPack] = []
        for pack in self.list_active():
            manifest = pack.manifest
            hints = manifest.routing_hints
            if (
                compatible(country_hint, manifest.country, hints.country)
                and compatible(state_hint, manifest.state, hints.state)
                and compatible(industry_hint, manifest.industry, hints.industry)
                and compatible(action_type_hint, manifest.action_type, hints.action_type)
                and evidenced(manifest.country, hints.country)
                and evidenced(manifest.state, hints.state)
                and evidenced(manifest.industry, hints.industry)
                and evidenced(manifest.action_type, hints.action_type)
                and not any(contains_alias(alias) for alias in hints.excluded_states)
                and not any(contains_alias(alias) for alias in hints.excluded_action_types)
            ):
                matches.append(pack)
        if not matches:
            raise CapabilityPackUnsupportedError("项目材料未匹配任何受控试点 Capability Pack")
        if len(matches) != 1:
            raise CapabilityPackRegistryError("项目材料匹配到多个 active Capability Pack")
        return matches[0]


@lru_cache(maxsize=1)
def get_capability_pack_registry() -> CapabilityPackRegistry:
    from app.core.config import get_settings

    return CapabilityPackRegistry(app_env=get_settings().app_env, include_test_fixtures=False)


def load_frozen_capability_pack(
    snapshot: dict,
    *,
    registry: CapabilityPackRegistry | None = None,
) -> LoadedCapabilityPack:
    """Resolve and verify a frozen identity without re-running route matching."""
    active_registry = registry or get_capability_pack_registry()
    pack = active_registry.get_exact(
        str(snapshot.get("capability_pack_id") or ""),
        str(snapshot.get("capability_pack_version") or ""),
        str(snapshot.get("capability_pack_hash") or ""),
    )
    manifest = pack.manifest
    expected = {
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
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise CapabilityPackRegistryError("冻结 snapshot 与 Capability Pack 制品或配置身份不一致")
    return pack
