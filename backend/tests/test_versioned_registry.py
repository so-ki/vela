"""WS-1C/C3-A: versioned reader registry, canonical hash v1 and gate dispatch."""

# ruff: noqa: F811 -- imported pytest fixture names are intentionally requested
# again as test parameters in this module.

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import update

from app.models.mechanism import ClaimCompilation
from app.services import mechanism_service
from app.services.answerability_gate_service import (
    AnswerabilityGateError,
    require_delivery_answerability,
)
from app.services.generation_guard import stable_hash
from app.services.versioned import registry as versioned_registry
from app.services.versioned.canonical_hash import canonical_hash_v1
from app.services.versioned.registry import (
    DuplicateVersionError,
    UnsupportedVersionError,
    build_unique_version_map,
    get_compiler_reader,
)

from test_versioned_goldens import golden_state as _golden_state_fixture  # noqa: F401

GOLDEN_DIR = Path(__file__).parent / "goldens" / "versioned"


def _golden(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


# --- canonical hash v1 -------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"中文键": "中文值：许可路径", "nested": {"z": 1, "a": None}},
        {"b": 2, "a": 1},
        [3, 1, 2, [True, False, None]],
        {"dt": datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)},
        {"none": None, "bool": True, "int": 7, "float": 1.5},
        {"outer": [{"inner": {"深": "层"}}]},
    ],
)
def test_canonical_hash_v1_equals_stable_hash(payload) -> None:
    assert canonical_hash_v1(payload) == stable_hash(payload)


def test_canonical_hash_v1_reproduces_all_golden_hashes() -> None:
    compiler = _golden("compiler_v0_2.json")["expected"]
    assert canonical_hash_v1(compiler["input_snapshot"]) == compiler["input_hash"]
    assert canonical_hash_v1(compiler["claim_values"]) == compiler["output_hash"]
    proof = _golden("coverage_proof_v0_1.json")["expected"]
    assert canonical_hash_v1(proof["proof_body"]) == proof["proof_hash"]
    assert canonical_hash_v1(proof["proof_body"]["denominator"]) == proof["denominator_hash"]
    release = _golden("delivery_release_v1_1.json")["expected"]
    assert canonical_hash_v1(release["delivery_snapshot"]) == release["snapshot_hash"]
    assert canonical_hash_v1(release["release_body"]) == release["release_hash"]


# --- registry construction guards -------------------------------------------


def test_registry_contains_required_historical_entries() -> None:
    assert "0.2" in versioned_registry.SUPPORTED_COMPILER_READERS
    assert versioned_registry.CURRENT_COMPILER_WRITE_VERSION == "0.2"
    reader = get_compiler_reader("0.2")
    assert reader.version == "0.2"


def test_delivery_registry_contains_frozen_snapshot_and_release_readers() -> None:
    assert versioned_registry.CURRENT_DELIVERY_SNAPSHOT_WRITE_VERSION == "1.0"
    assert versioned_registry.CURRENT_DELIVERY_RELEASE_WRITE_VERSION == "1.1"
    snapshot_reader = versioned_registry.get_delivery_snapshot_reader("1.0")
    release_reader = versioned_registry.get_delivery_release_reader("1.1")
    assert snapshot_reader.version == snapshot_reader.gate_version == "1.0"
    assert release_reader.version == "1.1"
    assert ("0.2", "0.1", "1.0", "1.1") in (
        versioned_registry.SUPPORTED_DELIVERY_COMBINATIONS
    )
    versioned_registry.validate_delivery_registry_configuration()


@pytest.mark.parametrize("bad", ["", "latest", "9.9", None])
def test_unknown_delivery_versions_never_fall_back(bad) -> None:
    with pytest.raises(UnsupportedVersionError):
        versioned_registry.get_delivery_snapshot_reader(bad)
    with pytest.raises(UnsupportedVersionError):
        versioned_registry.get_delivery_release_reader(bad)


