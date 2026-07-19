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
from app.services.versioned.claim_compiler import v0_3 as claim_compiler_v0_3
from app.services.versioned.coverage_proof import v0_1 as coverage_proof_v0_1
from app.services.versioned.coverage_proof import v0_2 as coverage_proof_v0_2
from app.services.versioned.delivery_release import v1_1 as delivery_release_v1_1
from app.services.versioned.delivery_snapshot import v1_0 as delivery_snapshot_v1_0


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


CURRENT_COMPILER_WRITE_VERSION = "0.3"
CURRENT_COVERAGE_PROOF_WRITE_VERSION = "0.2"
CURRENT_DELIVERY_SNAPSHOT_WRITE_VERSION = "1.0"
CURRENT_DELIVERY_RELEASE_WRITE_VERSION = "1.1"


@dataclass(frozen=True)
class CompilerReader:
    """One frozen compiler version: builders plus its frozen hash algorithm."""

    version: str
    build_input_snapshot: Callable[..., dict[str, Any]]
    build_claim_values: Callable[..., list[dict[str, Any]]]
    checklist_items: Callable[[dict[str, Any]], list[dict[str, Any]]]
    hash_payload: Callable[[Any], str]
    build_denominator: Callable[..., list[dict[str, Any]]] | None = None
    build_research_values: Callable[..., list[dict[str, Any]]] | None = None
    build_output_payload: Callable[..., Any] | None = None


_COMPILER_V0_2 = CompilerReader(
    version=claim_compiler_v0_2.VERSION,
    build_input_snapshot=claim_compiler_v0_2.build_input_snapshot,
    build_claim_values=claim_compiler_v0_2.build_claim_values,
    checklist_items=claim_compiler_v0_2.checklist_items,
    hash_payload=claim_compiler_v0_2.hash_payload,
)

