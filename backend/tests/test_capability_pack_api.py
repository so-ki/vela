"""Real API/transaction coverage for the Capability Pack boundary.

All database, upload, manifest, and artifact mutations live under ``tmp_path``.
The production Capability Pack tree is read-only to this test module.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

import app.capability_packs.registry as registry_module
import app.services.material_file_storage as material_file_storage
import app.services.scenario_pipeline as scenario_pipeline
import app.services.scenario_scope_service as scope_service
from app.capability_packs.registry import CAPABILITY_PACKS_ROOT, CapabilityPackRegistry
from app.core.database import Base, get_db
from app.core.deps import get_current_legal_user, get_current_user
from app.main import create_app
from app.models.scenario import (
    InvestigationScenario,
    ScenarioGenerationAttempt,
    ScenarioGenerationInput,
)
from app.models.user import User
from app.schemas.scenario import BusinessSubmitRequest
from app.services.generation_guard import stable_hash
from app.services.scenario_service import _materials_only_payload


FORMAL_PACK_ID = "brazil_new_energy_greenfield"
FIXTURE_PACK_ID = "test_fixture_pack"
FORMAL_DIMENSIONS = ["labor", "foreign_investment"]
_PROPOSAL_SEMANTIC_KEYS = (
    "pack_id",
    "pack_version",
    "pack_hash",
    "rules_artifact_id",
    "country",
    "state",
    "city",
    "industry",
    "action_type",
)


@pytest.fixture()
def db_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'capability-api.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(id=1, email="pack-business@example.com", full_name="Pack Business", role="business"),
                User(id=2, email="pack-legal@example.com", full_name="Pack Legal", role="legal"),
            ]
        )
        db.commit()
    return factory


@pytest.fixture(autouse=True)
def isolated_upload_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(material_file_storage, "UPLOAD_ROOT", tmp_path / "scenario_materials")


def _api_client(factory, user_id: int) -> TestClient:
    app = create_app()

    def override_db():
        with factory() as db:
            yield db

    def override_user():
        with factory() as db:
            return db.get(User, user_id)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_legal_user] = override_user
    return TestClient(app)


def _formal_payload(project_name: str = "巴西新能源绿地工厂") -> dict:
    return {
        "project_name": project_name,
        "country": "BR",
        "state": "sao_paulo",
        "industry": "new_energy_manufacturing",
        "action_type": "greenfield_plant",
        "investment_structure": "境外投资人通过巴西子公司实施投资",
        "project_content_scale": "建设新能源电池、储能与电动汽车制造工厂",
        "description": "项目拟在巴西圣保罗州建设新能源制造绿地工厂并雇佣当地员工。",
        "scope_acknowledged": True,
        "scope_notice_version": "scope-notice-v2",
    }


def _submit_formal(client: TestClient, project_name: str = "巴西新能源绿地工厂") -> dict:
    response = client.post(
        "/api/v1/scenarios/submit-materials",
        data={"payload": json.dumps(_formal_payload(project_name), ensure_ascii=False)},
        files=[
            (
                "files",
                (
                    "proposal.txt",
                    "巴西圣保罗州新能源制造绿地设厂投资方案".encode(),
                    "text/plain",
                ),
            )
        ],
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm_body(proposal: dict, **updates) -> dict:
    body = {
        "compliance_dimensions": FORMAL_DIMENSIONS,
        "expected_proposal_hash": proposal["proposal_hash"],
        "fit_decision": "fit",
        "match_threshold": 73,
        "retrieval_top_k": 2,
        "polish": False,
        "include_playbook_suggestions": False,
        "selected_issue_codes": [],
    }
    body.update(updates)
    return body


def _freeze_failed_snapshot(
    factory,
    business_client: TestClient,
    legal_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    project_name: str,
) -> tuple[int, dict]:
    submitted = _submit_formal(business_client, project_name)
    proposal = submitted["scenario_scope"]["proposed"]

    def stop_after_snapshot(*args, **kwargs):
        raise ValueError("controlled stop after snapshot")

    monkeypatch.setattr(scenario_pipeline, "run_generate_investigation_pack", stop_after_snapshot)
    response = legal_client.post(
        f"/api/v1/scenarios/{submitted['id']}/confirm-scope",
        json=_confirm_body(proposal),
    )
    assert response.status_code == 400, response.text
    with factory() as db:
        scenario = db.get(InvestigationScenario, submitted["id"])
        snapshot = copy.deepcopy(scenario.scenario_scope["snapshot"])
        assert scenario.status == "scope_generation_failed"
        assert snapshot
    return submitted["id"], snapshot


def _proposal_hash(proposal: dict) -> str:
    return stable_hash({key: proposal.get(key) for key in _PROPOSAL_SEMANTIC_KEYS})


def _isolated_registry_root(tmp_path: Path) -> tuple[Path, Path, Path]:
    app_root = tmp_path / "isolated_app"
    capability_root = app_root / "capability_packs"
    pack_root = capability_root / FORMAL_PACK_ID
    rules_root = app_root / "rules"
    data_root = app_root / "data"
    pack_root.mkdir(parents=True)
    rules_root.mkdir(parents=True)
    data_root.mkdir(parents=True)

    source_manifest = CAPABILITY_PACKS_ROOT / FORMAL_PACK_ID / "manifest.json"
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    target_manifest = pack_root / "manifest.json"
    shutil.copy2(source_manifest, target_manifest)
    rules_name = manifest["rules_artifact"]["resource"].split("://", 1)[1]
    corpus_name = manifest["corpus_artifact"]["resource"].split("://", 1)[1]
    target_rules = rules_root / rules_name
    target_corpus = data_root / corpus_name
    shutil.copy2(CAPABILITY_PACKS_ROOT.parent / "rules" / rules_name, target_rules)
    shutil.copy2(CAPABILITY_PACKS_ROOT.parent / "data" / corpus_name, target_corpus)
    return capability_root, target_manifest, target_rules


def test_catalog_api_returns_only_the_formal_brazil_pack(db_factory):
    client = _api_client(db_factory, 1)
    try:
        response = client.get("/api/v1/capability-packs")
        assert response.status_code == 200, response.text
        assert [item["pack_id"] for item in response.json()] == [FORMAL_PACK_ID]
        assert all(item["pack_id"] != FIXTURE_PACK_ID for item in response.json())

        catalog_response = client.get("/api/v1/capability-packs/catalog")
        assert catalog_response.status_code == 200, catalog_response.text
        catalog = catalog_response.json()
        assert catalog["capability_pack"]["pack_id"] == FORMAL_PACK_ID
        assert catalog["capability_pack"]["version"] == "1.3.0"
        assert catalog["capability_pack"]["content_status"] == "provisional"
        assert catalog["capability_pack"]["status"] == "active"
        assert catalog["rules_artifact"]["artifact_id"] == "brazil_new_energy"
        assert catalog["corpus_artifact"]["artifact_id"] == "brazil_legal_corpus"
    finally:
        client.close()


def test_submit_materials_api_persists_authoritative_pack_identity(db_factory):
    client = _api_client(db_factory, 1)
    try:
        submitted = _submit_formal(client)
    finally:
        client.close()

    proposed = submitted["scenario_scope"]["proposed"]
    formal_pack = CapabilityPackRegistry(app_env="production").get(FORMAL_PACK_ID)
    assert proposed["pack_id"] == formal_pack.manifest.pack_id
    assert proposed["pack_version"] == formal_pack.manifest.version
    assert proposed["pack_hash"] == formal_pack.manifest.semantic_hash
    assert proposed["rules_artifact_id"] == formal_pack.manifest.rules_artifact.artifact_id
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, submitted["id"])
        assert scenario.rules_pack_id == formal_pack.manifest.rules_artifact.artifact_id
        assert scenario.scenario_scope["proposed"]["pack_id"] == FORMAL_PACK_ID


def test_unmatched_submit_api_fails_without_creating_default_brazil_project(db_factory):
    client = _api_client(db_factory, 1)
    try:
        response = client.post(
            "/api/v1/scenarios/submit-materials",
            json={
                "project_name": "墨西哥矿业并购",
                "country": "MX",
                "industry": "mining",
                "action_type": "acquisition",
                "description": "拟在墨西哥收购一项矿业资产并开展后续运营。",
                "scope_acknowledged": True,
            },
        )
        assert 400 <= response.status_code < 500, response.text
        assert "Capability Pack" in response.text or "支持" in response.text
    finally:
        client.close()
    with db_factory() as db:
        assert db.query(InvestigationScenario).count() == 0


def test_uploaded_source_text_participates_in_pack_matching(db_factory):
    client = _api_client(db_factory, 1)
    try:
        response = client.post(
            "/api/v1/scenarios/submit-materials",
            data={
                "payload": json.dumps(
                    {
                        "project_name": "上传材料决定路由",
                        "description": "请以后端归档的原始方案文件作为能力包路由证据。",
                        "scope_acknowledged": True,
                    },
                    ensure_ascii=False,
                )
            },
            files=[
                (
                    "files",
                    (
                        "route-evidence.txt",
                        "项目位于巴西圣保罗州，拟建设新能源电池制造绿地工厂。".encode(),
                        "text/plain",
                    ),
                )
            ],
        )
        assert response.status_code == 201, response.text
        assert response.json()["scenario_scope"]["proposed"]["pack_id"] == FORMAL_PACK_ID
    finally:
        client.close()


def test_client_route_fields_cannot_force_a_pack_against_uploaded_material(db_factory):
    client = _api_client(db_factory, 1)
    try:
        forced = _formal_payload("伪造路由字段")
        forced.update(
            {
                "country": "BR",
                "industry": "new_energy_manufacturing",
                "action_type": "greenfield_plant",
                "project_content_scale": "收购既有铜矿企业与采矿权",
                "description": "本项目拟在墨西哥收购铜矿企业并取得既有采矿权。",
            }
        )
        response = client.post(
            "/api/v1/scenarios/submit-materials",
            data={"payload": json.dumps(forced, ensure_ascii=False)},
            files=[
                (
                    "files",
                    (
                        "mexico-mining.txt",
                        "墨西哥铜矿企业并购及既有采矿权收购方案".encode(),
                        "text/plain",
                    ),
                )
            ],
        )
        assert 400 <= response.status_code < 500, response.text
    finally:
        client.close()
    with db_factory() as db:
        assert db.query(InvestigationScenario).count() == 0


def test_legacy_pending_scope_cannot_receive_the_current_pack_implicitly(db_factory):
    business_client = _api_client(db_factory, 1)
    legal_client = _api_client(db_factory, 2)
    try:
        submitted = _submit_formal(business_client, "历史 Scope 不得隐式绑定当前能力包")
        proposal = submitted["scenario_scope"]["proposed"]
        with db_factory() as db:
            scenario = db.get(InvestigationScenario, submitted["id"])
            scenario.scenario_scope = None
            flag_modified(scenario, "scenario_scope")
            db.commit()

        response = legal_client.post(
            f"/api/v1/scenarios/{submitted['id']}/confirm-scope",
            json=_confirm_body(proposal),
        )
        assert response.status_code == 409, response.text
        assert "不能隐式选择" in response.text
    finally:
        business_client.close()
        legal_client.close()

    with db_factory() as db:
        scenario = db.get(InvestigationScenario, submitted["id"])
        assert scenario.status == "pending_scope"
        assert scenario.scope_snapshot_hash is None
        assert db.query(ScenarioGenerationAttempt).count() == 0


def test_confirm_api_revalidates_proposed_pack_identity(db_factory):
    business_client = _api_client(db_factory, 1)
    legal_client = _api_client(db_factory, 2)
    try:
        submitted = _submit_formal(business_client, "待重验能力包身份")
        with db_factory() as db:
            scenario = db.get(InvestigationScenario, submitted["id"])
            scope = copy.deepcopy(scenario.scenario_scope)
            proposal = scope["proposed"]
            proposal["pack_version"] = "9.9.9"
            proposal["proposal_hash"] = _proposal_hash(proposal)
            scenario.scenario_scope = scope
            flag_modified(scenario, "scenario_scope")
            db.commit()

        response = legal_client.post(
            f"/api/v1/scenarios/{submitted['id']}/confirm-scope",
            json=_confirm_body(proposal),
        )
        assert 400 <= response.status_code < 500, response.text
    finally:
        business_client.close()
        legal_client.close()

    with db_factory() as db:
        scenario = db.get(InvestigationScenario, submitted["id"])
        assert scenario.status == "pending_scope"
        assert scenario.scope_snapshot_hash is None
        assert scenario.scenario_scope.get("snapshot") is None
        assert db.query(ScenarioGenerationAttempt).count() == 0


def test_confirm_api_snapshot_freezes_pack_artifacts_retrieval_and_output(
    db_factory, monkeypatch: pytest.MonkeyPatch
):
    business_client = _api_client(db_factory, 1)
    legal_client = _api_client(db_factory, 2)
    try:
        scenario_id, snapshot = _freeze_failed_snapshot(
            db_factory,
            business_client,
            legal_client,
            monkeypatch,
            project_name="冻结 Capability Pack 全量身份",
        )
    finally:
        business_client.close()
        legal_client.close()

    pack = CapabilityPackRegistry(app_env="production").get(FORMAL_PACK_ID)
    manifest = pack.manifest
    assert snapshot["capability_pack_id"] == manifest.pack_id
    assert snapshot["capability_pack_version"] == manifest.version
    assert snapshot["capability_pack_hash"] == manifest.semantic_hash
    assert snapshot["issue_modules"] == list(manifest.issue_modules)
    assert snapshot["rules_artifact_id"] == manifest.rules_artifact.artifact_id
    assert snapshot["rules_artifact_version"] == manifest.rules_artifact.version
    assert snapshot["rules_artifact_hash"] == manifest.rules_artifact.content_hash
    assert snapshot["corpus_artifact_id"] == manifest.corpus_artifact.artifact_id
    assert snapshot["corpus_artifact_version"] == manifest.corpus_artifact.version
    assert snapshot["corpus_artifact_hash"] == manifest.corpus_artifact.content_hash
    assert snapshot["retrieval_config"] == manifest.retrieval_config.model_dump(mode="json")
    assert snapshot["output_profile"] == manifest.output_profile.model_dump(mode="json")
    assert snapshot["generation_input_id"]
    assert snapshot["generation_input_hash"]
    with db_factory() as db:
        record = db.get(ScenarioGenerationInput, snapshot["generation_input_id"])
        assert record is not None
        assert record.scenario_id == scenario_id
        assert record.input_hash == snapshot["generation_input_hash"]


def test_retry_api_uses_original_snapshot_without_registry_match(
    db_factory, monkeypatch: pytest.MonkeyPatch
):
    business_client = _api_client(db_factory, 1)
    legal_client = _api_client(db_factory, 2)
    try:
        scenario_id, original_snapshot = _freeze_failed_snapshot(
            db_factory,
            business_client,
            legal_client,
            monkeypatch,
            project_name="Retry 不重新匹配能力包",
        )

        def forbidden_match(*args, **kwargs):
            raise AssertionError("retry must not run registry matching")

        monkeypatch.setattr(CapabilityPackRegistry, "match", forbidden_match)
        monkeypatch.setattr(CapabilityPackRegistry, "match_material", forbidden_match)
        monkeypatch.setattr(
            scenario_pipeline,
            "run_generate_investigation_pack",
            lambda db, user, scenario, **kwargs: scenario,
        )
        response = legal_client.post(f"/api/v1/scenarios/{scenario_id}/retry-generation")
        assert response.status_code == 200, response.text
    finally:
        business_client.close()
        legal_client.close()

    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        assert scenario.scenario_scope["snapshot"] == original_snapshot
        assert db.query(ScenarioGenerationInput).count() == 1
        assert db.query(ScenarioGenerationAttempt).count() == 2


@pytest.mark.parametrize("tamper_kind", ["manifest", "artifact"])
def test_old_snapshot_fails_closed_when_pack_or_artifact_is_tampered_in_isolated_root(
    db_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_kind: str,
):
    business_client = _api_client(db_factory, 1)
    legal_client = _api_client(db_factory, 2)
    try:
        scenario_id, _ = _freeze_failed_snapshot(
            db_factory,
            business_client,
            legal_client,
            monkeypatch,
            project_name=f"隔离篡改检查-{tamper_kind}",
        )
        root, manifest_path, rules_path = _isolated_registry_root(tmp_path)
        if tamper_kind == "manifest":
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["output_profile"]["brief_title"] = "tmp-only tampered title"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            rules["pack"]["name"] = "tmp-only tampered rules"
            rules_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        isolated_registry = CapabilityPackRegistry(root=root, app_env="production")
        monkeypatch.setattr(registry_module, "get_capability_pack_registry", lambda: isolated_registry)
        monkeypatch.setattr(scope_service, "get_capability_pack_registry", lambda: isolated_registry)
        response = legal_client.post(f"/api/v1/scenarios/{scenario_id}/retry-generation")
        assert response.status_code == 409, response.text
    finally:
        business_client.close()
        legal_client.close()


def test_fixture_pack_only_builds_service_proposal_and_snapshot_without_formal_project(
    db_factory, monkeypatch: pytest.MonkeyPatch
):
    registry = CapabilityPackRegistry(app_env="test", include_test_fixtures=True)
    fixture_pack = registry.get(FIXTURE_PACK_ID)
    payload = BusinessSubmitRequest(
        project_name="fixture-country-token fixture-state-token fixture-industry-token fixture-action-token",
        country="ZZ-TEST",
        state="ZZ-STATE",
        industry="fixture_industry",
        action_type="fixture_action",
        description="fixture-country-token fixture-state-token fixture-industry-token fixture-action-token material",
        scope_acknowledged=True,
    )
    with db_factory() as db:
        business = db.get(User, 1)
        scope = scope_service.build_proposed_scenario_scope(payload, business, registry=registry)
        proposal = scope["proposed"]
        transient = InvestigationScenario(
            user_id=business.id,
            project_name=payload.project_name,
            rules_pack_id=proposal["rules_artifact_id"],
            scenario_scope=scope,
            is_demo=False,
            country=proposal["country"],
            state=proposal["state"],
            city=proposal["city"],
            industry=proposal["industry"],
            action_type=proposal["action_type"],
            description=payload.description,
            compliance_dimensions=[],
            status="pending_scope",
        )
        snapshot = scope_service._snapshot_for_request(
            transient,
            business,
            "f" * 64,
            "fixture-generation-input",
            expected_proposal_hash=proposal["proposal_hash"],
            compliance_dimensions=["fixture_issue"],
            selected_issue_codes=[],
            match_threshold=70,
            retrieval_top_k=1,
            fit_decision="fit",
            polish=False,
            include_playbook_suggestions=False,
            registry=registry,
        )
        materials_payload = _materials_only_payload(
            payload,
            capability_pack=fixture_pack,
        )
        assert db.query(InvestigationScenario).count() == 0

    assert transient.id is None
    assert proposal["pack_id"] == FIXTURE_PACK_ID
    assert snapshot["capability_pack_id"] == FIXTURE_PACK_ID
    assert snapshot["rules_artifact_id"] == fixture_pack.manifest.rules_artifact.artifact_id
    assert snapshot["corpus_artifact_id"] == fixture_pack.manifest.corpus_artifact.artifact_id
    assert materials_payload["industry_pack_id"] == fixture_pack.manifest.rules_artifact.artifact_id
    assert FIXTURE_PACK_ID not in {item["pack_id"] for item in registry.list_public_active()}
