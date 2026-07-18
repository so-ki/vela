"""Static, append-only registry of versioned readers (WS-1C/C3, D-0008/D-0013).

Rules:
- Explicit static mapping only — no entry points, reflection, dynamic import
  or filename scanning.
- Dispatch is by the persisted version string exactly. Never fall back to the
  current writer, the "latest" version or map ordering.
- Historical entries must never be removed; tests/test_versioned_registry.py
  guards the required minimum set.
- ``CURRENT_*_WRITE_VERSION`` is consulted by writers only; readers never use
  it to interpret stored data.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy.orm import Session

from app.services.versioned.claim_compiler import v0_2 as claim_compiler_v0_2


class VersionedRegistryError(ValueError):
    pass


class DuplicateVersionError(VersionedRegistryError):
    pass


class UnsupportedVersionError(VersionedRegistryError):
    def __init__(self, unit: str, version: object) -> None:
        self.unit = unit
        self.version = version
        super().__init__(f"未注册的 {unit} 版本：{version!r}")


CURRENT_COMPILER_WRITE_VERSION = "0.2"


@dataclass(frozen=True)
class CompilerReader:
    """One frozen compiler version: builders plus its frozen hash algorithm."""

    version: str
    build_input_snapshot: Callable[..., dict[str, Any]]
    build_claim_values: Callable[..., list[dict[str, Any]]]
    checklist_items: Callable[[dict[str, Any]], list[dict[str, Any]]]
    hash_payload: Callable[[Any], str]


_COMPILER_V0_2 = CompilerReader(
    version=claim_compiler_v0_2.VERSION,
    build_input_snapshot=claim_compiler_v0_2.build_input_snapshot,
    build_claim_values=claim_compiler_v0_2.build_claim_values,
    checklist_items=claim_compiler_v0_2.checklist_items,
    hash_payload=claim_compiler_v0_2.hash_payload,
)


def build_unique_version_map(
    unit: str, entries: Iterable[tuple[str, Any]]
) -> Mapping[str, Any]:
    """Build a read-only version map; duplicate versions are a config error.

    A plain dict literal would silently keep only the last duplicate key, so
    registries must be constructed through this function.
    """

    mapping: dict[str, Any] = {}
    for version, value in entries:
        if version in mapping:
            raise DuplicateVersionError(f"{unit} 版本重复注册：{version}")
        mapping[version] = value
    if not mapping:
        raise VersionedRegistryError(f"{unit} registry 不得为空")
    return MappingProxyType(mapping)


SUPPORTED_COMPILER_READERS: Mapping[str, CompilerReader] = build_unique_version_map(
    "claim_compiler",
    (
        ("0.2", _COMPILER_V0_2),
    ),
)


def get_compiler_reader(version: object) -> CompilerReader:
    """Exact lookup by the persisted compiler version. No fallback of any kind."""

    if not isinstance(version, str) or version not in SUPPORTED_COMPILER_READERS:
        raise UnsupportedVersionError("claim_compiler", version)
    return SUPPORTED_COMPILER_READERS[version]


def current_compiler_writer() -> CompilerReader:
    return get_compiler_reader(CURRENT_COMPILER_WRITE_VERSION)


def compiler_build_input_snapshot(
    db: Session, *, scenario: Any, drafts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Write-path helper: always the current write version."""

    return current_compiler_writer().build_input_snapshot(db, scenario=scenario, drafts=drafts)
