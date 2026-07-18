from __future__ import annotations

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.deps import get_current_user
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.mechanism import CoverageProof
from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User
from app.services.answerability_gate_service import (
    AnswerabilityGateError,
    require_delivery_answerability,
)
from app.services.generation_guard import stable_hash


@pytest.fixture()
def db_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'mechanism.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    payload = {
        "document_extract": {
            "facts": [
                {
                    "fact_id": "fact:site",
                    "subject": "project",
                    "field": "investment_destination",
                    "value": "Campinas",
                    "source_filename": "proposal.pdf",
                    "source_snippet": "项目地点 Campinas",
                    "verification_status": "business_confirmed",
                }
            ]
        },
        "sections_with_legal": [
            {
                "dimension_id": "environment",
                "items": [
                    {
                        "code": "ENV-001",
                        "title": "环境许可路径",
                        "priority": "high",
                        "legal_hits": [
                            {
                                "id": "law-1",
                                "urn": "urn:lex:br:test",
                                "url": "https://example.invalid/law-1",
                                "grounded": True,
                                "citation_status": "grounded",
                                "review_status": "expert_verified",
                                "requires_review": False,
                            }
                        ],
                    },
                    {
                        "code": "LAND-001",
                        "title": "土地权属核验",
                        "priority": "high",
                        "legal_hits": [],
                    },
                ],
            }
        ],
        "brief": {
            "sections": [
                {
                    "items": [
                        {
                            "code": "ENV-001",
                            "gate_status": "passed",
                            "risk_zh": "该项目的环境许可路径需要按适用法源进一步确认。",
                            "risk_pt": "A rota de licenciamento requer confirmação.",
                        },
                        {"code": "LAND-001", "gate_status": "blocked"},
                    ]
                }
            ]
        },
    }
    with factory() as db:
        db.add_all(
            [
                User(
                    id=1,
                    email="business@example.com",
                    full_name="Business",
                    role="business",
                    disclaimer_accepted=True,
                ),
                User(
                    id=2,
                    email="legal@example.com",
                    full_name="Legal",
                    role="legal",
                    disclaimer_accepted=True,
                ),
            ]
        )
        scenario = InvestigationScenario(
            id=1,
            user_id=1,
            project_name="Mechanism test",
            country="brazil",
            state="sao_paulo",
            city="campinas",
            industry="new_energy",
            action_type="greenfield_plant",
            description="A controlled mechanism-layer test scenario.",
            compliance_dimensions=["environment"],
            status="generated",
            is_demo=False,
        )
        scenario.checklist = ComplianceChecklist(
            scenario_id=1,
            title="Checklist",
            version="v0.1",
            payload=payload,
            total_items=2,
        )
        db.add(scenario)
        db.commit()
    return factory


def _client(factory, user_id: int) -> TestClient:
    app = create_app()

    def override_db():
        with factory() as db:
            yield db

    def override_user():
        with factory() as db:
            return db.get(User, user_id)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app)


