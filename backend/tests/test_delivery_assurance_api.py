from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.deps import get_current_user
from app.main import create_app
from app.models.delivery_assurance import ScenarioDeliveryArtifact
from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User
from app.services.generation_guard import stable_hash


@pytest.fixture()
def delivery_api_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'delivery-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(
                    id=1,
                    email="owner@example.com",
                    full_name="Scenario Owner",
                    organization="Acme",
                    role="business",
                    disclaimer_accepted=True,
                ),
                User(
                    id=2,
                    email="other@example.com",
                    full_name="Other Customer",
                    organization="Other",
                    role="business",
                    disclaimer_accepted=True,
                ),
                User(
                    id=3,
                    email="legal@example.com",
                    full_name="Brazil Expert",
                    organization="Law Firm",
                    role="legal",
                    disclaimer_accepted=True,
                ),
            ]
        )
        scenario = InvestigationScenario(
            id=1,
            user_id=1,
            project_name="Candidate review",
            country="brazil",
            state="SP",
            city="Campinas",
            industry="new_energy",
            action_type="greenfield_plant",
            description="Review the exact frozen bytes.",
            compliance_dimensions=["environment"],
            status="review_approved",
            scope_snapshot_hash="a" * 64,
            is_demo=False,
        )
        scenario.checklist = ComplianceChecklist(
            title="Frozen checklist",
            version="v1",
            payload={"review": {"status": "approved"}},
            total_items=1,
        )
        db.add(scenario)
        for index, artifact_type in enumerate(("audit_bundle", "docx", "pdf"), start=1):
            content = f"candidate-{artifact_type}".encode()
            db.add(
                ScenarioDeliveryArtifact(
                    id=f"10000000-0000-0000-0000-00000000000{index}",
                    scenario_id=1,
                    artifact_type=artifact_type,
                    snapshot_hash="b" * 64,
                    content_sha256=hashlib.sha256(content).hexdigest(),
                    content_length=len(content),
                    media_type="application/octet-stream",
                    filename=f"candidate.{artifact_type}",
                    renderer_version="test-renderer@commit",
                    content=content,
                    status="candidate",
                    created_by=3,
                )
            )
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


def test_candidate_download_is_exact_scoped_and_explicitly_not_released(delivery_api_db):
    path = (
        "/api/v1/scenarios/1/delivery-assurance/artifacts/"
        "10000000-0000-0000-0000-000000000002/candidate"
    )
    owner = _client(delivery_api_db, 1)
    other_customer = _client(delivery_api_db, 2)
    legal = _client(delivery_api_db, 3)
    try:
        response = owner.get(path)
        assert response.status_code == 200, response.text
        assert response.content == b"candidate-docx"
        assert response.headers["x-content-sha256"] == hashlib.sha256(
            response.content
        ).hexdigest()
        assert response.headers["x-customer-delivery-authorized"] == "false"
        assert response.headers["cache-control"] == "no-store"

        assert legal.get(path).status_code == 200
        assert other_customer.get(path).status_code == 403
    finally:
        owner.close()
        other_customer.close()
        legal.close()


def test_candidate_manifest_hash_matches_returned_manifest(delivery_api_db):
    client = _client(delivery_api_db, 1)
    try:
        response = client.get(
            "/api/v1/scenarios/1/delivery-assurance/artifact-manifest"
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["snapshot_hash"] == "b" * 64
        assert {item["artifact_type"] for item in body["artifact_manifest"]} == {
            "docx",
            "pdf",
            "audit_bundle",
        }
        assert body["artifact_manifest_hash"] == stable_hash(body["artifact_manifest"])
    finally:
        client.close()
