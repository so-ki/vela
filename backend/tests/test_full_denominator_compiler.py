from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.capability_packs.registry import get_capability_pack_registry
from app.core.database import Base
from app.models.mechanism import FactRecord
from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User
from app.schemas.mechanism import ClaimCompileRequest
from app.services.generation_guard import stable_hash
from app.services.mechanism_service import (
    MechanismValidationError,
    compilation_research_items,
    compile_claims,
)
from app.services.versioned import registry as versioned_registry


def _scope_snapshot(dimensions: list[str]) -> dict:
    pack = get_capability_pack_registry().list_active()[0]
    manifest = pack.manifest
    body = {
        "capability_pack_id": manifest.pack_id,
        "capability_pack_version": manifest.version,
        "capability_pack_hash": manifest.semantic_hash,
        "rules_artifact_id": manifest.rules_artifact.artifact_id,
        "rules_artifact_version": manifest.rules_artifact.version,
        "rules_artifact_hash": manifest.rules_artifact.content_hash,
        "corpus_artifact_id": manifest.corpus_artifact.artifact_id,
        "corpus_artifact_version": manifest.corpus_artifact.version,
        "corpus_artifact_hash": manifest.corpus_artifact.content_hash,
        "issue_modules": list(manifest.issue_modules),
        "compliance_dimensions": dimensions,
    }
    return {**body, "snapshot_hash": stable_hash(body)}