_COMPILER_V0_3 = CompilerReader(
    version=claim_compiler_v0_3.VERSION,
    build_input_snapshot=claim_compiler_v0_3.build_input_snapshot,
    build_claim_values=claim_compiler_v0_3.build_claim_values,
    checklist_items=claim_compiler_v0_3.checklist_items,
    hash_payload=claim_compiler_v0_3.hash_payload,
    build_denominator=claim_compiler_v0_3.build_denominator,
    build_research_values=claim_compiler_v0_3.build_research_values,
    build_output_payload=claim_compiler_v0_3.build_output_payload,
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
        ("0.3", _COMPILER_V0_3),
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
    requires_research_items: bool = False
    validate_body_structure: Callable[[dict[str, Any]], bool] | None = None
    stored_counts: Callable[[dict[str, Any]], tuple[int, int, int, int]] | None = None


_COVERAGE_PROOF_V0_1 = CoverageProofReader(
    version=coverage_proof_v0_1.VERSION,
    build_proof_body=coverage_proof_v0_1.build_proof_body,
    hash_payload=coverage_proof_v0_1.hash_payload,
)

_COVERAGE_PROOF_V0_2 = CoverageProofReader(
    version=coverage_proof_v0_2.VERSION,
    build_proof_body=coverage_proof_v0_2.build_proof_body,
    hash_payload=coverage_proof_v0_2.hash_payload,
    requires_research_items=True,
    validate_body_structure=coverage_proof_v0_2.validate_body_structure,
    stored_counts=coverage_proof_v0_2.stored_counts,
)


SUPPORTED_COVERAGE_PROOF_READERS: Mapping[str, CoverageProofReader] = build_unique_version_map(
    "coverage_proof",
    (
        ("0.1", _COVERAGE_PROOF_V0_1),
        ("0.2", _COVERAGE_PROOF_V0_2),
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
            ("0.3", "0.2"),
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


def coverage_proof_writer_for_compiler(compiler_version: str) -> CoverageProofReader:
    """Choose the unique explicitly compatible writer for a compilation.

    This is write routing only. Persisted proofs are always read by their own
    schema identity and never use this helper.
    """

    current = current_coverage_proof_writer()
    if (compiler_version, current.version) in SUPPORTED_COMPILER_PROOF_COMBINATIONS:
        return current
    compatible = sorted(
        proof
        for compiler, proof in SUPPORTED_COMPILER_PROOF_COMBINATIONS
        if compiler == compiler_version
    )
    if len(compatible) != 1:
        raise UnsupportedCombinationError(compiler_version, current.version)
    return get_coverage_reader(compatible[0])


@dataclass(frozen=True)
class DeliverySnapshotReader:
    version: str
    gate_version: str
    build_gate_payload: Callable[..., dict[str, Any]]
    build_mechanism_payload: Callable[..., dict[str, Any]]
    build_snapshot_payload: Callable[..., dict[str, Any]]
    hash_payload: Callable[[Any], str]


_DELIVERY_SNAPSHOT_V1_0 = DeliverySnapshotReader(
    version=delivery_snapshot_v1_0.VERSION,
    gate_version=delivery_snapshot_v1_0.GATE_VERSION,
    build_gate_payload=delivery_snapshot_v1_0.build_gate_payload,
    build_mechanism_payload=delivery_snapshot_v1_0.build_mechanism_payload,
    build_snapshot_payload=delivery_snapshot_v1_0.build_snapshot_payload,
    hash_payload=delivery_snapshot_v1_0.hash_payload,
)

SUPPORTED_DELIVERY_SNAPSHOT_READERS: Mapping[str, DeliverySnapshotReader] = (
    build_unique_version_map("delivery_snapshot", (("1.0", _DELIVERY_SNAPSHOT_V1_0),))
)


def get_delivery_snapshot_reader(version: object) -> DeliverySnapshotReader:
    if not isinstance(version, str) or version not in SUPPORTED_DELIVERY_SNAPSHOT_READERS:
        raise UnsupportedVersionError("delivery_snapshot", version)
    return SUPPORTED_DELIVERY_SNAPSHOT_READERS[version]


def current_delivery_snapshot_writer() -> DeliverySnapshotReader:
    return get_delivery_snapshot_reader(CURRENT_DELIVERY_SNAPSHOT_WRITE_VERSION)


@dataclass(frozen=True)
class DeliveryReleaseReader:
    version: str
    build_release_body: Callable[..., dict[str, Any]]
    credential_evidence: Callable[[Any], dict[str, Any]]
    attestation_evidence: Callable[[Any], dict[str, Any]]
    uat_evidence: Callable[[Any], dict[str, Any]]
    content_certification_evidence: Callable[[Any], dict[str, Any]]
    deployment_evidence_manifest: Callable[[Any], dict[str, Any]]
    delivery_evidence_manifest: Callable[[list[Any]], list[dict[str, Any]]]
    hash_payload: Callable[[Any], str]


_DELIVERY_RELEASE_V1_1 = DeliveryReleaseReader(
    version=delivery_release_v1_1.VERSION,
    build_release_body=delivery_release_v1_1.build_release_body,
    credential_evidence=delivery_release_v1_1.credential_evidence,
    attestation_evidence=delivery_release_v1_1.attestation_evidence,
    uat_evidence=delivery_release_v1_1.uat_evidence,
    content_certification_evidence=delivery_release_v1_1.content_certification_evidence,
    deployment_evidence_manifest=delivery_release_v1_1.deployment_evidence_manifest,
    delivery_evidence_manifest=delivery_release_v1_1.delivery_evidence_manifest,
    hash_payload=delivery_release_v1_1.hash_payload,
)

SUPPORTED_DELIVERY_RELEASE_READERS: Mapping[str, DeliveryReleaseReader] = (
    build_unique_version_map("delivery_release", (("1.1", _DELIVERY_RELEASE_V1_1),))
)


def get_delivery_release_reader(version: object) -> DeliveryReleaseReader:
    if not isinstance(version, str) or version not in SUPPORTED_DELIVERY_RELEASE_READERS:
        raise UnsupportedVersionError("delivery_release", version)
    return SUPPORTED_DELIVERY_RELEASE_READERS[version]


def current_delivery_release_writer() -> DeliveryReleaseReader:
    return get_delivery_release_reader(CURRENT_DELIVERY_RELEASE_WRITE_VERSION)


SUPPORTED_DELIVERY_COMBINATIONS: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        ("0.2", "0.1", "1.0", "1.1"),
        ("0.3", "0.2", "1.0", "1.1"),
    }
)


def require_supported_delivery_combination(
    compiler_version: str,
    proof_version: str,
    snapshot_version: str,
    release_version: str,
) -> None:
    combination = (compiler_version, proof_version, snapshot_version, release_version)
    if combination not in SUPPORTED_DELIVERY_COMBINATIONS:
        raise VersionedRegistryConfigurationError(
            "不受支持的 delivery 版本组合：" + "+".join(combination)
        )


def validate_delivery_registry_configuration() -> None:
    for unit, readers, current in (
        ("delivery_snapshot", SUPPORTED_DELIVERY_SNAPSHOT_READERS, CURRENT_DELIVERY_SNAPSHOT_WRITE_VERSION),
        ("delivery_release", SUPPORTED_DELIVERY_RELEASE_READERS, CURRENT_DELIVERY_RELEASE_WRITE_VERSION),
    ):
        if current not in readers:
            raise VersionedRegistryConfigurationError(f"CURRENT {unit} writer {current!r} 未注册")
        for key, reader in readers.items():
            if reader.version != key:
                raise VersionedRegistryConfigurationError(
                    f"{unit} registry key {key!r} 与 reader.version {reader.version!r} 不一致"
                )
    for compiler, proof, snapshot, release in SUPPORTED_DELIVERY_COMBINATIONS:
        if compiler not in SUPPORTED_COMPILER_READERS or proof not in SUPPORTED_COVERAGE_PROOF_READERS:
            raise VersionedRegistryConfigurationError("delivery 兼容矩阵引用未注册机制 reader")
        if snapshot not in SUPPORTED_DELIVERY_SNAPSHOT_READERS or release not in SUPPORTED_DELIVERY_RELEASE_READERS:
            raise VersionedRegistryConfigurationError("delivery 兼容矩阵引用未注册 delivery reader")


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
validate_delivery_registry_configuration()


def current_compiler_writer() -> CompilerReader:
    return get_compiler_reader(CURRENT_COMPILER_WRITE_VERSION)


def compiler_build_input_snapshot(
    db: Session, *, scenario: Any, drafts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Write-path helper: always the current write version."""

    return current_compiler_writer().build_input_snapshot(db, scenario=scenario, drafts=drafts)
