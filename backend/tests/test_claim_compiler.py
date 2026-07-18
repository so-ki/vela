from app.core.statuses import ClaimVerdict
from app.models.claim import Claim, ClaimEvidence
from app.services.claim_compiler import claims_summary, compile_claims


def _brief(items):
    return {"sections": [{"dimension_id": "d1", "items": items}]}


def _item(code, gate_status="passed", citations=None, requires_review=False, block_reason=None):
    return {
        "code": code,
        "title": f"item {code}",
        "gate_status": gate_status,
        "block_reason": block_reason,
        "match_score": 80,
        "requires_review": requires_review,
        "risk_zh": f"conclusion for {code}",
        "risk_pt": None,
        "citations": citations or [],
    }


def _citation(status="corpus_verified", score=0.8):
    return {
        "id": "hit-1",
        "url": "https://example.test/source",
        "source_label": "test-source",
        "citation_status": status,
        "grounding_score": score,
    }


def test_supported_claim_requires_grounded_citation(db_session, scenario_row):
    projections = compile_claims(
        db_session, scenario_row.id, _brief([_item("A-001", citations=[_citation()])])
    )
    assert projections[0]["verdict"] == ClaimVerdict.SUPPORTED.value
    claim = db_session.query(Claim).one()
    evidences = db_session.query(ClaimEvidence).filter_by(claim_id=claim.id).all()
    assert len(evidences) == 1
    assert evidences[0].hit_ref["url"] == "https://example.test/source"


def test_conclusion_without_evidence_is_unanswerable(db_session, scenario_row):
    projections = compile_claims(db_session, scenario_row.id, _brief([_item("A-002", citations=[])]))
    assert projections[0]["verdict"] == ClaimVerdict.UNANSWERABLE.value


def test_blocked_item_stays_blocked(db_session, scenario_row):
    projections = compile_claims(
        db_session,
        scenario_row.id,
        _brief([_item("A-003", gate_status="blocked", block_reason="below threshold", citations=[_citation()])]),
    )
    assert projections[0]["verdict"] == ClaimVerdict.BLOCKED.value
    assert "below threshold" in projections[0]["verdict_reason"]


def test_weak_grounding_needs_review(db_session, scenario_row):
    projections = compile_claims(
        db_session,
        scenario_row.id,
        _brief([_item("A-004", citations=[_citation(status="weak_grounding", score=0.4)])]),
    )
    assert projections[0]["verdict"] == ClaimVerdict.NEEDS_REVIEW.value


def test_ungrounded_citations_do_not_support(db_session, scenario_row):
    projections = compile_claims(
        db_session,
        scenario_row.id,
        _brief([_item("A-005", citations=[_citation(status="ungrounded", score=0.0)])]),
    )
    assert projections[0]["verdict"] == ClaimVerdict.UNANSWERABLE.value


def test_recompile_replaces_previous_claims(db_session, scenario_row):
    compile_claims(db_session, scenario_row.id, _brief([_item("A-006", citations=[_citation()])]))
    compile_claims(db_session, scenario_row.id, _brief([_item("A-007", citations=[_citation()])]))
    claims = db_session.query(Claim).all()
    assert len(claims) == 1
    assert claims[0].checklist_code == "A-007"


def test_claims_summary_counts_unsupported(db_session, scenario_row):
    projections = compile_claims(
        db_session,
        scenario_row.id,
        _brief([
            _item("A-008", citations=[_citation()]),
            _item("A-009", citations=[]),
            _item("A-010", gate_status="blocked"),
        ]),
    )
    summary = claims_summary(projections)
    assert summary["total"] == 3
    assert summary["unsupported"] == 2