def test_duplicate_version_registration_fails() -> None:
    with pytest.raises(DuplicateVersionError):
        build_unique_version_map("unit", (("0.2", object()), ("0.2", object())))


def test_empty_registry_is_a_configuration_error() -> None:
    with pytest.raises(versioned_registry.VersionedRegistryError):
        build_unique_version_map("unit", ())


@pytest.mark.parametrize("bad", ["9.9", "", None, "latest", "0.20"])
def test_unknown_compiler_version_never_falls_back(bad) -> None:
    with pytest.raises(UnsupportedVersionError):
        get_compiler_reader(bad)


def test_current_write_version_not_used_for_reader_selection(monkeypatch) -> None:
    """Simulating a future write default must not change historical dispatch."""

    monkeypatch.setattr(versioned_registry, "CURRENT_COMPILER_WRITE_VERSION", "0.3")
    reader = get_compiler_reader("0.2")
    assert reader.version == "0.2"
    with pytest.raises(UnsupportedVersionError):
        get_compiler_reader("0.3")


def test_future_delivery_write_defaults_do_not_replace_historical_readers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        versioned_registry, "CURRENT_DELIVERY_SNAPSHOT_WRITE_VERSION", "2.0"
    )
    monkeypatch.setattr(
        versioned_registry, "CURRENT_DELIVERY_RELEASE_WRITE_VERSION", "2.0"
    )
    assert versioned_registry.get_delivery_snapshot_reader("1.0").version == "1.0"
    assert versioned_registry.get_delivery_release_reader("1.1").version == "1.1"
    with pytest.raises(UnsupportedVersionError):
        versioned_registry.get_delivery_snapshot_reader("2.0")
    with pytest.raises(UnsupportedVersionError):
        versioned_registry.get_delivery_release_reader("2.0")


# --- gate dispatch (uses the golden fixture state) ---------------------------


def _prepare_gate_state(state) -> None:
    db = state["db"]
    env_claim = next(c for c in state["claims"] if c.checklist_code == "ENV-001")
    mechanism_service.confirm_claim(
        db, claim=env_claim, decision="confirmed",
        confirmation_note="confirmed by golden counsel", user=state["legal"],
    )
    mechanism_service.create_coverage_proof(
        db,
        scenario=state["scenario"],
        compilation=state["compilation"],
        claims=mechanism_service.compilation_claims(db, state["compilation"].id),
        denominator_ref="manual:golden-denominator",
        user=state["legal"],
    )


def test_gate_passes_current_versions_and_ignores_future_write_default(
    _golden_state_fixture, monkeypatch
) -> None:
    golden_state = _golden_state_fixture
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    gate = require_delivery_answerability(db, scenario=golden_state["scenario"])
    assert gate["compiler_version"] == "0.2"

    # A stored 0.2 compilation keeps validating through the 0.2 reader even
    # after the write default moves on (D-0008).
    monkeypatch.setattr(versioned_registry, "CURRENT_COMPILER_WRITE_VERSION", "0.3")
    gate_again = require_delivery_answerability(db, scenario=golden_state["scenario"])
    assert gate_again["compiler_version"] == "0.2"


def test_unknown_stored_compiler_version_fails_closed_422(
    _golden_state_fixture,
) -> None:
    golden_state = _golden_state_fixture
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    db.execute(
        update(ClaimCompilation)
        .where(ClaimCompilation.id == golden_state["compilation"].id)
        .values(compiler_version="9.9")
    )
    db.flush()
    db.expire_all()
    with pytest.raises(AnswerabilityGateError) as exc:
        require_delivery_answerability(db, scenario=golden_state["scenario"])
    assert exc.value.http_status == 422
    assert exc.value.reason_codes == ("compiler_version_unsupported",)


