from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.api import scenarios as scenario_api
from app.core.database import Base
from app.core.database import get_db
from app.core.deps import get_current_legal_user, get_current_user
from app.main import create_app
from app.models.scenario import InvestigationScenario, ScenarioGenerationAttempt, ScenarioGenerationInput
from app.models.user import User
from app.schemas.scenario import BusinessSubmitRequest, ScenarioCreateRequest
from app.services.generation_guard import (
    GenerationConflictError,
    GenerationGuardError,
    load_generation_context,
    require_generation_config,
    snapshot_hash,
)
from app.services.audit_bundle_service import build_audit_bundle
from app.services.retrieval_expansion import retrieve_item_with_expansion
from app.services.scenario_pipeline import _safe_audit, mark_generation_failed, run_generate_investigation_pack
from app.services.scenario_scope_service import acquire_generation_lease, build_proposed_scenario_scope
from app.services.scenario_service import create_scenario_materials_only
from app.services.legal_agent_service import run_investigation_agent
from app.services.rule_engine import ScenarioInput, generate_checklist, get_demo_scenario_template
from app.services.legal_rag import retrieve_for_checklist
from app.services.brief_generator import generate_brief


DIMS = ["labor", "foreign_investment", "tax", "environment", "industry_access"]


@pytest.fixture()
def db_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'scope.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(id=1, email="business@example.com", full_name="business", role="business"),
                User(id=2, email="legal@example.com", full_name="legal", role="legal"),
            ]
        )
        db.commit()
    return factory


def payload(**updates) -> BusinessSubmitRequest:
    data = {
        "project_name": "巴西圣保罗州新能源绿地工厂",
        "description": "计划在巴西圣保罗州绿地设厂，新建新能源制造工厂并雇佣当地员工。",
        "scope_acknowledged": True,
    }
    data.update(updates)
    return BusinessSubmitRequest(**data)


def create_pending(factory) -> int:
    with factory() as db:
        user = db.get(User, 1)
        scenario = create_scenario_materials_only(db, user, payload())
        return scenario.id


def request_for(scenario: InvestigationScenario, **updates):
    data = dict(
        expected_proposal_hash=scenario.scenario_scope["proposed"]["proposal_hash"],
        compliance_dimensions=DIMS,
        selected_issue_codes=[],
        match_threshold=70,
        retrieval_top_k=3,
        fit_decision="accept_warning",
        polish=False,
        include_playbook_suggestions=False,
    )
    data.update(updates)
    return data


def test_business_ack_and_authoritative_proposal(db_factory):
    with db_factory() as db:
        business = db.get(User, 1)
        with pytest.raises(ValueError, match="知悉"):
            build_proposed_scenario_scope(payload(scope_acknowledged=False), business)
        scope = build_proposed_scenario_scope(payload(), business)
        assert scope["proposed"]["rules_pack_id"] == "brazil_new_energy"
        assert scope["proposed"]["state"] == "sao_paulo"
        assert scope["proposed"]["action_type"] == "greenfield_plant"
        with pytest.raises(ValueError, match="受控试点"):
            build_proposed_scenario_scope(payload(country="mexico"), business)


def test_demo_template_explicitly_evidences_the_frozen_greenfield_scope(db_factory):
    template = get_demo_scenario_template()
    template.pop("compliance_dimensions", None)
    request = BusinessSubmitRequest(
        **template,
        scope_acknowledged=True,
        scope_notice_version="scope-notice-v2",
    )
    with db_factory() as db:
        scope = build_proposed_scenario_scope(request, db.get(User, 1))
    assert scope["proposed"]["pack_id"] == "brazil_new_energy_greenfield"
    assert "绿地设厂" in request.description


def test_business_city_is_preserved_instead_of_defaulting_to_first_rules_city(db_factory):
    with db_factory() as db:
        business = db.get(User, 1)
        scope = build_proposed_scenario_scope(payload(city="sorocaba"), business)

    assert scope["proposed"]["state"] == "sao_paulo"
    assert scope["proposed"]["city"] == "sorocaba"


