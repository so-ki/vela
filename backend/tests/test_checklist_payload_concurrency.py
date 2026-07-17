from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.api import projects as project_api
from app.api import scenarios as scenario_api
from app.core.database import Base
from app.models.audit_log import AuditLog
from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User


@pytest.fixture()
def checklist_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'checklist-cas.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        legal = User(
            id=2,
            email="legal-cas@example.com",
            full_name="法务 CAS",
            role="legal",
        )
        business = User(
            id=3,
            email="business-cas@example.com",
            full_name="业务 CAS",
            role="business",
        )
        scenario = InvestigationScenario(
            id=1,
            user_id=3,
            project_name="巴西工厂 CAS",
            country="brazil",
            state="SP",
            city="São Paulo",
            industry="new_energy",
            action_type="greenfield_plant",
            description="cross-module optimistic locking regression",
            compliance_dimensions=["environment"],
            status="review_in_progress",
            is_demo=False,
        )
        scenario.checklist = ComplianceChecklist(
            title="review",
            version="v0.1",
            total_items=1,
            payload={
                "brief": {"sections": []},
                "review": {
                    "status": "in_progress",
                    "revision": 0,
                    "items": [],
                },
            },
        )
        db.add_all([legal, business, scenario])
        db.commit()
        assert scenario.checklist.revision == 0
    return factory


def test_stale_project_writer_cannot_erase_legal_finalize(checklist_db) -> None:
    """Reproduce the legal-finalize/business-save race across API modules."""

    legal_db = checklist_db()
    business_db = checklist_db()
    try:
        legal_scenario = legal_db.get(InvestigationScenario, 1)
        business_scenario = business_db.get(InvestigationScenario, 1)
        legal_user = legal_db.get(User, 2)

        stale_business_payload = copy.deepcopy(business_scenario.checklist.payload)
        stale_business_payload["project_hub"] = {"version": "stale-business-copy"}

        finalized_payload = copy.deepcopy(legal_scenario.checklist.payload)
        finalized_payload["review"] = {
            "status": "approved",
            "revision": 1,
            "items": [],
        }
        finalized_payload["audit_bundle"] = {
            "bundle_version": "1.0",
            "review_revision": 1,
        }
        scenario_api._commit_review_mutation(
            legal_db,
            legal_scenario,
            finalized_payload,
            current_user=legal_user,
            new_scenario_status="review_approved",
            audit_entries=[("review.finalize", '{"review_revision":1}')],
        )

        with pytest.raises(HTTPException) as conflict:
            project_api._save_payload(
                business_db,
                business_scenario,
                stale_business_payload,
            )
        assert conflict.value.status_code == 409
        assert "刷新后重试" in str(conflict.value.detail)
    finally:
        legal_db.close()
        business_db.close()

    with checklist_db() as verify_db:
        persisted = verify_db.get(InvestigationScenario, 1)
        assert persisted.status == "review_approved"
        assert persisted.checklist.revision == 1
        assert persisted.checklist.payload["review"]["status"] == "approved"
        assert persisted.checklist.payload["review"]["revision"] == 1
        assert persisted.checklist.payload["audit_bundle"]["review_revision"] == 1
        assert "project_hub" not in persisted.checklist.payload
        assert verify_db.query(AuditLog).filter_by(action="review.finalize").count() == 1


def test_mapper_cas_covers_direct_legacy_payload_assignment(checklist_db) -> None:
    """Direct service assignments cannot bypass the model-wide version guard."""

    first = checklist_db()
    stale = checklist_db()
    try:
        current_scenario = first.get(InvestigationScenario, 1)
        stale_scenario = stale.get(InvestigationScenario, 1)
        # Force both one-to-one checklist rows into their respective identity
        # maps before either transaction writes.
        assert current_scenario.checklist.revision == 0
        assert stale_scenario.checklist.revision == 0

        current_scenario.checklist.payload = {"writer": "current"}
        first.commit()
        assert current_scenario.checklist.revision == 1

        stale_scenario.checklist.payload = {"writer": "stale"}
        with pytest.raises(StaleDataError):
            stale.commit()
        stale.rollback()
    finally:
        first.close()
        stale.close()

    with checklist_db() as verify_db:
        persisted = verify_db.get(InvestigationScenario, 1).checklist
        assert persisted.revision == 1
        assert persisted.payload == {"writer": "current"}


def test_project_hub_get_is_read_only(checklist_db, monkeypatch) -> None:
    with checklist_db() as db:
        scenario = db.get(InvestigationScenario, 1)
        business = db.get(User, 3)
        original_payload = copy.deepcopy(scenario.checklist.payload)
        original_revision = scenario.checklist.revision
        monkeypatch.setattr(
            project_api,
            "_save_payload",
            lambda *_args, **_kwargs: pytest.fail("GET hub must not save payload"),
        )

        response = project_api.get_project_hub(1, db, business)

        assert response.project_id == 1
        assert scenario.checklist.payload == original_payload
        assert scenario.checklist.revision == original_revision
        assert scenario.checklist not in db.dirty

    with checklist_db() as verify_db:
        persisted = verify_db.get(InvestigationScenario, 1).checklist
        assert persisted.payload == original_payload
        assert persisted.revision == original_revision


def test_alembic_backfills_revision_for_existing_checklists(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    backend_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "existing-before-revision.db"
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "20260717_0001")
    legacy_engine = create_engine(f"sqlite:///{database_path}")
    metadata = sa.MetaData()
    metadata.reflect(legacy_engine)
    now = datetime.now(timezone.utc)
    with legacy_engine.begin() as connection:
        connection.execute(
            metadata.tables["users"].insert().values(
                id=1,
                email="legacy@example.com",
                full_name="Legacy",
                role="business",
                auth_provider="local",
                is_active=True,
                disclaimer_accepted=False,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["investigation_scenarios"].insert().values(
                id=1,
                user_id=1,
                project_name="Legacy project",
                country="brazil",
                is_demo=False,
                state="SP",
                city="São Paulo",
                industry="new_energy",
                action_type="greenfield_plant",
                description="legacy row",
                compliance_dimensions=[],
                status="pending_scope",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["compliance_checklists"].insert().values(
                id=1,
                scenario_id=1,
                title="Legacy checklist",
                version="v0.1",
                payload={"legacy": True},
                total_items=0,
                created_at=now,
            )
        )
    legacy_engine.dispose()

    command.upgrade(config, "head")
    upgraded_engine = create_engine(f"sqlite:///{database_path}")
    inspector = sa.inspect(upgraded_engine)
    columns = {column["name"]: column for column in inspector.get_columns("compliance_checklists")}
    assert columns["revision"]["nullable"] is False
    with upgraded_engine.connect() as connection:
        revision = connection.execute(
            sa.text("SELECT revision FROM compliance_checklists WHERE id = 1")
        ).scalar_one()
    upgraded_engine.dispose()
    assert revision == 0
