import pytest

from app.core.statuses import CoverageTaskStatus
from app.models.coverage import CoverageProof
from app.services.coverage_service import (
    DenominatorRequiredError,
    build_scenario_proof,
    coverage_projection,
    sync_tasks_from_payload,
    upsert_task,
)


def _payload():
    return {
        "investigation_adequacy": {
            "dimensions": [
                {
                    "dimension_id": "dim_a",
                    "elements": [
                        {"id": "el1", "status": "covered"},
                        {"id": "el2", "status": "missing"},
                        {"id": "el3", "status": "at_risk"},
                    ],
                }
            ],
            "is_investigation_ready": False,
        },
        "brief": {
            "sections": [
                {
                    "items": [
                        {"code": "X-001", "citations": [{"id": "h"}]},
                        {"code": "X-002", "citations": [], "block_reason": "no hits"},
                    ]
                }
            ]
        },
        "grounding_report": {"grounding_rate": 0.8},
    }


def test_sync_tasks_derives_gaps_and_satisfied(db_session, scenario_row):
    sync_tasks_from_payload(db_session, scenario_row.id, _payload())
    projection = coverage_projection(db_session, scenario_row.id)
    kinds = {(t["kind"], t["status"]) for t in projection["tasks"]}
    assert ("material_gap", "open") in kinds          # missing element
    assert ("element_gap", "open") in kinds           # at_risk element
    assert ("element_gap", "satisfied") in kinds      # covered element
    assert ("retrieval_gap", "open") in kinds         # zero-hit brief item
    assert projection["open_count"] == 3


def test_enumerated_absent_requires_official_denominator(db_session, scenario_row):
    with pytest.raises(DenominatorRequiredError):
        upsert_task(
            db_session,
            scenario_id=scenario_row.id,
            kind="retrieval_gap",
            origin="zero_hit",
            status=CoverageTaskStatus.ENUMERATED_ABSENT,
            denominator_source=None,
        )
    task = upsert_task(
        db_session,
        scenario_id=scenario_row.id,
        kind="retrieval_gap",
        origin="zero_hit",
        checklist_code="X-003",
        status=CoverageTaskStatus.ENUMERATED_ABSENT,
        denominator_source="curated_official_list",
    )
    assert task.status == CoverageTaskStatus.ENUMERATED_ABSENT.value


def test_proof_uses_pack_elements_as_denominator(db_session, scenario_row):
    proof = build_scenario_proof(db_session, scenario_row.id, _payload())
    assert proof is not None
    assert proof.denominator_source == "pack_dimension_elements"
    assert proof.denominator_count == 3
    assert proof.covered_count == 1
    assert proof.proof_hash


def test_no_adequacy_means_no_proof(db_session, scenario_row):
    proof = build_scenario_proof(db_session, scenario_row.id, {"brief": {}})
    assert proof is None
    assert db_session.query(CoverageProof).count() == 0


def test_proofs_are_append_only(db_session, scenario_row):
    build_scenario_proof(db_session, scenario_row.id, _payload())
    build_scenario_proof(db_session, scenario_row.id, _payload())
    assert db_session.query(CoverageProof).count() == 2
