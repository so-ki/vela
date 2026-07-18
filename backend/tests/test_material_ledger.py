import pytest

from app.core.statuses import MaterialBlockState
from app.services.material_ledger_service import (
    InvalidTransitionError,
    bulk_transition,
    create_block,
    ledger_projection,
    record_intake,
    transition,
)


def test_create_block_defaults_to_raw_archived(db_session, scenario_row):
    block = create_block(
        db_session,
        scenario_id=scenario_row.id,
        kind="file",
        filename="a.pdf",
        content_bytes=b"hello",
    )
    assert block.state == MaterialBlockState.RAW_ARCHIVED.value
    assert block.content_hash is not None and len(block.content_hash) == 64
    assert len(block.transitions) == 1


def test_valid_transition_records_history(db_session, scenario_row):
    block = create_block(db_session, scenario_id=scenario_row.id, kind="file", filename="a.pdf")
    transition(db_session, block, MaterialBlockState.EXTRACTED, reason="parsed")
    transition(db_session, block, MaterialBlockState.VERIFIED)
    assert block.state == MaterialBlockState.VERIFIED.value
    states = [(t.from_state, t.to_state) for t in block.transitions]
    assert ("raw_archived", "extracted") in states
    assert ("extracted", "verified") in states


def test_illegal_transition_rejected(db_session, scenario_row):
    block = create_block(db_session, scenario_id=scenario_row.id, kind="file", filename="a.pdf")
    transition(db_session, block, MaterialBlockState.SUPERSEDED)
    with pytest.raises(InvalidTransitionError):
        transition(db_session, block, MaterialBlockState.IN_USE)


def test_record_intake_builds_blocks_for_files_and_snapshot(db_session, scenario_row):
    uploads = [("doc1.pdf", b"abc", "application/pdf"), ("doc2.pdf", b"def", "application/pdf")]
    snapshot = {
        "filename": "doc1.pdf",
        "facts": [
            {"field": "f1", "value": "v1", "verification_status": "verified"},
            {"field": "f2", "value": "v2", "verification_status": "verified"},
        ],
    }
    mapping = record_intake(
        db_session,
        scenario_id=scenario_row.id,
        pack_id=None,
        uploads=uploads,
        archived_files=[{"filename": "doc1.pdf", "stored_name": "s1"}],
        extract_snapshot=snapshot,
    )
    assert set(mapping) == {"doc1.pdf", "doc2.pdf", "__extract__"}
    projection = ledger_projection(db_session, scenario_row.id)
    assert len(projection) == 3
    snap = next(p for p in projection if p["kind"] == "extract_snapshot")
    assert snap["state"] == MaterialBlockState.VERIFIED.value


def test_snapshot_with_unverified_fact_is_unverified(db_session, scenario_row):
    snapshot = {
        "filename": "d.pdf",
        "facts": [
            {"field": "f1", "value": "v1", "verification_status": "verified"},
            {"field": "f2", "value": "v2", "verification_status": "unverified"},
        ],
    }
    record_intake(
        db_session, scenario_id=scenario_row.id, pack_id=None, extract_snapshot=snapshot
    )
    projection = ledger_projection(db_session, scenario_row.id)
    assert projection[0]["state"] == MaterialBlockState.UNVERIFIED.value


def test_bulk_transition_skips_illegal_moves(db_session, scenario_row):
    a = create_block(db_session, scenario_id=scenario_row.id, kind="file", filename="a")
    b = create_block(db_session, scenario_id=scenario_row.id, kind="file", filename="b")
    transition(db_session, a, MaterialBlockState.EXTRACTED)
    transition(db_session, b, MaterialBlockState.SUPERSEDED)
    moved = bulk_transition(db_session, scenario_row.id, MaterialBlockState.IN_USE)
    assert moved == 1
    assert a.state == MaterialBlockState.IN_USE.value
    assert b.state == MaterialBlockState.SUPERSEDED.value
