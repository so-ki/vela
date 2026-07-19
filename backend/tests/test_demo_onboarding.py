from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.cold_start_service as cold_start_service
import app.services.legal_ingest as legal_ingest
import app.services.legal_monitor as legal_monitor
import app.services.legal_rag as legal_rag
import app.services.material_file_storage as material_file_storage
import app.services.playbook_deviation_service as playbook_deviation_service
import app.services.user_preference_service as user_preference_service
import scripts.seed_demo_user as seed_demo_user
from app.core.database import Base, get_db
from app.core.security import get_password_hash, verify_password
from app.main import create_app
from app.models.user import User
from app.schemas.brief import BriefCitationResponse
from app.schemas.legal import LegalHitResponse
from scripts.seed_demo_user import DEMO_LEGAL_PROFILE_VERSION, _demo_organization, seed_demo_users


def test_production_smoke_seed_uses_instance_organization(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INSTANCE_ORGANIZATION", "Vela controlled smoke")
    assert _demo_organization({"organization": "untrusted label"}) == "Vela controlled smoke"

    monkeypatch.delenv("INSTANCE_ORGANIZATION")
    with pytest.raises(RuntimeError):
        _demo_organization({"organization": "untrusted label"})


def test_production_seed_entrypoint_rejects_non_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SQLiteDialect:
        name = "sqlite"

    class SQLiteBind:
        dialect = SQLiteDialect()

    class SQLiteSession:
        def get_bind(self) -> SQLiteBind:
            return SQLiteBind()

        def close(self) -> None:
            pass

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        seed_demo_user,
        "init_db",
        lambda: pytest.fail("production seed must fail before initializing SQLite"),
    )
    monkeypatch.setattr(seed_demo_user, "SessionLocal", SQLiteSession)
    monkeypatch.setattr(
        seed_demo_user,
        "seed_demo_users",
        lambda _db: pytest.fail("production seed must fail before mutating SQLite"),
    )

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        seed_demo_user.seed()


@pytest.fixture()
def demo_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runtime_dir = tmp_path / "runtime"
    profiles_dir = runtime_dir / "playbook_profiles"
    monkeypatch.setattr(cold_start_service, "PROFILES_DIR", profiles_dir)
    monkeypatch.setattr(cold_start_service, "SESSIONS_DIR", runtime_dir / "interview_sessions")
    monkeypatch.setattr(cold_start_service, "TEMPLATES_DIR", runtime_dir / "playbook_templates")
    monkeypatch.setattr(material_file_storage, "UPLOAD_ROOT", runtime_dir / "scenario_materials")
    monkeypatch.setattr(user_preference_service, "PREFS_DIR", runtime_dir / "user_preferences")
    monkeypatch.setattr(playbook_deviation_service, "DEVIATIONS_PATH", runtime_dir / "playbook_deviations.json")
    monkeypatch.setattr(legal_monitor, "MONITOR_PATH", runtime_dir / "legal_monitor.json")
    monkeypatch.setattr(legal_monitor, "INDEX_FLAG", runtime_dir / "legal_index.json")
    monkeypatch.setattr(legal_ingest, "INDEX_FLAG", runtime_dir / "legal_index.json")
    # Exercise the real deterministic keyword RAG without opening the shared Chroma store.
    monkeypatch.setattr(legal_ingest, "_chroma_available", False)
    monkeypatch.setattr(legal_rag, "_chroma_available", False)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'demo-users.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory, profiles_dir


