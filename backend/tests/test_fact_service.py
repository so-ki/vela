from app.services.fact_service import active_facts, facts_projection, record_facts_from_extract
from app.services.material_ledger_service import record_intake


def _snapshot():
    return {
        "filename": "doc.pdf",
        "facts": [
            {
                "field": "employee_count",
                "value": "120",
                "source_snippet": "one hundred twenty staff",
                "source_filename": "doc.pdf",
                "verification_status": "verified",
                "grounding_score": 0.9,
            },
            {"field": "budget", "value": "10m", "verification_status": "unverified"},
        ],
    }


def test_record_facts_creates_quintuple(db_session, scenario_row):
    mapping = record_intake(
        db_session,
        scenario_id=scenario_row.id,
        pack_id=None,
        uploads=[("doc.pdf", b"x", None)],
        extract_snapshot=_snapshot(),
    )
    records = record_facts_from_extract(
        db_session,
        scenario_id=scenario_row.id,
        subject="Test Project",
        extract_snapshot=_snapshot(),
        block_by_name=mapping,
    )
    assert len(records) == 2
    verified = next(r for r in records if r.attribute == "employee_count")
    assert verified.subject == "Test Project"
    assert verified.value == "120"
    assert verified.asserted_at is not None
    assert verified.source_block_id == mapping["doc.pdf"]
    assert verified.verification_status == "verified"


def test_fact_without_source_cannot_be_verified(db_session, scenario_row):
    records = record_facts_from_extract(
        db_session,
        scenario_id=scenario_row.id,
        subject="s",
        extract_snapshot={"facts": [{"field": "a", "value": "b", "verification_status": "verified"}]},
        block_by_name={},
    )
    assert records[0].verification_status == "unverified"


def test_resubmission_supersedes_previous_facts(db_session, scenario_row):
    record_facts_from_extract(
        db_session,
        scenario_id=scenario_row.id,
        subject="s",
        extract_snapshot={"facts": [{"field": "employee_count", "value": "120"}]},
    )
    record_facts_from_extract(
        db_session,
        scenario_id=scenario_row.id,
        subject="s",
        extract_snapshot={"facts": [{"field": "employee_count", "value": "450"}]},
    )
    live = active_facts(db_session, scenario_row.id)
    assert len(live) == 1
    assert live[0].value == "450"
    projection = facts_projection(db_session, scenario_row.id)
    assert projection[0]["attribute"] == "employee_count"
