"""Executable "delete Brazil" boundary for the platform mechanism layer.

This test deliberately copies only the synthetic fixture pack into an isolated
registry.  Reading either production Brazil artifact is a test failure, so a
green run proves the checklist/retrieval/brief path is pack-driven rather than
silently falling back to the first production jurisdiction.
"""

from __future__ import annotations

import builtins
import os
import shutil
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.capability_packs.registry as registry_module
import app.services.legal_rag as legal_rag
import app.services.scenario_scope_service as scope_service
from app.capability_packs.registry import CAPABILITY_PACKS_ROOT, CapabilityPackRegistry
from app.core.database import Base
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.scenario import BusinessSubmitRequest
from app.services.brief_generator import generate_brief
from app.services.generation_guard import load_generation_context
from app.services.legal_rag import retrieve_for_checklist
from app.services.rule_engine import ScenarioInput, generate_checklist


FIXTURE_PACK_ID = "test_fixture_pack"
FORMAL_PACK_DIR = CAPABILITY_PACKS_ROOT / "brazil_new_energy_greenfield"
FORBIDDEN_PRODUCTION_PATHS = {
    (FORMAL_PACK_DIR / "manifest.json").resolve(),
    (CAPABILITY_PACKS_ROOT.parent / "rules" / "brazil_new_energy.json").resolve(),
    (CAPABILITY_PACKS_ROOT.parent / "data" / "brazil_legal_corpus.json").resolve(),
}


def _isolated_fixture_registry(tmp_path: Path) -> CapabilityPackRegistry:
    root = tmp_path / "capability_packs"
    destination = root / "fixtures" / FIXTURE_PACK_ID
    destination.parent.mkdir(parents=True)
    shutil.copytree(
        CAPABILITY_PACKS_ROOT / "fixtures" / FIXTURE_PACK_ID,
        destination,
    )
    return CapabilityPackRegistry(
        root=root,
        app_env="test",
        include_test_fixtures=True,
    )


def _db_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'country-independent.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _reject_production_artifact_reads(monkeypatch) -> None:
    original_read_bytes = Path.read_bytes
    original_path_open = Path.open
    original_open = builtins.open

    def assert_not_production_artifact(path: str | bytes | os.PathLike) -> None:
        assert Path(os.fsdecode(path)).resolve() not in FORBIDDEN_PRODUCTION_PATHS, (
            "country-independent fixture flow must not read a formal Brazil artifact"
        )

    def guarded_read_bytes(path: Path) -> bytes:
        assert_not_production_artifact(path)
        return original_read_bytes(path)

    def guarded_path_open(path: Path, *args, **kwargs):
        assert_not_production_artifact(path)
        return original_path_open(path, *args, **kwargs)

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            assert_not_production_artifact(file)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(builtins, "open", guarded_open)


def test_synthetic_pack_runs_checklist_retrieval_refusal_and_brief_without_brazil(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry = _isolated_fixture_registry(tmp_path)
    factory = _db_factory(tmp_path)
    _reject_production_artifact_reads(monkeypatch)

    # All frozen-snapshot reloads must resolve against the isolated registry.
    monkeypatch.setattr(registry_module, "get_capability_pack_registry", lambda: registry)
    monkeypatch.setattr(scope_service, "get_capability_pack_registry", lambda: registry)
    monkeypatch.setattr(legal_rag, "_chroma_available", False)

    with factory() as db:
        business = User(
            id=1,
            email="fixture-business@example.invalid",
            full_name="fixture business",
            role="business",
        )
        legal = User(
            id=2,
            email="fixture-legal@example.invalid",
            full_name="fixture legal",
            role="legal",
        )
        db.add_all([business, legal])
        db.commit()

        request = BusinessSubmitRequest(
            project_name=(
                "fixture-country-token fixture-state-token "
                "fixture-industry-token fixture-action-token"
            ),
            country="ZZ-TEST",
            state="ZZ-STATE",
            city="fixture_city",
            industry="fixture_industry",
            action_type="fixture_action",
            description=(
                "fixture-country-token fixture-state-token fixture-industry-token "
                "fixture-action-token synthetic material"
            ),
            scope_acknowledged=True,
        )
        scope = scope_service.build_proposed_scenario_scope(
            request,
            business,
            registry=registry,
        )
        proposed = scope["proposed"]
        scenario = InvestigationScenario(
            user_id=business.id,
            project_name=request.project_name,
            rules_pack_id=proposed["rules_artifact_id"],
            scenario_scope=scope,
            is_demo=False,
            country=proposed["country"],
            state=proposed["state"],
            city=proposed["city"],
            industry=proposed["industry"],
            action_type=proposed["action_type"],
            investment_structure="synthetic",
            description=request.description,
            compliance_dimensions=[],
            status="pending_scope",
        )
        db.add(scenario)
        db.commit()

        lease = scope_service.acquire_generation_lease(
            db,
            scenario,
            legal,
            expected_proposal_hash=proposed["proposal_hash"],
            compliance_dimensions=["fixture_supported", "fixture_missing"],
            selected_issue_codes=[],
            match_threshold=70,
            retrieval_top_k=2,
            fit_decision="fit",
            polish=False,
            include_playbook_suggestions=False,
        )
        assert lease.acquired is True
        config = load_generation_context(
            db,
            scenario,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
        )

        checklist = generate_checklist(
            db,
            ScenarioInput(
                project_name=scenario.project_name,
                country=config.country,
                state=config.state,
                city=config.city,
                industry=config.industry,
                action_type=config.action_type,
                investment_structure="synthetic",
                description=scenario.description,
                compliance_dimensions=list(config.compliance_dimensions),
                rules_pack_id=config.rules_artifact_id,
            ),
            config.rules_artifact_id,
            generation_config=config,
        )
        assert checklist["total_items"] == 2
        assert {item["code"] for section in checklist["sections"] for item in section["items"]} == {
            "FIX-SUP-001",
            "FIX-MISS-001",
        }

        retrieval = retrieve_for_checklist(
            db,
            checklist["sections"],
            top_k=config.retrieval_top_k,
            match_threshold=config.match_threshold,
            expansion_context=config.generation_input["expansion_context"],
            generation_config=config,
        )
        repeated = retrieve_for_checklist(
            db,
            checklist["sections"],
            top_k=config.retrieval_top_k,
            match_threshold=config.match_threshold,
            expansion_context=config.generation_input["expansion_context"],
            generation_config=config,
        )
        assert retrieval == repeated
        assert retrieval["total_hits"] == 1
        assert retrieval["zero_hit_items"] == ["FIX-MISS-001"]
        assert "fixture-official" in retrieval["disclaimer"]

        brief = generate_brief(
            db,
            scenario,
            checklist,
            sections_with_legal=retrieval["sections"],
            threshold=config.match_threshold,
            polish=False,
            generation_config=config,
        )
        by_code = {
            item["code"]: item
            for section in brief["sections"]
            for item in section["items"]
        }
        assert brief["status"] == "partial"
        assert brief["passed_count"] == 1
        assert brief["blocked_count"] == 1
        assert by_code["FIX-SUP-001"]["gate_status"] == "passed"
        assert by_code["FIX-MISS-001"]["gate_status"] == "blocked"
        assert by_code["FIX-MISS-001"]["block_reason"] == "未检索到相关法条片段"
        assert brief["capability_pack"]["pack_id"] == FIXTURE_PACK_ID
        assert "非真实" in brief["disclaimer"]