def _client(factory) -> TestClient:
    app = create_app()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _login(client: TestClient, email: str, password: str = "Demo1234!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_seed_converges_dirty_demo_accounts_without_touching_real_legal(demo_environment):
    factory, profiles_dir = demo_environment
    with factory() as db:
        db.add_all(
            [
                User(
                    id=41,
                    email="LEGAL@DEMO.VELA",
                    full_name="stale",
                    organization="stale",
                    hashed_password=get_password_hash("WrongPassword1!"),
                    role="business",
                    auth_provider="sso",
                    external_subject="stale-subject",
                    is_active=False,
                    disclaimer_accepted=False,
                ),
                User(
                    id=42,
                    email="biz@demo.vela",
                    full_name="stale",
                    organization="stale",
                    hashed_password=None,
                    role="legal",
                    auth_provider="sso",
                    external_subject="stale-subject",
                    is_active=False,
                    disclaimer_accepted=False,
                ),
                User(
                    id=43,
                    email="real.legal@example.com",
                    full_name="Real Legal",
                    organization="Real Corp",
                    hashed_password=get_password_hash("RealPassword1!"),
                    role="legal",
                    auth_provider="local",
                    is_active=True,
                    disclaimer_accepted=True,
                ),
            ]
        )
        db.commit()

        seed_demo_users(db)
        legal = db.get(User, 41)
        business = db.get(User, 42)
        real_legal = db.get(User, 43)
        assert legal is not None and business is not None and real_legal is not None
        assert (legal.email, legal.role, legal.full_name) == ("legal@demo.vela", "legal", "演示法务")
        assert (business.email, business.role, business.full_name) == ("biz@demo.vela", "business", "演示业务")
        for user in (legal, business):
            assert user.is_active is True
            assert user.disclaimer_accepted is True
            assert user.disclaimer_accepted_at is not None
            assert user.auth_provider == "local"
            assert user.external_subject is None
            assert user.hashed_password and verify_password("Demo1234!", user.hashed_password)
        assert real_legal.full_name == "Real Legal"
        assert verify_password("RealPassword1!", real_legal.hashed_password or "")

        profile_path = profiles_dir / "user_41.json"
        first_profile_bytes = profile_path.read_bytes()
        profile = json.loads(first_profile_bytes)
        assert profile["completed"] is True
        assert profile["user_id"] == 41
        assert profile["profile_version"] == DEMO_LEGAL_PROFILE_VERSION
        assert profile["profile_source"] == "demo_seed"
        assert profile["industry_focus"] == ["new_energy"]
        assert profile["owner_binding"] == {
            "binding_version": "1.0",
            "user_id": 41,
            "email": "legal@demo.vela",
            "auth_provider": "local",
            "external_subject": None,
        }
        assert cold_start_service.profile_for_generation(41)["completed"] is False
        assert cold_start_service.profile_for_generation(
            41,
            owner_email="LEGAL@DEMO.VELA",
            owner_auth_provider="local",
            owner_external_subject=None,
        )["completed"] is True
        assert not (profiles_dir / "user_42.json").exists()
        assert not (profiles_dir / "user_43.json").exists()

        first_hashes = (legal.hashed_password, business.hashed_password)
        seed_demo_users(db)
        assert db.query(User).count() == 3
        assert (db.get(User, 41).hashed_password, db.get(User, 42).hashed_password) == first_hashes
        assert profile_path.read_bytes() == first_profile_bytes


def test_fresh_demo_api_roles_onboarding_and_extract_dto(demo_environment):
    factory, profiles_dir = demo_environment
    with factory() as db:
        seeded = seed_demo_users(db)
        db.add_all(
            [
                User(
                    email="real.legal@example.com",
                    full_name="Real Legal",
                    hashed_password=get_password_hash("RealPassword1!"),
                    role="legal",
                    is_active=True,
                    disclaimer_accepted=True,
                ),
                User(
                    email="admin@example.com",
                    full_name="Admin",
                    hashed_password=get_password_hash("AdminPassword1!"),
                    role="admin",
                    is_active=True,
                    disclaimer_accepted=True,
                ),
            ]
        )
        db.commit()
        legal_id = seeded["legal@demo.vela"].id
        business_id = seeded["biz@demo.vela"].id
        real_legal_id = db.query(User).filter(User.email == "real.legal@example.com").one().id

    assert (profiles_dir / f"user_{legal_id}.json").exists()
    assert not (profiles_dir / f"user_{business_id}.json").exists()

    client = _client(factory)
    legal_token = _login(client, "legal@demo.vela")
    business_token = _login(client, "biz@demo.vela")
    real_legal_token = _login(client, "real.legal@example.com", "RealPassword1!")
    admin_token = _login(client, "admin@example.com", "AdminPassword1!")

    for token, email, role in (
        (legal_token, "legal@demo.vela", "legal"),
        (business_token, "biz@demo.vela", "business"),
    ):
        response = client.get("/api/v1/auth/me", headers=_headers(token))
        assert response.status_code == 200
        me = response.json()
        assert me["email"] == email
        assert me["role"] == role
        assert me["is_active"] is True
        assert me["disclaimer_accepted"] is True

    legal_status = client.get("/api/v1/onboarding/status", headers=_headers(legal_token))
    assert legal_status.status_code == 200
    assert legal_status.json() == {"completed": True, "required": True, "role": "legal"}

    business_status = client.get("/api/v1/onboarding/status", headers=_headers(business_token))
    assert business_status.status_code == 200
    assert business_status.json() == {"completed": True, "required": False, "role": "business"}

    assert client.post("/api/v1/legal/index", headers=_headers(business_token)).status_code == 403
    assert client.post("/api/v1/legal/monitor/scan", headers=_headers(business_token)).status_code == 403

    real_status = client.get("/api/v1/onboarding/status", headers=_headers(real_legal_token))
    assert real_status.status_code == 200
    assert real_status.json() == {"completed": False, "required": True, "role": "legal"}
    admin_status = client.get("/api/v1/onboarding/status", headers=_headers(admin_token))
    assert admin_status.status_code == 200
    assert admin_status.json() == {"completed": False, "required": True, "role": "admin"}

    legal_profile = client.get("/api/v1/onboarding/profile", headers=_headers(legal_token))
    assert legal_profile.status_code == 200
    assert legal_profile.json()["profile_version"] == DEMO_LEGAL_PROFILE_VERSION
    assert legal_profile.json()["default_compliance_dimensions"]
    assert client.get("/api/v1/onboarding/interview/script", headers=_headers(admin_token)).status_code == 200

    business_only_requests = (
        client.get("/api/v1/onboarding/profile", headers=_headers(business_token)),
        client.get("/api/v1/onboarding/interview/script", headers=_headers(business_token)),
        client.post("/api/v1/onboarding/interview/start", headers=_headers(business_token)),
        client.post(
            "/api/v1/onboarding/interview/missing/answer",
            headers=_headers(business_token),
            json={"question_id": "org_name", "answer": "Demo"},
        ),
        client.post(
            "/api/v1/onboarding/interview/missing/sync",
            headers=_headers(business_token),
            json={"answers": {}},
        ),
        client.post(
            "/api/v1/onboarding/interview/missing/upload",
            headers=_headers(business_token),
            files={"file": ("policy.txt", b"long enough policy content", "text/plain")},
        ),
        client.post(
            "/api/v1/onboarding/interview/complete",
            headers=_headers(business_token),
            json={"session_id": "missing"},
        ),
        client.post(
            "/api/v1/onboarding/templates",
            headers=_headers(business_token),
            files={"file": ("template.txt", b"long enough template content", "text/plain")},
        ),
    )
    assert [response.status_code for response in business_only_requests] == [403] * len(business_only_requests)

    interview_start = client.post("/api/v1/onboarding/interview/start", headers=_headers(real_legal_token))
    assert interview_start.status_code == 200, interview_start.text
    session_id = interview_start.json()["session_id"]
    for question_id, answer in (
        ("org_name", "Real Corp Legal"),
        ("primary_jurisdiction", "brazil"),
        ("industry_focus", ["new_energy"]),
    ):
        answered = client.post(
            f"/api/v1/onboarding/interview/{session_id}/answer",
            headers=_headers(real_legal_token),
            json={"question_id": question_id, "answer": answer},
        )
        assert answered.status_code == 200, answered.text
    completed = client.post(
        "/api/v1/onboarding/interview/complete",
        headers=_headers(real_legal_token),
        json={"session_id": session_id},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["completed"] is True
    assert completed.json()["profile_source"] == "interview"
    completed_status = client.get("/api/v1/onboarding/status", headers=_headers(real_legal_token))
    assert completed_status.json() == {"completed": True, "required": True, "role": "legal"}
    real_profile = json.loads((profiles_dir / f"user_{real_legal_id}.json").read_text(encoding="utf-8"))
    assert real_profile["owner_binding"] == {
        "binding_version": "1.0",
        "user_id": real_legal_id,
        "email": "real.legal@example.com",
        "auth_provider": "local",
        "external_subject": None,
    }

    scan_response = client.post(
        "/api/v1/scenarios/extract-document",
        headers=_headers(business_token),
        files={"file": ("scan.txt", b"abc", "text/plain")},
    )
    assert scan_response.status_code == 200, scan_response.text
    assert scan_response.json()["scan_or_empty"] is True
    assert scan_response.json()["extraction_warning"]

    grounded_response = client.post(
        "/api/v1/scenarios/extract-document",
        headers=_headers(business_token),
        files={
            "file": (
                "proposal.txt",
                (
                    "项目名称：巴西新能源制造绿地工厂。项目拟在巴西圣保罗州建设新能源电池制造工厂，"
                    "计划投资十亿元并雇佣当地员工四百五十人。该项目将建设生产车间、研发中心和仓库。"
                ).encode("utf-8"),
                "text/plain",
            )
        },
    )
    assert grounded_response.status_code == 200, grounded_response.text
    assert grounded_response.json()["facts"]
    assert all("verification_status" in fact and "grounding_score" in fact for fact in grounded_response.json()["facts"])


def test_preserved_demo_profile_cannot_complete_a_reused_real_legal_id(demo_environment):
    factory, profiles_dir = demo_environment
    with factory() as db:
        seeded = seed_demo_users(db)
        demo_legal_id = seeded["legal@demo.vela"].id
        engine = db.get_bind()

    profile_path = profiles_dir / f"user_{demo_legal_id}.json"
    assert profile_path.exists()
    assert cold_start_service.get_playbook_profile(
        demo_legal_id,
        owner_email="LEGAL@DEMO.VELA",
        owner_auth_provider="sso",
        owner_external_subject="different-subject",
    )["completed"] is False

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add(
            User(
                id=demo_legal_id,
                email="new.real.legal@example.com",
                full_name="New Real Legal",
                hashed_password=get_password_hash("NewRealPassword1!"),
                role="legal",
                auth_provider="local",
                is_active=True,
                disclaimer_accepted=True,
            )
        )
        db.commit()

    client = _client(factory)
    token = _login(client, "new.real.legal@example.com", "NewRealPassword1!")
    status_response = client.get("/api/v1/onboarding/status", headers=_headers(token))
    assert status_response.status_code == 200
    assert status_response.json() == {"completed": False, "required": True, "role": "legal"}
    profile_response = client.get("/api/v1/onboarding/profile", headers=_headers(token))
    assert profile_response.status_code == 200
    assert profile_response.json()["completed"] is False
    assert "不匹配" in (profile_response.json()["message"] or "")
    client.close()


def test_grounding_fields_are_not_dropped_by_response_dtos():
    legal_hit = LegalHitResponse(
        id="doc-1",
        source="official",
        source_label="Official",
        urn="urn:test",
        url="https://example.invalid/doc-1",
        title_pt="Título",
        title_zh="标题",
        excerpt_pt="Trecho",
        excerpt_zh="摘录",
        validity="active",
        level="federal",
        published_at="2026-01-01",
        match_score=88,
        vector_similarity=0.8,
        keyword_overlap=0.7,
        requires_review=False,
        grounding_score=0.91,
        citation_status="corpus_verified",
        grounded=True,
        grounding_note="verified",
    ).model_dump()
    assert legal_hit["grounding_score"] == 0.91
    assert legal_hit["citation_status"] == "corpus_verified"
    assert legal_hit["grounded"] is True
    assert legal_hit["grounding_note"] == "verified"

    citation = BriefCitationResponse(
        id="doc-1",
        source_label="Official",
        title_zh="标题",
        title_pt="Título",
        url="https://example.invalid/doc-1",
        match_score=88,
        requires_review=False,
        grounding_score=0.91,
        citation_status="corpus_verified",
        grounded=True,
    ).model_dump()
    assert citation["grounding_score"] == 0.91
    assert citation["citation_status"] == "corpus_verified"
    assert citation["grounded"] is True


def test_fresh_sqlite_real_mainline_generates_reviews_and_exports(demo_environment):
    factory, profiles_dir = demo_environment
    runtime_dir = profiles_dir.parent

    with factory() as db:
        users = seed_demo_users(db)
        for user in users.values():
            preferences = user_preference_service.load_user_preferences(user.id)
            preferences["llm_settings"] = {
                **preferences["llm_settings"],
                "enabled": False,
                "api_key": "",
            }
            user_preference_service.save_user_preferences(user.id, preferences)

    assert user_preference_service.PREFS_DIR == runtime_dir / "user_preferences"
    assert len(list((runtime_dir / "user_preferences").glob("user_*.json"))) == 2
    assert playbook_deviation_service.DEVIATIONS_PATH == runtime_dir / "playbook_deviations.json"
    assert legal_monitor.MONITOR_PATH == runtime_dir / "legal_monitor.json"
    assert material_file_storage.UPLOAD_ROOT == runtime_dir / "scenario_materials"

    client = _client(factory)

    # 1-2. Fresh public demo users can authenticate with their documented roles.
    business_token = _login(client, "biz@demo.vela")
    business_headers = _headers(business_token)
    business_status = client.get("/api/v1/onboarding/status", headers=business_headers)
    assert business_status.status_code == 200
    assert business_status.json() == {"completed": True, "required": False, "role": "business"}

    # 3. Business submits real material through the formal multipart endpoint.
    material = (
        "项目名称：坎皮纳斯储能系统组装厂。\n"
        "投资目的地：巴西圣保罗州坎皮纳斯市。\n"
        "投资结构：中资母公司通过巴西全资子公司投资，100% 外资。\n"
        "资金来源：境内自有资金及股东贷款。\n"
        "主要内容和规模：建设工业级新能源储能系统制造与组装绿地工厂，首年产能 200 MWh。\n"
        "项目计划创造约 120 名本地雇员，厂房占地 12,000 平方米，建设生产车间、研发中心和仓库。\n"
        "需办理外资企业设立、工业许可、环境评估、劳动登记、税务登记及州级 ICMS 激励。\n"
        "预计开工：2026-06-01。预计投产：2027-03-01。"
    )
    submit_response = client.post(
        "/api/v1/scenarios/submit-materials",
        headers=business_headers,
        data={
            "payload": json.dumps(
                {
                    "project_name": "坎皮纳斯储能系统组装厂",
                    "description": "拟在巴西圣保罗州建设新能源储能制造绿地工厂并雇佣当地员工。",
                    "scope_acknowledged": True,
                    "scope_notice_version": "scope-notice-v2",
                },
                ensure_ascii=False,
            )
        },
        files={"files": ("storage-project.txt", material.encode("utf-8"), "text/plain")},
    )
    assert submit_response.status_code == 201, submit_response.text
    submitted = submit_response.json()
    assert submitted["status"] == "pending_scope"
    scenario_id = submitted["id"]
    proposal = submitted["scenario_scope"]["proposed"]
    assert proposal["pack_id"] == "brazil_new_energy_greenfield"
    assert proposal["proposal_hash"]
    assert any((runtime_dir / "scenario_materials" / str(scenario_id)).iterdir())

    # 4. Legal demo login resolves the deterministic, versioned profile seeded for this user only.
    legal_token = _login(client, "legal@demo.vela")
    legal_headers = _headers(legal_token)
    legal_status = client.get("/api/v1/onboarding/status", headers=legal_headers)
    assert legal_status.status_code == 200
    assert legal_status.json() == {"completed": True, "required": True, "role": "legal"}
    legal_profile = client.get("/api/v1/onboarding/profile", headers=legal_headers)
    assert legal_profile.status_code == 200
    assert legal_profile.json()["completed"] is True
    assert legal_profile.json()["profile_version"] == DEMO_LEGAL_PROFILE_VERSION

    # 5. Confirming scope executes the real checklist -> keyword RAG -> brief pipeline.
    confirm_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/confirm-scope",
        headers=legal_headers,
        json={
            "compliance_dimensions": [
                "labor",
                "foreign_investment",
                "tax",
                "environment",
                "industry_access",
            ],
            "expected_proposal_hash": proposal["proposal_hash"],
            "fit_decision": "accept_warning",
            "match_threshold": 70,
            "retrieval_top_k": 3,
            "polish": False,
            "include_playbook_suggestions": True,
            "selected_issue_codes": [],
        },
    )
    assert confirm_response.status_code == 200, confirm_response.text
    generated = confirm_response.json()
    assert generated["status"] == "pending_legal_review"
    assert generated["checklist"]["total_items"] >= 15
    snapshot = generated["scenario_scope"]["snapshot"]
    assert snapshot["capability_pack_id"] == "brazil_new_energy_greenfield"
    assert snapshot["generation_input_hash"]
    assert snapshot["include_playbook_suggestions"] is True
    assert snapshot["audit_metadata"]["profile_snapshot"]["completed"] is True

    contract_upload = client.post(
        f"/api/v1/projects/{scenario_id}/contracts/upload?contract_type=general",
        headers=legal_headers,
        files={
            "file": (
                "supply-contract.txt",
                "Cláusula 1. A responsabilidade terá limitação de responsabilidade conforme a lei brasileira.".encode(
                    "utf-8"
                ),
                "text/plain",
            )
        },
    )
    assert contract_upload.status_code == 200, contract_upload.text
    contract_id = contract_upload.json()["id"]
    contract_analysis = client.post(
        f"/api/v1/projects/{scenario_id}/contracts/analyze?doc_id={contract_id}",
        headers=legal_headers,
    )
    assert contract_analysis.status_code == 200, contract_analysis.text
    assert contract_analysis.json()["summary"]["house_rules_profile"] is True

    brief_response = client.get(f"/api/v1/scenarios/{scenario_id}/brief", headers=legal_headers)
    assert brief_response.status_code == 200, brief_response.text
    brief = brief_response.json()
    assert brief["sections"]
    assert brief["mode"] == "template"
    assert brief["passed_count"] + brief["blocked_count"] == generated["checklist"]["total_items"]
    retrieval_response = client.post(f"/api/v1/scenarios/{scenario_id}/retrieve", headers=legal_headers)
    assert retrieval_response.status_code == 200, retrieval_response.text
    retrieval = retrieval_response.json()
    assert retrieval["total_hits"] > 0
    assert retrieval["sections"]
    assert (runtime_dir / "legal_index.json").exists()
    assert (runtime_dir / "legal_monitor.json").exists()

    # 6-7. Review is initialized from persisted generated data, fully approved, then finalized.
    review_response = client.post(f"/api/v1/scenarios/{scenario_id}/review/init", headers=legal_headers)
    assert review_response.status_code == 200, review_response.text
    review = review_response.json()
    assert review["status"] == "in_progress"
    assert review["items"]

    # Old clients that omit the revision fail closed instead of silently
    # overwriting a newer legal decision.
    assert client.post(
        f"/api/v1/scenarios/{scenario_id}/review/approve-all",
        headers=legal_headers,
    ).status_code == 422

    # The bundled corpus is deliberately provisional: no generated review
    # item can be S1 until every supporting source is expert_verified.  The
    # bulk endpoint must therefore fail closed instead of relabelling S2/S3.
    assert not any(
        item.get("tier") == "S1"
        and item.get("gate_status") == "passed"
        and not item.get("hard_block")
        for item in review["items"]
    )
    approve_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/review/approve-all",
        headers=legal_headers,
        params={"expected_revision": review["revision"]},
    )
    assert approve_response.status_code == 409, approve_response.text
    assert approve_response.json()["detail"] == "没有可批量确认的 S1 待审条目"
    approved = review
    # Provisional S2/S3 evidence must be confirmed item by item, with a
    # documented basis for S3.
    assert approved["pending_count"] > 0
    missing_item_precondition_checked = False
    for item in approved["items"]:
        if item["decision"] != "pending":
            continue
        comment = None
        if item.get("tier") == "S3" or item.get("hard_block"):
            comment = "演示复核：已核对本地冻结语料与官方链接；正式使用前仍须巴西执业律师确认法源定位。"
        if not missing_item_precondition_checked:
            missing = client.patch(
                f"/api/v1/scenarios/{scenario_id}/review/items/{item['code']}",
                headers=legal_headers,
                json={"decision": "approved", "comment": comment},
            )
            assert missing.status_code == 422, missing.text
            missing_item_precondition_checked = True
        response = client.patch(
            f"/api/v1/scenarios/{scenario_id}/review/items/{item['code']}",
            headers=legal_headers,
            json={
                "decision": "approved",
                "comment": comment,
                "expected_revision": approved["revision"],
            },
        )
        assert response.status_code == 200, response.text
        approved = response.json()
    assert approved["pending_count"] == 0
    assert approved["can_finalize"] is True

    assert client.post(
        f"/api/v1/scenarios/{scenario_id}/review/finalize",
        headers=legal_headers,
    ).status_code == 422

    finalize_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/review/finalize",
        headers=legal_headers,
        params={"expected_revision": approved["revision"]},
    )
    assert finalize_response.status_code == 200, finalize_response.text
    finalized = finalize_response.json()
    assert finalized["status"] == "approved"
    assert finalized["can_export"] is True

    # 8. Final review alone is not a delivery authorization.  Draft brief
    # preview remained available above, while every final artifact now fails
    # closed until Claim + CoverageProof bind the current snapshot.
    blocked_delivery = client.get(
        f"/api/v1/scenarios/{scenario_id}/export/docx", headers=legal_headers
    )
    assert blocked_delivery.status_code == 409, blocked_delivery.text
    assert blocked_delivery.json()["detail"]["reason_codes"] == [
        "claim_compilation_missing"
    ]

    fact_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/facts",
        headers=business_headers,
        json={
            "subject": "project",
            "attribute": "confirmed_project_material",
            "value": "坎皮纳斯储能系统组装厂项目材料",
            "fact_time": "2026-07-17",
            "block_id": "submitted-material:project",
            "fact_pack_version": "facts-v0.1",
            "source_document": "project-material.txt",
        },
    )
    assert fact_response.status_code == 201, fact_response.text
    fact_id = fact_response.json()["id"]
    fact_confirm = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/facts/{fact_id}/confirm",
        headers=business_headers,
        json={"confirmation_note": "业务提交人确认该事实与本次冻结项目材料一致。"},
    )
    assert fact_confirm.status_code == 200, fact_confirm.text

    drafts = []
    for section in brief["sections"]:
        for item in section["items"]:
            grounded_citations = [
                value for value in item["citations"] if value["grounded"]
            ]
            if not grounded_citations:
                continue
            citation = grounded_citations[0]
            drafts.append(
                {
                    "checklist_code": item["code"],
                    "statement": item["risk_zh"],
                    "fact_refs": [fact_id],
                    "evidence_refs": [f"{item['code']}:{citation['id']}"],
                }
            )
    assert drafts, "正式检索结果应至少支持一条真实法律 Claim 草稿"
    compilation_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/claims/compile",
        headers=legal_headers,
        json={"drafts": drafts},
    )
    assert compilation_response.status_code == 201, compilation_response.text
    first_compilation = compilation_response.json()
    assert first_compilation["compiler_version"] == "0.3"
    assert first_compilation["denominator_count"] == 30
    assert len(first_compilation["research_items"]) == 30
    assert len({item["checklist_code"] for item in first_compilation["research_items"]}) == 30
    assert all(claim["statement"].strip() for claim in first_compilation["claims"])

    # A critical supplemental fact enters through the formal business API and
    # is explicitly selected by legal in a real Claim draft.  Both compiler
    # input and output hashes must change; the compiler is not a fixed demo
    # response.  A third compilation restores the brief-bound legal wording
    # for the delivery gate while retaining the supplemental fact in history.
    supplemental_fact_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/facts",
        headers=business_headers,
        json={
            "subject": "project",
            "attribute": "hazardous_material_inventory",
            "value": "测试补充事实：规划阶段预计储存 18 吨危险化学品",
            "fact_time": "2026-07-18",
            "block_id": "submitted-material:hazardous-inventory",
            "fact_pack_version": "facts-v0.1",
            "source_document": "storage-project.txt",
            "assertion_polarity": "affirmative",
        },
    )
    assert supplemental_fact_response.status_code == 201, supplemental_fact_response.text
    supplemental_fact_id = supplemental_fact_response.json()["id"]
    supplemental_fact_confirm = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/facts/{supplemental_fact_id}/confirm",
        headers=business_headers,
        json={"confirmation_note": "业务提交人确认该补充测试事实来自本次正式上传材料。"},
    )
    assert supplemental_fact_confirm.status_code == 200, supplemental_fact_confirm.text
    drafts_with_supplemental_fact = [
        {
            **draft,
            "fact_refs": (
                [*draft["fact_refs"], supplemental_fact_id]
                if index == 0
                else draft["fact_refs"]
            ),
        }
        for index, draft in enumerate(drafts)
    ]
    changed_compilation_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/claims/compile",
        headers=legal_headers,
        json={"drafts": drafts_with_supplemental_fact},
    )
    assert changed_compilation_response.status_code == 201, changed_compilation_response.text
    changed_compilation = changed_compilation_response.json()
    assert changed_compilation["input_hash"] != first_compilation["input_hash"]
    assert changed_compilation["output_hash"] != first_compilation["output_hash"]
    assert any(
        supplemental_fact_id in claim["fact_refs"]
        for claim in changed_compilation["claims"]
    )

    gate_compilation_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/claims/compile",
        headers=legal_headers,
        json={"drafts": drafts},
    )
    assert gate_compilation_response.status_code == 201, gate_compilation_response.text
    compilation = gate_compilation_response.json()
    assert compilation["input_hash"] != first_compilation["input_hash"]
    assert compilation["output_hash"] == first_compilation["output_hash"]
    for claim in compilation["claims"]:
        if claim["status"] != "awaiting_human_confirmation":
            continue
        claim_response = client.post(
            f"/api/v1/scenarios/{scenario_id}/mechanism/claims/{claim['id']}/confirm",
            headers=legal_headers,
            json={
                "decision": "confirmed",
                "confirmation_note": "终审法务逐项核对事实、限定表述与冻结法源定位后确认。",
            },
        )
        assert claim_response.status_code == 200, claim_response.text
    proof_response = client.post(
        f"/api/v1/scenarios/{scenario_id}/mechanism/coverage-proofs",
        headers=legal_headers,
        json={
            "compilation_id": compilation["id"],
            "denominator_ref": "frozen checklist and evidence snapshot",
        },
    )
    assert proof_response.status_code == 201, proof_response.text
    proof_body = proof_response.json()["proof"]
    assert proof_body["schema_version"] == "0.2"
    assert proof_body["pack_total"] == 30
    assert proof_body["pack_total"] == (
        proof_body["scope_total"] + proof_body["out_of_scope_by_scope_count"]
    )
    assert proof_body["scope_total"] == sum(
        proof_body[f"{disposition}_count"]
        for disposition in (
            "supported",
            "not_applicable",
            "rejected",
            "unanswerable",
            "uncovered",
        )
    )

    audit_response = client.get(
        f"/api/v1/scenarios/{scenario_id}/mechanism/audit",
        headers=legal_headers,
    )
    assert audit_response.status_code == 200, audit_response.text
    audit_actions = [event["action"] for event in audit_response.json()]
    assert audit_actions.count("mechanism.claim_compile") == 3
    assert "mechanism.fact_create" in audit_actions
    assert "mechanism.fact_business_confirm" in audit_actions

    # Stored-proof corruption is distinguished from ordinary workflow staleness
    # and is also audit logged as a blocked 422 delivery attempt.
    with factory() as db:
        from app.models.mechanism import CoverageProof

        stored_proof = db.get(CoverageProof, proof_response.json()["id"])
        original_proof_hash = stored_proof.proof_hash
        stored_proof.proof_hash = "f" * 64
        db.commit()
    corrupt_delivery = client.get(
        f"/api/v1/scenarios/{scenario_id}/export/audit-bundle", headers=legal_headers
    )
    assert corrupt_delivery.status_code == 422, corrupt_delivery.text
    assert "coverage_proof_stored_hash_invalid" in corrupt_delivery.json()["detail"][
        "reason_codes"
    ]
    with factory() as db:
        from app.models.mechanism import CoverageProof

        stored_proof = db.get(CoverageProof, proof_response.json()["id"])
        stored_proof.proof_hash = original_proof_hash
        db.commit()

    # Passing Answerability does not create an external legal authorization.
    # Demo identities have no OAB credential, ITI-validated artifact signature,
    # customer UAT, gold run or production provenance, so every final download
    # remains blocked.  This is an intentional real-client boundary.
    for artifact_path in ("audit-bundle", "docx", "pdf"):
        response = client.get(
            f"/api/v1/scenarios/{scenario_id}/export/{artifact_path}",
            headers=legal_headers,
        )
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["delivery_allowed"] is False
        assert detail["blocking_reasons"] == ["active_delivery_release_missing"]

    with factory() as db:
        from app.models.audit_log import AuditLog
        from app.models.scenario import InvestigationScenario, ScenarioGenerationAttempt

        scenario = db.get(InvestigationScenario, scenario_id)
        assert scenario is not None
        assert scenario.status == "review_approved"
        attempts = db.query(ScenarioGenerationAttempt).filter_by(scenario_id=scenario_id).all()
        assert len(attempts) == 1
        assert attempts[0].status == "succeeded"
        blocked_gate_logs = (
            db.query(AuditLog)
            .filter(AuditLog.action == "delivery.answerability_gate_blocked")
            .all()
        )
        assert len(blocked_gate_logs) == 2
        blocked_details = "\n".join(entry.detail or "" for entry in blocked_gate_logs)
        assert "claim_compilation_missing" in blocked_details
        assert "coverage_proof_stored_hash_invalid" in blocked_details
        customer_release_logs = (
            db.query(AuditLog)
            .filter(AuditLog.action == "delivery.customer_release_blocked")
            .all()
        )
        assert len(customer_release_logs) == 3
        assert all("active_delivery_release_missing" in (entry.detail or "") for entry in customer_release_logs)
    client.close()
