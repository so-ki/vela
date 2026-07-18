from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.deps import get_current_user
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.legal_source_version import LegalChangeEvent, LegalSourceVersion
from app.models.user import User
from app.schemas.legal_source_version import LegalSourceDecisionRequest
from app.services.legal_source_version_service import (
    SourceVersionConflict,
    decide_source_version,
)


@pytest.fixture()
def source_version_db(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'source-versions.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(
                    id=1,
                    email="business-source@example.com",
                    full_name="Business",
                    role="business",
                    disclaimer_accepted=True,
                ),
                User(
                    id=2,
                    email="legal-source@example.com",
                    full_name="Legal",
                    role="legal",
                    disclaimer_accepted=True,
                ),
            ]
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


def _candidate_payload(*, raw: str = "RAW v1", normalized: str = "Article 1: Alpha") -> dict:
    return {
        "canonical_id": "law:example:climate-act",
        "citation_id": "Official Gazette 2026/17",
        "urn": "urn:lex:example:2026-01-01;climate-act",
        "source_authority": "Example National Gazette",
        "official_domain": "gazette.example.gov",
        "official_source_basis": "Domain recorded in the legal team's approved authority register.",
        "source_url": "https://gazette.example.gov/laws/climate-act",
        "fetched_at": "2026-07-17T08:00:00Z",
        "etag": '"abc"',
        "last_modified": "2026-07-17T07:00:00Z",
        "raw_content": raw,
        "normalized_content": normalized,
        "parser_version": "official-html-v1",
        "valid_from": "2026-08-01",
        "relations": [
            {
                "relation_type": "implements",
                "target_canonical_id": "law:example:framework",
                "target_urn": "urn:lex:example:2020;framework",
            }
        ],
        "articles": [
            {
                "article_id": "art-1",
                "heading": "Scope",
                "normalized_text": "Alpha",
                "relations": [],
            }
        ],
    }


def test_candidate_capture_is_legal_only_hash_pinned_audited_and_not_published(source_version_db):
    business = _client(source_version_db, 1)
    legal = _client(source_version_db, 2)
    path = "/api/v1/legal/source-versions/candidates"
    payload = _candidate_payload()
    try:
        denied = business.post(path, json=payload)
        assert denied.status_code == 403

        created = legal.post(path, json=payload)
        assert created.status_code == 201, created.text
        body = created.json()
        version = body["version"]
        assert version["status"] == "candidate"
        assert version["raw_hash"] == hashlib.sha256(b"RAW v1").hexdigest()
        assert version["normalized_hash"] == hashlib.sha256(
            "Article 1: Alpha".encode()
        ).hexdigest()
        assert "raw_content" not in version
        assert "normalized_content" not in version
        assert version["release_scope"] == "source_registry_only"
        assert version["capability_pack_corpus_updated"] is False
        assert version["current_version_designation"] == "not_assigned"
        assert body["change_event"]["change_type"] == "initial"
        assert body["change_event"]["article_diff"][0]["change_type"] == "added"

        with source_version_db() as db:
            stored = db.get(LegalSourceVersion, version["id"])
            assert stored.raw_content == "RAW v1"
            assert stored.normalized_content == "Article 1: Alpha"
            audit = (
                db.query(AuditLog)
                .filter(AuditLog.action == "legal_source.candidate_create")
                .one()
            )
            assert "capability_pack_corpus_updated=false" in audit.detail
    finally:
        business.close()
        legal.close()