@pytest.fixture()
def compiler_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        versioned_registry, "CURRENT_COMPILER_WRITE_VERSION", "0.3"
    )
    engine = create_engine(f"sqlite:///{tmp_path / 'compiler-03.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        business = User(
            id=1,
            email="business@example.invalid",
            full_name="Business",
            role="business",
            disclaimer_accepted=True,
        )
        legal = User(
            id=2,
            email="legal@example.invalid",
            full_name="Legal",
            role="legal",
            disclaimer_accepted=True,
        )
        snapshot = _scope_snapshot(["environment"])
        scenario = InvestigationScenario(
            id=1,
            user_id=business.id,
            project_name="Compiler 0.3 test",
            country="BR",
            state="sao_paulo",
            city="campinas",
            industry="new_energy_manufacturing",
            action_type="greenfield_plant",
            description="Formal test scenario",
            compliance_dimensions=["environment"],
            scenario_scope={"snapshot": snapshot},
            scope_snapshot_hash=snapshot["snapshot_hash"],
            status="generated",
            is_demo=False,
        )
        scenario.checklist = ComplianceChecklist(
            scenario_id=1,
            title="Screened checklist",
            version="v0.1",
            total_items=1,
            payload={
                "scenario_scope_snapshot": snapshot,
                "sections_with_legal": [
                    {
                        "dimension_id": "environment",
                        "items": [
                            {
                                "code": "ENV-001",
                                "title": "Environmental licensing",
                                "priority": "high",
                                "relevance_score": 7,
                                "rationale": "screened by formal rules",
                                "legal_hits": [
                                    {
                                        "id": "law-1",
                                        "grounded": True,
                                        "citation_status": "grounded",
                                        "review_status": "expert_verified",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )
        db.add_all([business, legal, scenario])
        db.commit()
        yield db, scenario, business, legal


def test_compiler_03_always_materializes_all_30_pack_items_without_placeholder_claims(
    compiler_db,
) -> None:
    db, scenario, _business, legal = compiler_db
    compilation, claims = compile_claims(
        db,
        scenario=scenario,
        request=ClaimCompileRequest(),
        user=legal,
    )
    research_items = compilation_research_items(db, compilation.id)

    assert compilation.compiler_version == "0.3"
    assert compilation.denominator_count == 30
    assert claims == []
    assert len(research_items) == 30
    assert len({item.checklist_code for item in research_items}) == 30
    assert sum(item.scope_status == "in_scope" for item in research_items) == 4
    assert sum(
        item.scope_status == "out_of_scope_by_scope" for item in research_items
    ) == 26
    assert all(
        item.disposition is None
        for item in research_items
        if item.scope_status == "out_of_scope_by_scope"
    )
    assert all(
        item.disposition == "uncovered"
        for item in research_items
        if item.scope_status == "in_scope"
    )


def test_compiler_03_creates_claim_only_from_real_legal_draft(compiler_db) -> None:
    db, scenario, business, legal = compiler_db
    fact = FactRecord(
        id="fact-confirmed",
        scenario_id=scenario.id,
        subject="project",
        attribute="site",
        value="Campinas",
        assertion_polarity="affirmative",
        fact_time="2026-07-19",
        block_id="upload:1",
        fact_pack_version="facts-v1",
        status="business_confirmed",
        confirmation_note="confirmed by business",
        business_confirmed_by=business.id,
        created_by=business.id,
    )
    db.add(fact)
    db.flush()
    compilation, claims = compile_claims(
        db,
        scenario=scenario,
        request=ClaimCompileRequest(
            drafts=[
                {
                    "checklist_code": "ENV-001",
                    "statement": "The licensing path remains subject to legal review.",
                    "fact_refs": [fact.id],
                    "evidence_refs": ["ENV-001:law-1"],
                }
            ]
        ),
        user=legal,
    )
    research_items = compilation_research_items(db, compilation.id)

    assert len(claims) == 1
    assert claims[0].checklist_code == "ENV-001"
    assert claims[0].statement.startswith("The licensing path")
    assert all("\u5f85\u6838\u9a8c\u4e8b\u9879" not in claim.statement for claim in claims)
    linked = next(item for item in research_items if item.checklist_code == "ENV-001")
    assert linked.linked_claim_id == claims[0].id
    assert linked.research_status == "claim_pending"


def test_not_applicable_requires_confirmed_negative_business_fact_and_legal_note(
    compiler_db,
) -> None:
    db, scenario, business, legal = compiler_db
    fact = FactRecord(
        id="fact-no-hazardous-storage",
        scenario_id=scenario.id,
        subject="project",
        attribute="hazardous_storage",
        value="No hazardous materials will be stored",
        assertion_polarity="negative",
        fact_time="2026-07-19",
        block_id="upload:2",
        fact_pack_version="facts-v1",
        status="business_confirmed",
        confirmation_note="business confirmed the negative fact",
        business_confirmed_by=business.id,
        created_by=business.id,
    )
    db.add(fact)
    db.flush()
    request = ClaimCompileRequest(
        research_decisions=[
            {
                "checklist_code": "ENV-002",
                "disposition": "not_applicable",
                "negative_fact_refs": [fact.id],
                "confirmation_note": "Legal confirmed this negative fact makes the item inapplicable.",
            }
        ]
    )
    compilation, claims = compile_claims(
        db, scenario=scenario, request=request, user=legal
    )
    decided = next(
        item
        for item in compilation_research_items(db, compilation.id)
        if item.checklist_code == "ENV-002"
    )
    assert claims == []
    assert decided.disposition == "not_applicable"
    assert decided.negative_fact_refs == [fact.id]
    assert decided.legal_confirmed_by == legal.id

    fact.assertion_polarity = "affirmative"
    db.flush()
    with pytest.raises(MechanismValidationError, match="assertion_polarity=negative"):
        compile_claims(db, scenario=scenario, request=request, user=legal)


def test_compiler_03_input_hash_changes_when_formal_fact_changes(compiler_db) -> None:
    db, scenario, business, legal = compiler_db
    first, _ = compile_claims(
        db, scenario=scenario, request=ClaimCompileRequest(), user=legal
    )
    db.add(
        FactRecord(
            id="fact-key-capacity",
            scenario_id=scenario.id,
            subject="project",
            attribute="capacity",
            value="1000 units",
            assertion_polarity="affirmative",
            fact_time="2026-07-19",
            block_id="upload:3",
            fact_pack_version="facts-v1",
            status="business_confirmed",
            confirmation_note="confirmed by business",
            business_confirmed_by=business.id,
            created_by=business.id,
        )
    )
    db.flush()
    second, _ = compile_claims(
        db, scenario=scenario, request=ClaimCompileRequest(), user=legal
    )
    assert first.input_hash != second.input_hash
    assert first.output_hash == second.output_hash