def test_rio_city_field_is_conflict_evidence_and_cannot_be_rewritten(db_factory):
    with db_factory() as db:
        business = db.get(User, 1)
        with pytest.raises(ValueError, match="受控试点"):
            build_proposed_scenario_scope(payload(city="Rio de Janeiro"), business)


def test_same_concurrent_confirmation_gets_one_attempt(db_factory):
    scenario_id = create_pending(db_factory)

    def confirm(reverse: bool):
        with db_factory() as db:
            scenario = db.get(InvestigationScenario, scenario_id)
            legal = db.get(User, 2)
            dims = list(reversed(DIMS)) if reverse else DIMS
            return acquire_generation_lease(db, scenario, legal, **request_for(scenario, compliance_dimensions=dims))

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(confirm, [False, True]))
    assert sum(1 for lease in leases if lease.acquired) == 1
    assert len({lease.attempt_id for lease in leases}) == 1
    with db_factory() as db:
        assert db.query(ScenarioGenerationAttempt).count() == 1


def test_different_concurrent_confirmation_conflicts(db_factory):
    scenario_id = create_pending(db_factory)

    def confirm(top_k: int):
        with db_factory() as db:
            scenario = db.get(InvestigationScenario, scenario_id)
            legal = db.get(User, 2)
            try:
                return acquire_generation_lease(db, scenario, legal, **request_for(scenario, retrieval_top_k=top_k))
            except GenerationConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, [3, 4]))
    assert results.count("conflict") == 1
    assert sum(getattr(item, "acquired", False) for item in results if item != "conflict") == 1


def test_tampered_snapshot_is_rejected(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        lease = acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))
        assert lease.acquired
        snapshot = dict(scenario.scenario_scope["snapshot"])
        snapshot["match_threshold"] = 95
        scope = dict(scenario.scenario_scope)
        scope["snapshot"] = snapshot
        scenario.scenario_scope = scope
        db.commit()
        with pytest.raises(ValueError, match="哈希"):
            load_generation_context(db, scenario, attempt_id=lease.attempt_id, lease_token=lease.lease_token)


def test_user_preferences_cannot_override_frozen_threshold_or_topk(db_factory, monkeypatch):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        lease = acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))
        config = load_generation_context(db, scenario, attempt_id=lease.attempt_id, lease_token=lease.lease_token)
    seen = {}
    monkeypatch.setattr(
        "app.services.legal_agent_service.retrieve_for_checklist",
        lambda db, sections, **kwargs: seen.update(kwargs) or {"sections": [], "total_hits": 0, "zero_hit_items": []},
    )
    monkeypatch.setattr(
        "app.services.legal_agent_service.verify_sections_grounding",
        lambda sections, **kwargs: {"sections": sections, "requires_legal_check": False},
    )
    monkeypatch.setattr(
        "app.services.legal_agent_service.classify_sections",
        lambda sections, **kwargs: {"sections": sections, "tier_summary": {}},
    )
    with db_factory() as service_db:
        config = load_generation_context(
            service_db,
            service_db.get(InvestigationScenario, scenario_id),
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
        )
        run_investigation_agent(
            service_db,
            [],
            match_threshold=70,
            retrieval_top_k=3,
            user_id=2,
            use_brazil_connector=False,
            generation_config=config,
        )
    assert seen["match_threshold"] == 70
    assert seen["top_k"] == 3