def test_diff_and_human_review_state_machine_are_fail_closed(source_version_db):
    legal = _client(source_version_db, 2)
    business = _client(source_version_db, 1)
    create_path = "/api/v1/legal/source-versions/candidates"
    try:
        first = legal.post(create_path, json=_candidate_payload())
        assert first.status_code == 201, first.text
        first_id = first.json()["version"]["id"]

        direct_active = legal.post(
            f"/api/v1/legal/source-versions/{first_id}/decisions",
            json={"decision": "active", "note": "Attempt to skip review."},
        )
        assert direct_active.status_code == 422

        denied_review = business.post(
            f"/api/v1/legal/source-versions/{first_id}/decisions",
            json={"decision": "reviewed", "note": "Business cannot review."},
        )
        assert denied_review.status_code == 403

        reviewed = legal.post(
            f"/api/v1/legal/source-versions/{first_id}/decisions",
            json={"decision": "reviewed", "note": "Compared to official publication."},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "reviewed"
        active = legal.post(
            f"/api/v1/legal/source-versions/{first_id}/decisions",
            json={"decision": "active", "note": "Approved for source registry use."},
        )
        assert active.status_code == 200, active.text
        assert active.json()["status"] == "active"
        assert active.json()["capability_pack_corpus_updated"] is False

        terminal = legal.post(
            f"/api/v1/legal/source-versions/{first_id}/decisions",
            json={"decision": "rejected", "note": "Cannot reverse an active decision."},
        )
        assert terminal.status_code == 422

        second_payload = _candidate_payload(raw="RAW v2", normalized="Article 1: Beta Article 2: New")
        second_payload.update(
            {
                "fetched_at": "2026-07-18T08:00:00Z",
                "previous_version_id": first_id,
                "articles": [
                    {
                        "article_id": "art-1",
                        "heading": "Scope",
                        "normalized_text": "Beta",
                        "relations": [],
                    },
                    {
                        "article_id": "art-2",
                        "heading": "Duties",
                        "normalized_text": "New",
                        "relations": [],
                    },
                ],
            }
        )
        second = legal.post(create_path, json=second_payload)
        assert second.status_code == 201, second.text
        event = second.json()["change_event"]
        assert event["change_type"] == "content_changed"
        assert [(item["article_id"], item["change_type"]) for item in event["article_diff"]] == [
            ("art-1", "modified"),
            ("art-2", "added"),
        ]
    finally:
        legal.close()
        business.close()


def test_urn_is_optional_and_official_domain_is_explicitly_bound(source_version_db):
    legal = _client(source_version_db, 2)
    payload = _candidate_payload()
    payload.update(
        {
            "canonical_id": "law:second-jurisdiction:gazette:42",
            "citation_id": "Gazette No. 42/2026",
            "urn": None,
            "official_domain": "laws.second-jurisdiction.gov",
            "source_url": "https://laws.second-jurisdiction.gov/gazette/42",
        }
    )
    try:
        created = legal.post("/api/v1/legal/source-versions/candidates", json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["version"]["urn"] is None

        spoofed = dict(payload)
        spoofed.update(
            {
                "canonical_id": "law:second-jurisdiction:gazette:43",
                "citation_id": "Gazette No. 43/2026",
                "source_url": "https://attacker.invalid/gazette/43",
                "raw_content": "different raw",
                "normalized_content": "different normalized",
            }
        )
        rejected = legal.post("/api/v1/legal/source-versions/candidates", json=spoofed)
        assert rejected.status_code == 422
        assert "official_domain" in rejected.text
    finally:
        legal.close()


def test_source_capture_and_change_event_content_are_immutable(source_version_db):
    legal = _client(source_version_db, 2)
    try:
        created = legal.post(
            "/api/v1/legal/source-versions/candidates", json=_candidate_payload()
        )
        assert created.status_code == 201, created.text
        version_id = created.json()["version"]["id"]
        event_id = created.json()["change_event"]["id"]

        with source_version_db() as db:
            version = db.get(LegalSourceVersion, version_id)
            version.normalized_hash = "0" * 64
            with pytest.raises(ValueError, match="不可变"):
                db.flush()
            db.rollback()

        with source_version_db() as db:
            event = db.get(LegalChangeEvent, event_id)
            event.change_type = "format_only"
            with pytest.raises(ValueError, match="不可变"):
                db.flush()
    finally:
        legal.close()


def test_review_decision_uses_compare_and_swap_against_stale_sessions(source_version_db):
    legal = _client(source_version_db, 2)
    try:
        created = legal.post(
            "/api/v1/legal/source-versions/candidates", json=_candidate_payload()
        )
        assert created.status_code == 201, created.text
        version_id = created.json()["version"]["id"]

        first_session = source_version_db()
        stale_session = source_version_db()
        try:
            first_version = first_session.get(LegalSourceVersion, version_id)
            stale_version = stale_session.get(LegalSourceVersion, version_id)
            first_user = first_session.get(User, 2)
            stale_user = stale_session.get(User, 2)

            decide_source_version(
                first_session,
                version=first_version,
                request=LegalSourceDecisionRequest(
                    decision="reviewed", note="First legal decision wins."
                ),
                user=first_user,
            )
            first_session.commit()

            with pytest.raises(SourceVersionConflict, match="其他会话"):
                decide_source_version(
                    stale_session,
                    version=stale_version,
                    request=LegalSourceDecisionRequest(
                        decision="rejected", note="Stale competing decision loses."
                    ),
                    user=stale_user,
                )
            stale_session.rollback()
        finally:
            first_session.close()
            stale_session.close()

        with source_version_db() as db:
            assert db.get(LegalSourceVersion, version_id).status == "reviewed"
    finally:
        legal.close()
