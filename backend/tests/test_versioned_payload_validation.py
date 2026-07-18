"""C3-A.1: persisted-JSON structure validation, registry self-check and
writer-version single source of truth.

Adversarial premise: an attacker with raw SQL can rewrite persisted JSON AND
recompute the matching hashes. Structural validation at the gate boundary must
still fail closed with 422 + stable reason codes — never an uncaught 500.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from sqlalchemy import update

from app.models.mechanism import ClaimCompilation, CoverageProof
from app.models.scenario import ComplianceChecklist
from app.schemas.mechanism import ClaimCompileRequest
from app.services import mechanism_service
from app.services.answerability_gate_service import (
    AnswerabilityGateError,
    require_delivery_answerability,
)
from app.services.versioned import registry as versioned_registry
from app.services.versioned.canonical_hash import canonical_hash_v1
from app.services.versioned.registry import (
    VersionedRegistryConfigurationError,
    validate_registry_configuration,
)

from test_versioned_goldens import golden_state  # noqa: F401, F811  (shared fixture)
from test_versioned_registry import _prepare_gate_state  # noqa: F401


def _gate_error(db, scenario) -> AnswerabilityGateError:
    with pytest.raises(AnswerabilityGateError) as exc:
        require_delivery_answerability(db, scenario=scenario)
    return exc.value


def _set_compilation(db, compilation_id: str, **values) -> None:
    db.execute(
        update(ClaimCompilation).where(ClaimCompilation.id == compilation_id).values(**values)
    )
    db.flush()
    db.expire_all()


def _set_proof(db, scenario_id: int, **values) -> None:
    proof = (
        db.query(CoverageProof)
        .filter(CoverageProof.scenario_id == scenario_id)
        .order_by(CoverageProof.created_at.desc())
        .first()
    )
    db.execute(update(CoverageProof).where(CoverageProof.id == proof.id).values(**values))
    db.flush()
    db.expire_all()


# --- compiler snapshot structure --------------------------------------------


def test_input_snapshot_as_list_with_matching_hash_is_422(golden_state) -> None:
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    tampered = [1, 2, 3]
    _set_compilation(
        db,
        golden_state["compilation"].id,
        input_snapshot=tampered,
        input_hash=canonical_hash_v1(tampered),
    )
    error = _gate_error(db, golden_state["scenario"])
    assert error.http_status == 422
    assert error.reason_codes == ("compiler_input_snapshot_invalid",)


@pytest.mark.parametrize(
    "bad_drafts",
    [
        ["scalar-draft"],
        [{"checklist_code": "ENV-001"}],
        [{"checklist_code": 7, "statement": "x"}],
        [{"checklist_code": "ENV-001", "statement": "x", "fact_refs": "not-a-list"}],
    ],
)
def test_malformed_drafts_with_recomputed_hash_are_422(golden_state, bad_drafts) -> None:
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    compilation = golden_state["compilation"]
    snapshot = json.loads(json.dumps(compilation.input_snapshot))
    snapshot["drafts"] = bad_drafts
    _set_compilation(
        db,
        compilation.id,
        input_snapshot=snapshot,
        input_hash=canonical_hash_v1(snapshot),
    )
    error = _gate_error(db, golden_state["scenario"])
    assert error.http_status == 422
    assert error.reason_codes == ("compiler_input_snapshot_invalid",)


def test_corrupt_current_checklist_payload_is_422(golden_state) -> None:
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    db.execute(
        update(ComplianceChecklist)
        .where(ComplianceChecklist.scenario_id == 1)
        .values(payload=["not-an-object"])
    )
    db.flush()
    db.expire_all()
    error = _gate_error(db, golden_state["scenario"])
    assert error.http_status == 422
    assert error.reason_codes == ("compiler_current_payload_invalid",)


# --- coverage proof structure ------------------------------------------------


@pytest.mark.parametrize("bad_body", [[["x"]], "just-a-string", [1, 2]])
def test_non_object_proof_body_with_matching_hash_is_422(golden_state, bad_body) -> None:
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    _set_proof(db, 1, proof=bad_body, proof_hash=canonical_hash_v1(bad_body))
    error = _gate_error(db, golden_state["scenario"])
    assert error.http_status == 422
    assert error.reason_codes == ("coverage_proof_schema_unsupported",)


def test_numeric_proof_schema_version_is_422(golden_state) -> None:
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    proof = (
        db.query(CoverageProof).filter(CoverageProof.scenario_id == 1).first()
    )
    body = json.loads(json.dumps(proof.proof))
    body["schema_version"] = 123
    _set_proof(db, 1, proof=body, proof_hash=canonical_hash_v1(body))
    error = _gate_error(db, golden_state["scenario"])
    assert error.http_status == 422
    assert error.reason_codes == ("coverage_proof_schema_unsupported",)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda body: body.__setitem__("uncovered", ["bad"]),
        lambda body: body.__setitem__("denominator", [["bad"]]),
        lambda body: body.__setitem__("covered_checklist_codes", "ENV-001"),
        lambda body: body.__setitem__(
            "uncovered", [{"checklist_code": "X", "status": 5, "unanswerable_reasons": []}]
        ),
    ],
)
def test_known_schema_with_illegal_body_structure_is_422(golden_state, mutate) -> None:
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    proof = db.query(CoverageProof).filter(CoverageProof.scenario_id == 1).first()
    body = json.loads(json.dumps(proof.proof))
    mutate(body)
    denominator = body.get("denominator")
    _set_proof(
        db,
        1,
        proof=body,
        proof_hash=canonical_hash_v1(body),
        denominator_hash=canonical_hash_v1(denominator),
        denominator_count=len(denominator) if isinstance(denominator, list) else 0,
        uncovered_count=len(body.get("uncovered") or []),
    )
    error = _gate_error(db, golden_state["scenario"])
    assert error.http_status == 422
    assert error.reason_codes == ("coverage_proof_body_invalid",)


# --- real-gate incompatible combination --------------------------------------


def test_real_gate_blocks_excluded_known_combination(golden_state, monkeypatch) -> None:
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    monkeypatch.setattr(
        versioned_registry,
        "SUPPORTED_COMPILER_PROOF_COMBINATIONS",
        frozenset({("9.9", "9.9")}),
    )
    error = _gate_error(db, golden_state["scenario"])
    assert error.http_status == 422
    assert error.reason_codes == ("version_combination_unsupported:0.2+0.1",)


# --- registry configuration self-check ---------------------------------------


class _FakeReader:
    def __init__(self, version: str) -> None:
        self.version = version


def _config_kwargs(**overrides):
    kwargs = dict(
        compiler_readers={"0.2": _FakeReader("0.2")},
        proof_readers={"0.1": _FakeReader("0.1")},
        combinations=frozenset({("0.2", "0.1")}),
        current_compiler_write_version="0.2",
        current_proof_write_version="0.1",
    )
    kwargs.update(overrides)
    return kwargs


def test_registry_key_version_mismatch_fails_configuration() -> None:
    with pytest.raises(VersionedRegistryConfigurationError, match="不一致"):
        validate_registry_configuration(
            **_config_kwargs(compiler_readers={"0.2": _FakeReader("0.9")})
        )


def test_unregistered_current_write_version_fails_configuration() -> None:
    with pytest.raises(VersionedRegistryConfigurationError, match="未注册"):
        validate_registry_configuration(**_config_kwargs(current_compiler_write_version="0.3"))
    with pytest.raises(VersionedRegistryConfigurationError, match="未注册"):
        validate_registry_configuration(**_config_kwargs(current_proof_write_version="0.9"))


def test_combination_referencing_unregistered_version_fails_configuration() -> None:
    with pytest.raises(VersionedRegistryConfigurationError, match="兼容矩阵"):
        validate_registry_configuration(
            **_config_kwargs(combinations=frozenset({("0.2", "0.1"), ("0.3", "0.1")}))
        )


def test_missing_required_historical_entries_fail_configuration() -> None:
    with pytest.raises(VersionedRegistryConfigurationError, match="必需的历史"):
        validate_registry_configuration(
            **_config_kwargs(
                compiler_readers={"0.3": _FakeReader("0.3")},
                combinations=frozenset({("0.3", "0.1")}),
                current_compiler_write_version="0.3",
            )
        )
    with pytest.raises(VersionedRegistryConfigurationError, match="必需的历史版本组合"):
        validate_registry_configuration(
            **_config_kwargs(
                combinations=frozenset({("0.2", "0.1")}),
                required_combinations=(("0.2", "0.1"), ("0.2", "0.2")),
            )
        )


def test_production_registry_configuration_is_self_consistent() -> None:
    validate_registry_configuration(
        compiler_readers=versioned_registry.SUPPORTED_COMPILER_READERS,
        proof_readers=versioned_registry.SUPPORTED_COVERAGE_PROOF_READERS,
        combinations=versioned_registry.SUPPORTED_COMPILER_PROOF_COMBINATIONS,
        current_compiler_write_version=versioned_registry.CURRENT_COMPILER_WRITE_VERSION,
        current_proof_write_version=versioned_registry.CURRENT_COVERAGE_PROOF_WRITE_VERSION,
    )


# --- writer version single source of truth -----------------------------------


def test_compile_claims_persists_writer_version_not_module_constant(
    golden_state, monkeypatch
) -> None:
    """The persisted identity must come from writer.version — never from a
    copied constant. The synthetic 0.3 writer reuses the frozen 0.2 behavior
    and is NOT added to the production registry."""

    synthetic_writer = replace(versioned_registry.current_compiler_writer(), version="0.3")
    monkeypatch.setattr(
        versioned_registry, "current_compiler_writer", lambda: synthetic_writer
    )
    db = golden_state["db"]
    request = ClaimCompileRequest(drafts=golden_state["golden"]["inputs"]["drafts"])
    compilation, _claims = mechanism_service.compile_claims(
        db, scenario=golden_state["scenario"], request=request, user=golden_state["legal"]
    )
    assert compilation.compiler_version == "0.3"
    assert compilation.compiler_version != mechanism_service.COMPILER_VERSION
    assert compilation.input_hash == synthetic_writer.hash_payload(compilation.input_snapshot)
    expected_values = synthetic_writer.build_claim_values(
        synthetic_writer.checklist_items(golden_state["scenario"].checklist.payload),
        drafts=compilation.input_snapshot["drafts"],
        facts=compilation.input_snapshot["facts"],
        evidence=compilation.input_snapshot["evidence"],
    )
    assert compilation.output_hash == synthetic_writer.hash_payload(expected_values)