def test_llm_intent_cannot_expand_snapshot_dimensions(db_factory, monkeypatch):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        args = request_for(scenario, compliance_dimensions=["labor"])
        lease = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        config = load_generation_context(db, scenario, attempt_id=lease.attempt_id, lease_token=lease.lease_token)
        called = {"value": False}
        monkeypatch.setattr(
            "app.services.intent_parser.parse_scenario_intent",
            lambda **kwargs: called.update(value=True) or ({"dimensions": ["tax"]}, None),
        )
        result = generate_checklist(
            db,
            ScenarioInput(
                project_name=scenario.project_name,
                country=config.country,
                state=config.state,
                city=config.city,
                industry=config.industry,
                action_type=config.action_type,
                investment_structure=scenario.investment_structure or "",
                description=scenario.description,
                compliance_dimensions=["labor"],
                rules_pack_id=config.rules_pack_id,
            ),
            config.rules_pack_id,
            generation_config=config,
        )
        assert called["value"] is False
        assert result["selected_dimensions"] == ["labor"]


def test_repeat_success_and_failed_retry_reuse_snapshot(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        legal = db.get(User, 2)
        args = request_for(scenario)
        first = acquire_generation_lease(db, scenario, legal, **args)
        snapshot_hash = scenario.scope_snapshot_hash
        assert mark_generation_failed(
            db, scenario_id, first.attempt_id, first.lease_owner, first.lease_token, RuntimeError("boom")
        )
        db.refresh(scenario)
        retry = acquire_generation_lease(db, scenario, legal, **args)
        assert retry.acquired and retry.attempt_id != first.attempt_id
        assert scenario.scope_snapshot_hash == snapshot_hash
        db.execute(
            update(InvestigationScenario)
            .where(InvestigationScenario.id == scenario_id)
            .values(status="pending_legal_review", active_generation_attempt_id=None)
        )
        db.commit()
        db.refresh(scenario)
        completed = acquire_generation_lease(db, scenario, legal, **args)
        assert not completed.acquired and completed.outcome == "completed"


def test_late_failure_cannot_overwrite_success(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        lease = acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))
        db.execute(
            update(InvestigationScenario)
            .where(InvestigationScenario.id == scenario_id)
            .values(status="pending_legal_review", active_generation_attempt_id=None)
        )
        db.commit()
        assert mark_generation_failed(
            db, scenario_id, lease.attempt_id, lease.lease_owner, lease.lease_token, RuntimeError("late")
        ) is False
        assert db.get(InvestigationScenario, scenario_id).status == "pending_legal_review"


def test_audit_failure_does_not_change_business_state(db_factory, monkeypatch):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        scenario.status = "pending_legal_review"
        db.commit()
        monkeypatch.setattr("app.services.scenario_pipeline.write_audit_log", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("audit")))
        _safe_audit(db, user=db.get(User, 2), action="x", resource_type="scenario", resource_id=str(scenario_id))
        assert db.get(InvestigationScenario, scenario_id).status == "pending_legal_review"