def test_existing_stale_and_tamper_codes_unchanged(_golden_state_fixture) -> None:
    golden_state = _golden_state_fixture
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    scenario = golden_state["scenario"]
    payload = json.loads(json.dumps(scenario.checklist.payload))
    payload["sections_with_legal"][0]["items"][0]["title"] = "环境许可路径（已修改）"
    scenario.checklist.payload = payload
    db.flush()
    with pytest.raises(AnswerabilityGateError) as exc:
        require_delivery_answerability(db, scenario=scenario)
    assert exc.value.http_status == 409
    assert exc.value.reason_codes == ("compiler_input_snapshot_stale",)


# --- coverage proof registry & compatibility matrix (C3.2) -------------------


def test_proof_registry_and_combination_matrix_minimum_entries() -> None:
    assert "0.1" in versioned_registry.SUPPORTED_COVERAGE_PROOF_READERS
    assert versioned_registry.CURRENT_COVERAGE_PROOF_WRITE_VERSION == "0.1"
    assert ("0.2", "0.1") in versioned_registry.SUPPORTED_COMPILER_PROOF_COMBINATIONS
    reader = versioned_registry.get_coverage_reader("0.1")
    assert reader.version == "0.1"


@pytest.mark.parametrize("bad", ["0.9", "", None, "latest"])
def test_unknown_proof_schema_never_falls_back(bad) -> None:
    with pytest.raises(UnsupportedVersionError):
        versioned_registry.get_coverage_reader(bad)


def test_known_but_incompatible_combination_fails_closed() -> None:
    isolated = versioned_registry.build_unique_combination_set((("0.2", "0.1"),))
    versioned_registry.require_supported_combination("0.2", "0.1", combinations=isolated)
    with pytest.raises(versioned_registry.UnsupportedCombinationError):
        versioned_registry.require_supported_combination("0.3", "0.1", combinations=isolated)
    with pytest.raises(versioned_registry.UnsupportedCombinationError):
        versioned_registry.require_supported_combination("0.2", "0.2", combinations=isolated)


def test_duplicate_combination_registration_fails() -> None:
    with pytest.raises(DuplicateVersionError):
        versioned_registry.build_unique_combination_set((("0.2", "0.1"), ("0.2", "0.1")))


def _tamper_proof_body(db, scenario_id: int, mutate) -> None:
    from app.models.mechanism import CoverageProof

    proof = (
        db.query(CoverageProof)
        .filter(CoverageProof.scenario_id == scenario_id)
        .order_by(CoverageProof.created_at.desc())
        .first()
    )
    body = json.loads(json.dumps(proof.proof))
    mutate(body)
    db.execute(
        update(CoverageProof).where(CoverageProof.id == proof.id).values(proof=body)
    )
    db.flush()
    db.expire_all()


def test_missing_proof_schema_version_fails_closed_422(_golden_state_fixture) -> None:
    golden_state = _golden_state_fixture
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    _tamper_proof_body(db, 1, lambda body: body.pop("schema_version"))
    with pytest.raises(AnswerabilityGateError) as exc:
        require_delivery_answerability(db, scenario=golden_state["scenario"])
    assert exc.value.http_status == 422
    assert exc.value.reason_codes == ("coverage_proof_schema_unsupported",)


def test_unknown_proof_schema_version_fails_closed_422(_golden_state_fixture) -> None:
    golden_state = _golden_state_fixture
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    _tamper_proof_body(db, 1, lambda body: body.__setitem__("schema_version", "0.9"))
    with pytest.raises(AnswerabilityGateError) as exc:
        require_delivery_answerability(db, scenario=golden_state["scenario"])
    assert exc.value.http_status == 422
    assert exc.value.reason_codes == ("coverage_proof_schema_unsupported",)


def test_proof_writer_still_writes_0_1(_golden_state_fixture) -> None:
    golden_state = _golden_state_fixture
    _prepare_gate_state(golden_state)
    db = golden_state["db"]
    from app.models.mechanism import CoverageProof

    proof = db.query(CoverageProof).filter(CoverageProof.scenario_id == 1).first()
    assert proof.proof["schema_version"] == "0.1"
    gate = require_delivery_answerability(db, scenario=golden_state["scenario"])
    assert gate["coverage_proof_hash"] == proof.proof_hash
