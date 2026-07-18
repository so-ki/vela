from __future__ import annotations

import copy
import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import scenarios as scenario_api
from app.core.database import Base
from app.models.audit_log import AuditLog
from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User
from app.schemas.review import ReviewItemUpdateRequest, ReviewReturnRequest


@pytest.fixture()
def review_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'review-audit.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        legal = User(id=2, email="legal-b@example.com", full_name="法务 B", role="legal")
        scenario = InvestigationScenario(
            id=1,
            user_id=2,
            project_name="巴西工厂",
            country="brazil",
            state="SP",
            city="São Paulo",
            industry="new_energy",
            action_type="greenfield_plant",
            description="test",
            compliance_dimensions=["environment"],
            status="review_in_progress",
        )
        scenario.checklist = ComplianceChecklist(
            title="review",
            version="v0.1",
            total_items=1,
            payload={
                "review": {
                    "status": "in_progress",
                    "reviewer_id": 2,
                    "reviewer_name": "法务 B",
                    "started_at": "2026-07-17T00:00:00+00:00",
                    "revision": 0,
                    "items": [
                        {
                            "code": "ENV-001",
                            "title": "环境许可",
                            "dimension_name": "环境",
                            "gate_status": "needs_review",
                            "match_score": 75,
                            "tier": "S2",
                            "hard_block": False,
                            "decision": "pending",
                            "comment": None,
                            "external_counsel_required": False,
                            "legal_hits": [],
                            "reviewed_at": None,
                        }
                    ],
                }
            },
        )
        db.add_all([legal, scenario])
        db.commit()
    return factory


def test_api_item_change_and_audit_record_commit_together(review_db, monkeypatch):
    monkeypatch.setattr(scenario_api, "require_generated_result", lambda *args, **kwargs: object())
    monkeypatch.setattr(scenario_api, "record_review_decision", lambda *args, **kwargs: None)

    with review_db() as db:
        legal = db.get(User, 2)
        response = scenario_api.patch_review_item(
            1,
            "ENV-001",
            ReviewItemUpdateRequest(
                decision="approved",
                comment="已核对官方许可流程",
                expected_revision=0,
            ),
            db,
            legal,
        )
        assert response.revision == 1

        persisted = db.get(InvestigationScenario, 1).checklist.payload["review"]
        item = persisted["items"][0]
        assert item["reviewer_id"] == 2
        assert item["reviewer_name"] == "法务 B"
        audit = db.query(AuditLog).filter(AuditLog.action == "review.item_update").one()
        detail = json.loads(audit.detail)
        assert detail["reviewer_id"] == 2
        assert detail["decision"] == "approved"
        assert detail["previous"]["decision"] == "pending"

        with pytest.raises(HTTPException) as stale:
            scenario_api.patch_review_item(
                1,
                "ENV-001",
                ReviewItemUpdateRequest(
                    decision="rejected",
                    comment="stale",
                    expected_revision=0,
                ),
                db,
                legal,
            )
        assert stale.value.status_code == 409


def test_review_write_bodies_require_an_explicit_revision_precondition():
    with pytest.raises(ValidationError, match="expected_revision"):
        ReviewItemUpdateRequest(decision="approved", comment="missing precondition")
    with pytest.raises(ValidationError, match="expected_revision"):
        ReviewReturnRequest(note="missing precondition")


def test_audit_failure_rolls_back_the_review_change(review_db, monkeypatch):
    monkeypatch.setattr(scenario_api, "require_generated_result", lambda *args, **kwargs: object())
    learning_events = []
    monkeypatch.setattr(
        scenario_api,
        "record_review_decision",
        lambda *args, **kwargs: learning_events.append((args, kwargs)),
    )
    monkeypatch.setattr(
        scenario_api,
        "write_audit_log",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )

    with review_db() as db:
        legal = db.get(User, 2)
        with pytest.raises(RuntimeError, match="audit unavailable"):
            scenario_api.patch_review_item(
                1,
                "ENV-001",
                ReviewItemUpdateRequest(
                    decision="approved",
                    comment="核对完成",
                    expected_revision=0,
                ),
                db,
                legal,
            )

    with review_db() as db:
        persisted = db.get(InvestigationScenario, 1).checklist.payload["review"]
        assert persisted["revision"] == 0
        assert persisted["items"][0]["decision"] == "pending"
        assert db.query(AuditLog).count() == 0
        assert learning_events == []