def test_formal_api_bypasses_fail_closed(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        business = db.get(User, 1)
        legal = db.get(User, 2)
        create_payload = ScenarioCreateRequest(
            project_name="x",
            description="这是足够长的场景描述文本",
            compliance_dimensions=["labor"],
        )
        with pytest.raises(HTTPException) as create_exc:
            scenario_api.create_scenario(create_payload, db, legal)
        assert create_exc.value.status_code == 410
        for call in (
            lambda: scenario_api.retrieve_legal_sources(scenario_id, db, business),
            lambda: scenario_api.create_brief(scenario_id, False, db, business),
            lambda: scenario_api.start_review(scenario_id, db, legal),
        ):
            with pytest.raises(HTTPException) as exc:
                call()
            assert exc.value.status_code == 409


def test_internal_checklist_rag_and_brief_require_snapshot_config(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        raw = ScenarioInput(
            project_name=scenario.project_name,
            country=scenario.country,
            state=scenario.state,
            city=scenario.city,
            industry=scenario.industry,
            action_type=scenario.action_type,
            investment_structure="",
            description=scenario.description,
            compliance_dimensions=["labor"],
        )
        with pytest.raises(ValueError, match="冻结生成"):
            generate_checklist(db, raw)
        with pytest.raises(ValueError, match="冻结生成"):
            retrieve_for_checklist(db, [])
        with pytest.raises(ValueError, match="冻结生成"):
            generate_brief(db, scenario, {}, sections_with_legal=[])


def test_checklist_view_never_auto_retrieves():
    source = (pytest.importorskip("pathlib").Path(__file__).parents[2] / "frontend/src/views/ChecklistView.vue").read_text()
    assert "retrieveLegalSources" not in source
    assert "runRetrieval" not in source


def test_generation_input_is_frozen_across_material_change_and_retry(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        args = request_for(scenario)
        first = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        config = load_generation_context(
            db, scenario, attempt_id=first.attempt_id, lease_token=first.lease_token
        )
        frozen_description = config.generation_input["scenario_input"]["description"]
        assert mark_generation_failed(
            db, scenario_id, first.attempt_id, first.lease_owner, first.lease_token, RuntimeError("crash")
        )
        scenario = db.get(InvestigationScenario, scenario_id)
        scenario.description = "快照后被修改且不得进入 retry 的材料内容"
        db.commit()
        retry = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        retry_config = load_generation_context(
            db, scenario, attempt_id=retry.attempt_id, lease_token=retry.lease_token
        )
        assert retry_config.generation_input["scenario_input"]["description"] == frozen_description
        assert retry_config.generation_input_hash == config.generation_input_hash
        assert retry_config.config_hash == config.config_hash


def test_incremental_baseline_or_previous_pack_tampering_fails(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        lease = acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))
        snapshot = scenario.scenario_scope["snapshot"]
        record = db.get(ScenarioGenerationInput, snapshot["generation_input_id"])
        record.payload["incremental"]["baseline"] = {"description": "tampered"}
        flag_modified(record, "payload")
        db.commit()
        with pytest.raises(GenerationGuardError, match="input 哈希"):
            load_generation_context(db, scenario, attempt_id=lease.attempt_id, lease_token=lease.lease_token)


def test_expansion_final_hits_never_exceed_snapshot_topk(db_factory, monkeypatch):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        lease = acquire_generation_lease(
            db, scenario, db.get(User, 2), **request_for(scenario, retrieval_top_k=1)
        )
        config = load_generation_context(db, scenario, attempt_id=lease.attempt_id, lease_token=lease.lease_token)
        calls = {"count": 0}

        def fake_retrieve(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return [{"id": "low", "match_score": 10}]
            return [{"id": f"expanded-{i}", "match_score": 90 - i} for i in range(8)]

        monkeypatch.setattr("app.services.retrieval_expansion.retrieve_for_checklist_item", fake_retrieve)
        hits, meta = retrieve_item_with_expansion(
            db,
            item_code="LAB-001",
            dimension="labor",
            title="劳动",
            description="低命中",
            match_threshold=config.match_threshold,
            expansion_context=config.generation_input["expansion_context"],
            top_k=config.retrieval_top_k,
            generation_config=config,
        )
        assert meta["expanded"] is True
        assert len(hits) == 1


@pytest.mark.parametrize("top_k", [0, 10])
def test_retrieval_topk_zero_and_max_are_deterministic(db_factory, monkeypatch, top_k):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        lease = acquire_generation_lease(
            db, scenario, db.get(User, 2), **request_for(scenario, retrieval_top_k=top_k)
        )
        config = load_generation_context(db, scenario, attempt_id=lease.attempt_id, lease_token=lease.lease_token)
        monkeypatch.setattr(
            "app.services.retrieval_expansion.retrieve_for_checklist_item",
            lambda *args, **kwargs: [
                {"id": f"hit-{i}", "match_score": 10} for i in range(kwargs["top_k"])
            ],
        )
        hits, _ = retrieve_item_with_expansion(
            db,
            item_code="LAB-001",
            dimension="labor",
            title="劳动",
            description="低命中",
            match_threshold=config.match_threshold,
            expansion_context=config.generation_input["expansion_context"],
            top_k=top_k,
            generation_config=config,
        )
        assert len(hits) <= top_k
        if top_k == 0:
            assert hits == []


def test_self_consistent_but_unbound_config_is_rejected(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        lease = acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))
        config = load_generation_context(db, scenario, attempt_id=lease.attempt_id, lease_token=lease.lease_token)
        forged = replace(config, lease_token="a" * 32)
        with pytest.raises(GenerationGuardError, match="token"):
            require_generation_config(db, forged)
        wrong_scenario = replace(config, scenario_id=scenario.id + 999)
        with pytest.raises(GenerationGuardError):
            require_generation_config(db, wrong_scenario)


def test_unexpired_lease_cannot_be_taken_over(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        args = request_for(scenario)
        first = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        second = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        assert first.acquired is True
        assert second.acquired is False
        assert second.attempt_id == first.attempt_id


def test_expired_lease_allows_only_one_sqlite_takeover(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        first = acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))
        attempt = db.get(ScenarioGenerationAttempt, first.attempt_id)
        attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()

    def takeover(_: int):
        with db_factory() as db:
            scenario = db.get(InvestigationScenario, scenario_id)
            return acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(takeover, [1, 2]))
    assert sum(lease.acquired for lease in leases) == 1
    assert len({lease.attempt_id for lease in leases}) == 1
    with db_factory() as db:
        assert db.get(ScenarioGenerationAttempt, first.attempt_id).status == "superseded"
        assert db.get(InvestigationScenario, scenario_id).status == "scope_generating"


def test_old_attempt_after_takeover_cannot_fail_new_attempt(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        args = request_for(scenario)
        first = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        db.get(ScenarioGenerationAttempt, first.attempt_id).lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()
        takeover = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        assert takeover.acquired and takeover.attempt_id != first.attempt_id
        assert mark_generation_failed(
            db, scenario_id, first.attempt_id, first.lease_owner, first.lease_token, RuntimeError("late")
        ) is False
        db.refresh(scenario)
        assert scenario.active_generation_attempt_id == takeover.attempt_id
        assert scenario.status == "scope_generating"


def test_orphaned_attempt_after_snapshot_commit_is_recoverable(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        args = request_for(scenario)
        first = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        db.get(ScenarioGenerationAttempt, first.attempt_id).status = "failed"
        db.commit()
        recovery = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        assert recovery.acquired is True
        assert recovery.outcome == "orphan_recovery"
        assert recovery.attempt_id != first.attempt_id


def test_takeover_attempt_can_succeed_and_old_attempt_cannot_submit(db_factory, monkeypatch):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        args = request_for(scenario, compliance_dimensions=["labor"])
        first = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        db.get(ScenarioGenerationAttempt, first.attempt_id).lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()
        takeover = acquire_generation_lease(db, scenario, db.get(User, 2), **args)
        with pytest.raises(GenerationGuardError, match="失效|过期"):
            run_generate_investigation_pack(
                db,
                db.get(User, 2),
                scenario,
                attempt_id=first.attempt_id,
                lease_token=first.lease_token,
            )
        monkeypatch.setattr("app.services.scenario_pipeline.upsert_scenario_subscription", lambda *a, **k: None)
        monkeypatch.setattr("app.services.scenario_pipeline._safe_audit", lambda **kwargs: None)
        result = run_generate_investigation_pack(
            db,
            db.get(User, 2),
            scenario,
            attempt_id=takeover.attempt_id,
            lease_token=takeover.lease_token,
        )
        assert result.status == "pending_legal_review"
        assert db.get(ScenarioGenerationAttempt, takeover.attempt_id).status == "succeeded"
        assert db.get(ScenarioGenerationAttempt, first.attempt_id).status == "superseded"


def test_proposal_tampering_with_old_hash_is_rejected(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        scope = dict(scenario.scenario_scope)
        proposed = dict(scope["proposed"])
        proposed["country"] = "mexico"
        scope["proposed"] = proposed
        scenario.scenario_scope = scope
        db.commit()
        with pytest.raises(GenerationConflictError, match="提议内容"):
            acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))


def test_audit_metadata_does_not_change_semantic_hash(db_factory):
    scenario_id = create_pending(db_factory)
    with db_factory() as db:
        scenario = db.get(InvestigationScenario, scenario_id)
        acquire_generation_lease(db, scenario, db.get(User, 2), **request_for(scenario))
        snapshot = dict(scenario.scenario_scope["snapshot"])
        original_snapshot_hash = snapshot_hash(snapshot)
        original_config_hash = snapshot["generation_config_hash"]
        snapshot["audit_metadata"] = {
            "confirmed_by": 999,
            "confirmed_by_name": "changed display name",
            "confirmed_at": "2099-01-01T00:00:00Z",
            "labels": {"pack": "changed label"},
        }
        assert snapshot_hash(snapshot) == original_snapshot_hash
        assert snapshot["generation_config_hash"] == original_config_hash


def _asgi_client(factory, user_id: int = 2):
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


def test_real_asgi_routes_fail_closed_and_demo_is_isolated(db_factory):
    formal_id = create_pending(db_factory)
    with db_factory() as db:
        formal = db.get(InvestigationScenario, formal_id)
        formal.checklist.payload["review"] = {"status": "in_progress", "items": [{"code": "FAKE"}]}
        flag_modified(formal.checklist, "payload")
        demo = create_scenario_materials_only(db, db.get(User, 1), payload(), demo=True)
        demo_id = demo.id
        db.commit()
    client = _asgi_client(db_factory)
    assert client.post(f"/api/v1/scenarios/{formal_id}/retrieve").status_code == 409
    assert client.post(f"/api/v1/scenarios/{formal_id}/review/init").status_code == 409
    formal_rows = client.get("/api/v1/scenarios").json()
    assert {row["id"] for row in formal_rows} == {formal_id}
    demo_rows = client.get("/api/v1/demo/scenarios").json()
    assert {row["id"] for row in demo_rows} == {demo_id}
    assert client.post(f"/api/v1/scenarios/{demo_id}/review/init").status_code == 404
    assert client.post(
        f"/api/v1/scenarios/{demo_id}/review/finalize",
        params={"expected_revision": 0},
    ).status_code == 404
    assert client.get(f"/api/v1/scenarios/{demo_id}/export/audit-bundle").status_code == 404
    assert client.get(f"/api/v1/scenarios/{demo_id}/export/docx").status_code == 404
    assert client.get(f"/api/v1/scenarios/{demo_id}/export/pdf").status_code == 404
    assert client.get(f"/api/v1/projects/{demo_id}/hub").status_code == 404
    with db_factory() as db:
        demo = db.get(InvestigationScenario, demo_id)
        with pytest.raises(ValueError, match="演示项目"):
            build_audit_bundle(demo)


def test_frontend_frozen_and_deprecated_endpoint_behavior_is_static():
    root = pytest.importorskip("pathlib").Path(__file__).parents[2] / "frontend/src"
    gate = (root / "components/LegalMaterialGatePanel.vue").read_text()
    brief = (root / "views/BriefView.vue").read_text()
    dashboard = (root / "views/DashboardView.vue").read_text()
    client = (root / "api/client.ts").read_text()
    assert "!!props.scenario.scenario_scope?.snapshot" in gate
    assert "if (!frozen) try" in gate
    assert "retryInvestigationPack" in gate
    assert "await generateBrief" not in brief
    assert "createFullSample" not in dashboard
    assert "/scenarios/demo/sample" not in client
    assert "retrieveLegalSources" not in client
