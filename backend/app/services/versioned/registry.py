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
from app.services.versioned.coverage_proof import v0_1 as coverage_proof_v0_1


class VersionedRegistryError(ValueError):
    pass


class DuplicateVersionError(VersionedRegistryError):
    pass


class UnsupportedVersionError(VersionedRegistryError):
    def __init__(self, unit: str, version: object) -> None:
        self.unit = unit
        self.version = version
        super().__init__(f"未注册的 {unit} 版本：{version!r}")


class UnsupportedCombinationError(VersionedRegistryError):
    def __init__(self, compiler_version: object, proof_version: object) -> None:
        self.compiler_version = compiler_version
        self.proof_version = proof_version
        super().__init__(
            f"不受支持的版本组合：compiler {compiler_version!r} + proof {proof_version!r}"
        )


class VersionedRegistryConfigurationError(VersionedRegistryError):
    """The registry itself is misconfigured; refuse to operate, never repair."""


CURRENT_COMPILER_WRITE_VERSION = "0.2"
CURRENT_COVERAGE_PROOF_WRITE_VERSION = "0.1"


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


@dataclass(frozen=True)
class CoverageProofReader:
    """One frozen coverage-proof schema version."""

    version: str
    build_proof_body: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]]
    hash_payload: Callable[[Any], str]


_COVERAGE_PROOF_V0_1 = CoverageProofReader(
    version=coverage_proof_v0_1.VERSION,
    build_proof_body=coverage_proof_v0_1.build_proof_body,
    hash_payload=coverage_proof_v0_1.hash_payload,
)


SUPPORTED_COVERAGE_PROOF_READERS: Mapping[str, CoverageProofReader] = build_unique_version_map(
    "coverage_proof",
    (
        ("0.1", _COVERAGE_PROOF_V0_1),
    ),
)


def build_unique_combination_set(
    entries: Iterable[tuple[str, str]]
) -> frozenset[tuple[str, str]]:
    """Explicit compatibility pairs; duplicates are a configuration error."""

    pairs: set[tuple[str, str]] = set()
    for pair in entries:
        if pair in pairs:
            raise DuplicateVersionError(f"版本组合重复注册：{pair}")
        pairs.add(pair)
    if not pairs:
        raise VersionedRegistryError("版本兼容矩阵不得为空")
    return frozenset(pairs)


SUPPORTED_COMPILER_PROOF_COMBINATIONS: frozenset[tuple[str, str]] = (
    build_unique_combination_set(
        (
            ("0.2", "0.1"),
        )
    )
)


def get_coverage_reader(version: object) -> CoverageProofReader:
    """Exact lookup by the persisted proof schema version. No fallback."""

    if not isinstance(version, str) or version not in SUPPORTED_COVERAGE_PROOF_READERS:
        raise UnsupportedVersionError("coverage_proof", version)
    return SUPPORTED_COVERAGE_PROOF_READERS[version]


def require_supported_combination(
    compiler_version: str,
    proof_version: str,
    *,
    combinations: frozenset[tuple[str, str]] | None = None,
) -> None:
    """Registered versions may still be mutually incompatible; fail closed."""

    allowed = SUPPORTED_COMPILER_PROOF_COMBINATIONS if combinations is None else combinations
    if (compiler_version, proof_version) not in allowed:
        raise UnsupportedCombinationError(compiler_version, proof_version)


def current_coverage_proof_writer() -> CoverageProofReader:
    return get_coverage_reader(CURRENT_COVERAGE_PROOF_WRITE_VERSION)


def validate_registry_configuration(
    *,
    compiler_readers: Mapping[str, Any],
    proof_readers: Mapping[str, Any],
    combinations: frozenset[tuple[str, str]],
    current_compiler_write_version: str,
    current_proof_write_version: str,
    required_compiler_versions: tuple[str, ...] = ("0.2",),
    required_proof_versions: tuple[str, ...] = ("0.1",),
    required_combinations: tuple[tuple[str, str], ...] = (("0.2", "0.1"),),
) -> None:
    """Pure self-consistency check. Raises on any mismatch; never repairs,
    ignores or falls back. The production registry runs this once at module
    load; tests may pass isolated mappings to exercise every failure mode."""

    for unit, readers in (("claim_compiler", compiler_readers), ("coverage_proof", proof_readers)):
        for key, reader in readers.items():
            if getattr(reader, "version", None) != key:
                raise VersionedRegistryConfigurationError(
                    f"{unit} registry key {key!r} 与 reader.version {getattr(reader, 'version', None)!r} 不一致"
                )
    if current_compiler_write_version not in compiler_readers:
        raise VersionedRegistryConfigurationError(
            f"CURRENT_COMPILER_WRITE_VERSION {current_compiler_write_version!r} 未注册"
        )
    if current_proof_write_version not in proof_readers:
        raise VersionedRegistryConfigurationError(
            f"CURRENT_COVERAGE_PROOF_WRITE_VERSION {current_proof_write_version!r} 未注册"
        )
    for compiler_version, proof_version in combinations:
        if compiler_version not in compiler_readers:
            raise VersionedRegistryConfigurationError(
                f"兼容矩阵引用了未注册的 compiler 版本：{compiler_version!r}"
            )
        if proof_version not in proof_readers:
            raise VersionedRegistryConfigurationError(
                f"兼容矩阵引用了未注册的 proof 版本：{proof_version!r}"
            )
    for version in required_compiler_versions:
        if version not in compiler_readers:
            raise VersionedRegistryConfigurationError(f"必需的历史 compiler 版本缺失：{version!r}")
    for version in required_proof_versions:
        if version not in proof_readers:
            raise VersionedRegistryConfigurationError(f"必需的历史 proof 版本缺失：{version!r}")
    for pair in required_combinations:
        if pair not in combinations:
            raise VersionedRegistryConfigurationError(f"必需的历史版本组合缺失：{pair!r}")


# One-time production self-check at module load (D-0008: append-only,
# fail-closed configuration; no automatic repair).
validate_registry_configuration(
    compiler_readers=SUPPORTED_COMPILER_READERS,
    proof_readers=SUPPORTED_COVERAGE_PROOF_READERS,
    combinations=SUPPORTED_COMPILER_PROOF_COMBINATIONS,
    current_compiler_write_version=CURRENT_COMPILER_WRITE_VERSION,
    current_proof_write_version=CURRENT_COVERAGE_PROOF_WRITE_VERSION,
)


def current_compiler_writer() -> CompilerReader:
    return get_compiler_reader(CURRENT_COMPILER_WRITE_VERSION)


def compiler_build_input_snapshot(
    db: Session, *, scenario: Any, drafts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Write-path helper: always the current write version."""

    return current_compiler_writer().build_input_snapshot(db, scenario=scenario, drafts=drafts)
