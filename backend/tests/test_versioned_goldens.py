"""C3.0 characterization: current behavior must match the frozen golden vectors.

Goldens live in tests/goldens/versioned/ and are READ-ONLY: they were generated
from commit efc76e0 (pre-refactor), human-reviewed and committed. Tests compare
CURRENT outputs against the frozen JSON/hash constants — never function-vs-
function. Regenerating goldens requires an explicit approved decision.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.delivery_assurance import (
    DeliveryEvidenceObject,
    DeploymentEvidence,
    LegalContentCertification,
    LegalExpertCredential,
    ScenarioExpertAttestation,
    ScenarioUATAcceptance,
)
from app.models.mechanism import ClaimRecord, FactRecord
from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User
from app.schemas.mechanism import ClaimCompileRequest
from app.services import mechanism_service
from app.services.answerability_gate_service import require_delivery_answerability
from app.services.delivery_assurance_service import (
    _delivery_evidence_manifest,
    _release_body,
    build_delivery_snapshot,
)
from app.services.generation_guard import GenerationConfig, stable_hash

GOLDEN_DIR = Path(__file__).parent / "goldens" / "versioned"
FIXED_DT = datetime.fromisoformat("2026-07-01T12:00:00+00:00")

_TUPLE_FIELDS = {
    "issue_modules",
    "compliance_dimensions",
    "selected_issue_codes",
    "playbook_suggestion_codes",
}


def _load(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


class _UuidSeq:
    """Same deterministic sequence the golden generator used."""

    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"00000000-0000-4000-8000-{self.n:012d}"


@pytest.fixture()
def golden_state(tmp_path: Path, monkeypatch):
    """Rebuild the synthetic DB state exactly as recorded in the golden inputs."""

    compiler_golden = _load("compiler_v0_2.json")
    inputs = compiler_golden["inputs"]
    monkeypatch.setattr(
        mechanism_service.versioned_registry,
        "CURRENT_COMPILER_WRITE_VERSION",
        "0.2",
    )
    monkeypatch.setattr(
        mechanism_service.versioned_registry,
        "CURRENT_COVERAGE_PROOF_WRITE_VERSION",
        "0.1",
    )
    monkeypatch.setattr(mechanism_service, "uuid4", _UuidSeq())

    engine = create_engine(
        f"sqlite:///{tmp_path / 'golden.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add_all(
        [
            User(id=1, email="biz@example.invalid", full_name="Biz", role="business", disclaimer_accepted=True),
            User(id=2, email="legal@example.invalid", full_name="Legal", role="legal", disclaimer_accepted=True),
        ]
    )
    scenario = InvestigationScenario(
        id=1, user_id=1, project_name="Golden scenario", country="zz",
        state="zz-state", city="zz-city", industry="ind", action_type="act",
        description="synthetic golden scenario", compliance_dimensions=["environment"],
        status="generated", is_demo=False, scope_snapshot_hash="ab" * 32,
    )
    scenario.checklist = ComplianceChecklist(
        scenario_id=1, title="Golden checklist", version="v0.1",
        payload=json.loads(json.dumps(inputs["payload"])), total_items=3,
    )
    db.add(scenario)
    for spec in inputs["facts"]:
        db.add(FactRecord(scenario_id=1, created_by=1, **spec))
    db.commit()

    legal = db.get(User, 2)
    request = ClaimCompileRequest(drafts=inputs["drafts"])
    compilation, claims = mechanism_service.compile_claims(
        db, scenario=scenario, request=request, user=legal
    )
    yield {
        "db": db,
        "scenario": scenario,
        "legal": legal,
        "compilation": compilation,
        "claims": claims,
        "golden": compiler_golden,
    }
    db.close()


def _confirm_env_claim(state) -> None:
    db = state["db"]
    env_claim = next(c for c in state["claims"] if c.checklist_code == "ENV-001")
    mechanism_service.confirm_claim(
        db, claim=env_claim, decision="confirmed",
        confirmation_note="confirmed by golden counsel", user=state["legal"],
    )
    db.execute(
        update(ClaimRecord)
        .where(ClaimRecord.id == env_claim.id)
        .values(confirmed_at=FIXED_DT, updated_at=FIXED_DT)
    )
    db.flush()


def test_compiler_v0_2_matches_golden(golden_state) -> None:
    expected = golden_state["golden"]["expected"]
    compilation = golden_state["compilation"]
    assert compilation.compiler_version == expected["compiler_version"] == "0.2"
    assert compilation.input_snapshot == expected["input_snapshot"]
    assert compilation.input_hash == expected["input_hash"]
    assert compilation.output_hash == expected["output_hash"]
    assert compilation.denominator_count == expected["denominator_count"]
    assert compilation.ready_count == expected["ready_count"]
    assert compilation.refused_count == expected["refused_count"]
    stored_values = [
        {
            "checklist_code": c.checklist_code,
            "statement": c.statement,
            "status": c.status,
            "fact_refs": list(c.fact_refs or []),
            "evidence_refs": list(c.evidence_refs or []),
            "reason_codes": list(c.reason_codes or []),
        }
        for c in golden_state["claims"]
    ]
    assert stored_values == expected["claim_values"]
    # Hash constants are independently reproducible from the frozen bodies.
    assert stable_hash(expected["input_snapshot"]) == expected["input_hash"]
    assert stable_hash(expected["claim_values"]) == expected["output_hash"]


def test_coverage_proof_v0_1_matches_golden(golden_state) -> None:
    expected = _load("coverage_proof_v0_1.json")["expected"]
    _confirm_env_claim(golden_state)
    db = golden_state["db"]
    proof = mechanism_service.create_coverage_proof(
        db,
        scenario=golden_state["scenario"],
        compilation=golden_state["compilation"],
        claims=mechanism_service.compilation_claims(db, golden_state["compilation"].id),
        denominator_ref=expected["denominator_ref"],
        user=golden_state["legal"],
    )
    assert proof.proof == expected["proof_body"]
    assert proof.proof_hash == expected["proof_hash"]
    assert proof.denominator_hash == expected["denominator_hash"]
    assert proof.denominator_count == expected["denominator_count"]
    assert proof.covered_count == expected["covered_count"]
    assert proof.uncovered_count == expected["uncovered_count"]
    assert proof.unanswerable_count == expected["unanswerable_count"]
    assert proof.proof["schema_version"] == "0.1"
    assert stable_hash(expected["proof_body"]) == expected["proof_hash"]


def test_answerability_v1_0_matches_golden(golden_state) -> None:
    expected = _load("answerability_v1_0.json")["expected"]
    _confirm_env_claim(golden_state)
    db = golden_state["db"]
    mechanism_service.create_coverage_proof(
        db,
        scenario=golden_state["scenario"],
        compilation=golden_state["compilation"],
        claims=mechanism_service.compilation_claims(db, golden_state["compilation"].id),
        denominator_ref="manual:golden-denominator",
        user=golden_state["legal"],
    )
    gate = require_delivery_answerability(db, scenario=golden_state["scenario"])
    assert gate == expected["gate_payload"]
    assert gate["gate_version"] == "1.0"
    assert gate["provisional_evidence_promoted"] is False


def test_delivery_snapshot_and_release_match_golden(golden_state) -> None:
    golden = _load("delivery_release_v1_1.json")
    expected = golden["expected"]
    inputs = golden["inputs"]
    _confirm_env_claim(golden_state)
    db = golden_state["db"]
    mechanism_service.create_coverage_proof(
        db,
        scenario=golden_state["scenario"],
        compilation=golden_state["compilation"],
        claims=mechanism_service.compilation_claims(db, golden_state["compilation"].id),
        denominator_ref="manual:golden-denominator",
        user=golden_state["legal"],
    )
    config_kwargs = dict(inputs["generation_config_kwargs"])
    for key in _TUPLE_FIELDS:
        config_kwargs[key] = tuple(config_kwargs[key])
    config_kwargs["code_adjustments"] = tuple(
        tuple(item) for item in config_kwargs["code_adjustments"]
    )
    snapshot = build_delivery_snapshot(
        db, scenario=golden_state["scenario"], generation_config=GenerationConfig(**config_kwargs)
    )
    assert snapshot == expected["delivery_snapshot"]
    assert stable_hash(snapshot) == expected["snapshot_hash"]
    assert snapshot["schema_version"] == "1.0"
    assert snapshot["mechanism"]["answerability_gate"]["gate_version"] == "1.0"

    chain = inputs["release_chain"]
    dt_fields = inputs["datetime_fields"]

    def instantiate(model, key: str):
        spec = dict(chain[key])
        for field in dt_fields.get(key, []):
            if spec.get(field) is not None:
                spec[field] = datetime.fromisoformat(spec[field])
        return model(**spec)

    evidence_objects = []
    for raw in chain["evidence_objects"]:
        spec = dict(raw)
        for field in dt_fields["evidence_objects"]:
            if spec.get(field) is not None:
                spec[field] = datetime.fromisoformat(spec[field])
        evidence_objects.append(DeliveryEvidenceObject(**spec))

    release_body = _release_body(
        scenario_id=1,
        snapshot_hash=expected["snapshot_hash"],
        attestation=instantiate(ScenarioExpertAttestation, "attestation"),
        acceptance=instantiate(ScenarioUATAcceptance, "acceptance"),
        deployment=instantiate(DeploymentEvidence, "deployment"),
        content_certification=instantiate(LegalContentCertification, "content_certification"),
        scenario_credential=instantiate(LegalExpertCredential, "scenario_credential"),
        primary_credential=instantiate(LegalExpertCredential, "primary_credential"),
        secondary_credential=instantiate(LegalExpertCredential, "secondary_credential"),
        evidence_objects=evidence_objects,
        release_note=chain["release_note"],
        released_by=chain["released_by"],
        released_at=datetime.fromisoformat(chain["released_at"]),
        expires_at=datetime.fromisoformat(chain["expires_at"]),
    )
    assert release_body == expected["release_body"]
    assert stable_hash(release_body) == expected["release_hash"]
    assert release_body["schema_version"] == "1.1"
    assert _delivery_evidence_manifest(evidence_objects) == expected["evidence_manifest"]
    # Evidence manifest is sorted by object id regardless of input order.
    assert [item["id"] for item in expected["evidence_manifest"]] == sorted(
        item["id"] for item in expected["evidence_manifest"]
    )


def test_goldens_are_frozen_files() -> None:
    """The four golden files must exist and carry their frozen unit versions."""

    versions = {
        "compiler_v0_2.json": ("claim_compiler", "0.2"),
        "coverage_proof_v0_1.json": ("coverage_proof", "0.1"),
        "answerability_v1_0.json": ("answerability_gate", "1.0"),
    }
    for name, (unit, version) in versions.items():
        meta = _load(name)["_meta"]
        assert meta["unit"] == unit
        assert meta.get("version") == version
    release_meta = _load("delivery_release_v1_1.json")["_meta"]
    assert release_meta["versions"] == {
        "delivery_snapshot": "1.0",
        "delivery_release": "1.1",
    }