def test_database_compare_and_swap_rejects_concurrent_legacy_api_writes(
    review_db, monkeypatch
):
    monkeypatch.setattr(scenario_api, "require_generated_result", lambda *args, **kwargs: object())
    learning_events = []
    monkeypatch.setattr(
        scenario_api,
        "record_review_decision",
        lambda *args, **kwargs: learning_events.append((args, kwargs)),
    )
    first = review_db()
    second = review_db()
    try:
        scenario_a = first.get(InvestigationScenario, 1)
        scenario_b = second.get(InvestigationScenario, 1)
        legal_a = first.get(User, 2)
        legal_b = second.get(User, 2)

        response = scenario_api.patch_review_item(
            1,
            "ENV-001",
            ReviewItemUpdateRequest(decision="approved", comment="A", expected_revision=0),
            first,
            legal_a,
        )
        assert response.revision == 1

        with pytest.raises(HTTPException) as conflict:
            scenario_api.patch_review_item(
                1,
                "ENV-001",
                ReviewItemUpdateRequest(decision="rejected", comment="B", expected_revision=0),
                second,
                legal_b,
            )
        assert conflict.value.status_code == 409
        assert len(learning_events) == 1
    finally:
        first.close()
        second.close()


def test_review_initialization_and_audit_are_atomic(review_db, monkeypatch):
    monkeypatch.setattr(scenario_api, "require_generated_result", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        scenario_api,
        "init_review",
        lambda db, scenario, user: {
            "status": "in_progress",
            "reviewer_id": user.id,
            "reviewer_name": user.full_name,
            "started_at": "2026-07-17T00:00:00+00:00",
            "finalized_at": None,
            "revision": 0,
            "change_history": [],
            "items": [],
        },
    )
    monkeypatch.setattr(
        scenario_api,
        "write_audit_log",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )

    with review_db() as db:
        scenario = db.get(InvestigationScenario, 1)
        scenario.status = "pending_legal_review"
        scenario.checklist.payload = {"brief": {"sections": []}}
        db.commit()
        legal = db.get(User, 2)
        with pytest.raises(RuntimeError, match="audit unavailable"):
            scenario_api.start_review(1, db, legal)

    with review_db() as db:
        scenario = db.get(InvestigationScenario, 1)
        assert scenario.status == "pending_legal_review"
        assert "review" not in scenario.checklist.payload
        assert db.query(AuditLog).count() == 0


def test_finalize_replay_creates_no_duplicate_history_or_audit(review_db, monkeypatch):
    monkeypatch.setattr(scenario_api, "require_generated_result", lambda *args, **kwargs: object())
    monkeypatch.setattr(scenario_api, "build_audit_bundle", lambda *args, **kwargs: {"ok": True})

    with review_db() as db:
        legal = db.get(User, 2)
        scenario = db.get(InvestigationScenario, 1)
        payload = copy.deepcopy(scenario.checklist.payload)
        payload["review"]["items"][0]["decision"] = "approved"
        scenario.checklist.payload = payload
        db.commit()

        first = scenario_api.finalize_scenario_review(1, 0, db, legal)
        assert first.revision == 1
        checklist_revision = scenario.checklist.revision

        with pytest.raises(HTTPException) as replay:
            scenario_api.finalize_scenario_review(1, 1, db, legal)
        assert replay.value.status_code == 409

        db.expire_all()
        persisted = db.get(InvestigationScenario, 1)
        assert len(persisted.checklist.payload.get("finalize_history") or []) == 1
        assert persisted.checklist.revision == checklist_revision
        assert db.query(AuditLog).filter(AuditLog.action == "review.finalize").count() == 1


def test_bulk_approve_replay_creates_no_zero_change_audit(review_db, monkeypatch):
    monkeypatch.setattr(scenario_api, "require_generated_result", lambda *args, **kwargs: object())

    with review_db() as db:
        legal = db.get(User, 2)
        scenario = db.get(InvestigationScenario, 1)
        payload = copy.deepcopy(scenario.checklist.payload)
        item = payload["review"]["items"][0]
        item.update({"tier": "S1", "gate_status": "passed", "hard_block": False})
        scenario.checklist.payload = payload
        db.commit()

        first = scenario_api.approve_all_review_items(1, 0, db, legal)
        assert first.revision == 1
        checklist_revision = scenario.checklist.revision

        with pytest.raises(HTTPException) as replay:
            scenario_api.approve_all_review_items(1, 1, db, legal)
        assert replay.value.status_code == 409

        db.expire_all()
        persisted = db.get(InvestigationScenario, 1)
        assert persisted.checklist.revision == checklist_revision
        assert (
            db.query(AuditLog).filter(AuditLog.action == "review.bulk_approve_s1").count()
            == 1
        )