def test_material_ledger_requires_legal_confirmation_and_detects_stale_writes(db_factory):
    business = _client(db_factory, 1)
    legal = _client(db_factory, 2)
    path = "/api/v1/scenarios/1/mechanism/material-ledger/block-001"
    try:
        forbidden = business.put(
            path,
            json={
                "source_document": "proposal.pdf",
                "state": "verified",
                "confirmation_note": "checked",
            },
        )
        assert forbidden.status_code == 422
        assert "法务人工确认" in forbidden.text

        created = business.put(
            path,
            json={"source_document": "proposal.pdf", "state": "missing"},
        )
        assert created.status_code == 200, created.text
        assert created.json()["revision"] == 0
        assert created.json()["state_history"][0]["state"] == "missing"

        received = business.put(
            path,
            json={
                "source_document": "proposal.pdf",
                "state": "received",
                "expected_revision": 0,
            },
        )
        assert received.status_code == 200, received.text
        assert received.json()["revision"] == 1

        stale = business.put(
            path,
            json={
                "source_document": "proposal.pdf",
                "state": "ambiguous",
                "expected_revision": 0,
            },
        )
        assert stale.status_code == 409

        missing_note = legal.put(
            path,
            json={
                "source_document": "proposal.pdf",
                "state": "verified",
                "expected_revision": 1,
            },
        )
        assert missing_note.status_code == 422

        verified = legal.put(
            path,
            json={
                "source_document": "proposal.pdf",
                "state": "verified",
                "expected_revision": 1,
                "confirmation_note": "法务逐页核对清晰度与来源。",
            },
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["state"] == "verified"
        assert verified.json()["confirmed_by"] == 2
        assert len(verified.json()["state_history"]) == 3

        terminal_downgrade = business.put(
            path,
            json={
                "source_document": "proposal.pdf",
                "state": "received",
                "expected_revision": 2,
            },
        )
        assert terminal_downgrade.status_code == 422
    finally:
        business.close()
        legal.close()


def test_coverage_task_has_hash_pinned_explicit_denominator(db_factory):
    legal = _client(db_factory, 2)
    path = "/api/v1/scenarios/1/mechanism/coverage-tasks"
    try:
        invalid = legal.post(
            path,
            json={
                "source": "CETESB official directory",
                "state": "received",
                "denominator_ref": "https://example.invalid/directory",
                "denominator_snapshot_hash": "a" * 64,
                "denominator_items": ["A", "B"],
                "covered_items": ["C"],
            },
        )
        assert invalid.status_code == 422

        created = legal.post(
            path,
            json={
                "source": "CETESB official directory",
                "state": "received",
                "denominator_ref": "https://example.invalid/directory",
                "denominator_snapshot_hash": stable_hash(
                    {
                        "source": "CETESB official directory",
                        "denominator_ref": "https://example.invalid/directory",
                        "denominator_items": ["A", "B", "C"],
                    }
                ),
                "denominator_items": ["A", "B", "C"],
                "covered_items": ["A", "C"],
                "note": "官方目录快照下的受控覆盖任务",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["denominator_count"] == 3
        assert created.json()["covered_count"] == 2
        assert created.json()["missing_count"] == 1

        forged_hash = legal.post(
            path,
            json={
                "source": "CETESB official directory",
                "state": "received",
                "denominator_ref": "https://example.invalid/directory",
                "denominator_snapshot_hash": "b" * 64,
                "denominator_items": ["A"],
                "covered_items": [],
            },
        )
        assert forged_hash.status_code == 422
    finally:
        legal.close()


def test_claim_compiler_is_fail_closed_and_proof_counts_only_confirmed_claims(db_factory):
    business = _client(db_factory, 1)
    legal = _client(db_factory, 2)
    compile_path = "/api/v1/scenarios/1/mechanism/claims/compile"
    try:
        created_fact = business.post(
            "/api/v1/scenarios/1/mechanism/facts",
            json={
                "subject": "project",
                "attribute": "investment_destination",
                "value": "Campinas",
                "fact_time": "2026-07-17",
                "block_id": "proposal:1",
                "fact_pack_version": "facts-v0.1",
                "source_document": "proposal.pdf",
            },
        )
        assert created_fact.status_code == 201, created_fact.text
        fact_id = created_fact.json()["id"]
        unconfirmed_compile = legal.post(
            compile_path,
            json={
                "drafts": [
                    {
                        "checklist_code": "ENV-001",
                        "statement": "该项目的环境许可路径需要按适用法源进一步确认。",
                        "fact_refs": [fact_id],
                        "evidence_refs": ["ENV-001:law-1"],
                    }
                ]
            },
        )
        assert unconfirmed_compile.status_code == 201, unconfirmed_compile.text
        assert unconfirmed_compile.json()["claims"][0]["status"] == "refused"
        assert "fact_not_verified" in " ".join(
            unconfirmed_compile.json()["claims"][0]["reason_codes"]
        )

        confirmed_fact = business.post(
            f"/api/v1/scenarios/1/mechanism/facts/{fact_id}/confirm",
            json={"confirmation_note": "业务确认项目地点与提取材料一致。"},
        )
        assert confirmed_fact.status_code == 200, confirmed_fact.text
        assert confirmed_fact.json()["status"] == "business_confirmed"

        denied = business.post(compile_path, json={"drafts": []})
        assert denied.status_code == 403

        compiled = legal.post(
            compile_path,
            json={
                "drafts": [
                    {
                        "checklist_code": "ENV-001",
                        "statement": "该项目的环境许可路径需要按适用法源进一步确认。",
                        "fact_refs": [fact_id],
                        "evidence_refs": ["ENV-001:law-1"],
                    }
                ]
            },
        )
        assert compiled.status_code == 201, compiled.text
        body = compiled.json()
        assert body["denominator_count"] == 2
        assert body["ready_count"] == 1
        assert body["refused_count"] == 1
        by_code = {claim["checklist_code"]: claim for claim in body["claims"]}
        assert by_code["ENV-001"]["status"] == "awaiting_human_confirmation"
        assert by_code["LAND-001"]["status"] == "refused"
        assert "fact_reference_required" in by_code["LAND-001"]["reason_codes"]
        assert body["input_snapshot"]["evidence"]["ENV-001:law-1"]["eligible"] is True

        before_confirmation = legal.post(
            "/api/v1/scenarios/1/mechanism/coverage-proofs",
            json={"compilation_id": body["id"], "denominator_ref": "frozen checklist v0.1"},
        )
        assert before_confirmation.status_code == 201, before_confirmation.text
        assert before_confirmation.json()["covered_count"] == 0
        assert before_confirmation.json()["uncovered_count"] == 2

        with db_factory() as db:
            scenario = db.get(InvestigationScenario, 1)
            with pytest.raises(AnswerabilityGateError) as blocked:
                require_delivery_answerability(db, scenario=scenario)
            assert blocked.value.http_status == 409
            assert "included_claim_not_supported:ENV-001" in blocked.value.reason_codes

        claim_id = by_code["ENV-001"]["id"]
        confirmed = legal.post(
            f"/api/v1/scenarios/1/mechanism/claims/{claim_id}/confirm",
            json={
                "decision": "confirmed",
                "confirmation_note": "法务确认事实与经专家核验法源仅支持该限定表述。",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "supported"

        # The old proof committed the pre-confirmation claim states.  Changing
        # a Claim cannot silently make that proof current.
        with db_factory() as db:
            scenario = db.get(InvestigationScenario, 1)
            with pytest.raises(AnswerabilityGateError) as stale_proof:
                require_delivery_answerability(db, scenario=scenario)
            assert stale_proof.value.http_status == 409
            assert "coverage_proof_stale" in stale_proof.value.reason_codes

        proof = legal.post(
            "/api/v1/scenarios/1/mechanism/coverage-proofs",
            json={"compilation_id": body["id"], "denominator_ref": "frozen checklist v0.1"},
        )
        assert proof.status_code == 201, proof.text
        proof_body = proof.json()
        assert proof_body["denominator_count"] == 2
        assert proof_body["covered_count"] == 1
        assert proof_body["uncovered_count"] == 1
        assert proof_body["unanswerable_count"] == 1
        assert proof_body["proof"]["covered_checklist_codes"] == ["ENV-001"]
        assert proof_body["proof_hash"]

        with db_factory() as db:
            scenario = db.get(InvestigationScenario, 1)
            gate = require_delivery_answerability(db, scenario=scenario)
            assert gate["decision"] == "passed"
            assert gate["compilation_id"] == body["id"]
            assert gate["coverage_proof_id"] == proof_body["id"]

        with db_factory() as db:
            stored_proof = db.get(CoverageProof, proof_body["id"])
            original_hash = stored_proof.proof_hash
            stored_proof.proof_hash = "f" * 64
            db.commit()
            scenario = db.get(InvestigationScenario, 1)
            with pytest.raises(AnswerabilityGateError) as tampered_proof:
                require_delivery_answerability(db, scenario=scenario)
            assert tampered_proof.value.http_status == 422
            assert "coverage_proof_stored_hash_invalid" in tampered_proof.value.reason_codes
            stored_proof.proof_hash = original_hash
            db.commit()

        # A newly registered fact changes the current fact snapshot even if it
        # has not yet been confirmed or referenced.  Delivery must recompile.
        changed_snapshot = business.post(
            "/api/v1/scenarios/1/mechanism/facts",
            json={
                "subject": "project",
                "attribute": "new_fact",
                "value": "new value",
                "fact_time": "2026-07-18",
                "block_id": "proposal:2",
                "fact_pack_version": "facts-v0.2",
            },
        )
        assert changed_snapshot.status_code == 201, changed_snapshot.text
        with db_factory() as db:
            scenario = db.get(InvestigationScenario, 1)
            with pytest.raises(AnswerabilityGateError) as stale_compilation:
                require_delivery_answerability(db, scenario=scenario)
            assert stale_compilation.value.http_status == 409
            assert "compiler_input_snapshot_stale" in stale_compilation.value.reason_codes

        second_decision = legal.post(
            f"/api/v1/scenarios/1/mechanism/claims/{claim_id}/confirm",
            json={"decision": "rejected", "confirmation_note": "repeat decision"},
        )
        assert second_decision.status_code == 409
    finally:
        business.close()
        legal.close()

    with db_factory() as db:
        actions = {entry.action for entry in db.query(AuditLog).all()}
        assert "mechanism.claim_compile" in actions
        assert "mechanism.claim_human_decision" in actions
        assert "mechanism.coverage_proof_create" in actions
        assert "mechanism.fact_create" in actions
        assert "mechanism.fact_business_confirm" in actions


def test_grounded_provisional_evidence_stays_pending_until_legal_confirms(db_factory):
    business = _client(db_factory, 1)
    legal = _client(db_factory, 2)
    try:
        with db_factory() as db:
            checklist = db.query(ComplianceChecklist).filter_by(scenario_id=1).one()
            payload = copy.deepcopy(checklist.payload)
            hit = payload["sections_with_legal"][0]["items"][0]["legal_hits"][0]
            hit["review_status"] = "pending"
            hit["requires_review"] = True
            checklist.payload = payload
            db.commit()

        fact = business.post(
            "/api/v1/scenarios/1/mechanism/facts",
            json={
                "subject": "project",
                "attribute": "investment_destination",
                "value": "Campinas",
                "fact_time": "2026-07-17",
                "block_id": "proposal:1",
                "fact_pack_version": "facts-v0.1",
            },
        )
        fact_id = fact.json()["id"]
        assert business.post(
            f"/api/v1/scenarios/1/mechanism/facts/{fact_id}/confirm",
            json={"confirmation_note": "业务确认。"},
        ).status_code == 200

        compilation = legal.post(
            "/api/v1/scenarios/1/mechanism/claims/compile",
            json={
                "drafts": [
                    {
                        "checklist_code": "ENV-001",
                        "statement": "在法务核验前不得将该法源表述为已确认。",
                        "fact_refs": [fact_id],
                        "evidence_refs": ["ENV-001:law-1"],
                    }
                ]
            },
        )
        assert compilation.status_code == 201, compilation.text
        claim = next(item for item in compilation.json()["claims"] if item["checklist_code"] == "ENV-001")
        assert claim["status"] == "awaiting_human_confirmation"
        assert compilation.json()["input_snapshot"]["evidence"]["ENV-001:law-1"]["requires_review"] is True

        supported = legal.post(
            f"/api/v1/scenarios/1/mechanism/claims/{claim['id']}/confirm",
            json={"decision": "confirmed", "confirmation_note": "法务已逐条核验该临时法源。"},
        )
        assert supported.status_code == 200, supported.text
        assert supported.json()["status"] == "supported"
    finally:
        business.close()
        legal.close()
