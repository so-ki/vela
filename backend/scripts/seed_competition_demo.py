"""Seed the isolated Aurora competition database through the formal service path."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

COMPETITION_DATABASE_NAME = "vela_competition.db"
AURORA_PROJECT_NAME = "Aurora 储能系统集成工厂"
FORBIDDEN_COMPETITION_TERMS = ("BYD", "byd", "Campinas", "campinas", "坎皮纳斯")
DEMO_PASSWORD = "Demo1234!"

_DROP = object()


def validated_competition_database_path(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if path.name != COMPETITION_DATABASE_NAME:
        raise RuntimeError(
            f"competition reset is restricted to a file named {COMPETITION_DATABASE_NAME}"
        )
    return path


def reset_competition_database(raw_path: str | Path) -> None:
    """Delete only the explicitly named competition SQLite database and sidecars."""
    path = validated_competition_database_path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        candidate.unlink(missing_ok=True)


def _contains_forbidden_term(value: str) -> bool:
    return any(term in value for term in FORBIDDEN_COMPETITION_TERMS)


def _clean_competition_value(value: Any) -> Any:
    if isinstance(value, str):
        return _DROP if _contains_forbidden_term(value) else value
    if isinstance(value, list):
        cleaned = [_clean_competition_value(item) for item in value]
        return [item for item in cleaned if item is not _DROP]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            next_value = _clean_competition_value(item)
            if next_value is not _DROP:
                cleaned[key] = next_value
        return cleaned
    return value


def _add_safe_environment_source(payload: dict[str, Any]) -> str:
    source = {
        "id": "alesp-lei-997-1976-controle-poluicao",
        "urn": "urn:lex:br;sao.paulo:estadual:lei:1976-05-31;997",
        "url": (
            "https://www.al.sp.gov.br/repositorio/legislacao/lei/1976/"
            "compilacao-lei-997-31.05.1976.html"
        ),
        "title_zh": "圣保罗州第 997/1976 号法 — 环境污染防治与许可",
        "title_pt": "Lei estadual nº 997/1976 — controle da poluição do meio ambiente",
        "published_at": "1976-05-31",
        "grounded": True,
        "citation_status": "grounded",
        "review_status": "provisional",
        "requires_review": True,
    }
    for section in payload.get("sections_with_legal") or []:
        for item in section.get("items") or []:
            if item.get("code") == "ENV-001":
                existing = [
                    hit
                    for hit in item.get("legal_hits") or []
                    if hit.get("id") != source["id"]
                ]
                item["legal_hits"] = [source, *existing]
                return f"ENV-001:{source['id']}"
    raise RuntimeError("formal Aurora pack did not produce ENV-001")


def _assert_clean_competition_database(db: Any) -> None:
    from sqlalchemy import JSON, String, Text, select

    from app.core.database import Base

    findings: list[str] = []
    for table in Base.metadata.sorted_tables:
        columns = [
            column
            for column in table.columns
            if isinstance(column.type, (String, Text, JSON))
        ]
        if not columns:
            continue
        for row in db.execute(select(*columns)):
            serialized = json.dumps(list(row), ensure_ascii=False, default=str)
            if _contains_forbidden_term(serialized):
                findings.append(table.name)
    if findings:
        raise RuntimeError(
            "competition database contains prohibited historical wording in: "
            + ", ".join(sorted(set(findings)))
        )


def _assert_bound_competition_database(db: Any) -> Path:
    if os.environ.get("VELA_APP_MODE", "").strip().lower() != "competition":
        raise RuntimeError("competition seed requires VELA_APP_MODE=competition")
    configured_path = validated_competition_database_path(
        os.environ.get("VELA_COMPETITION_DB_PATH", "")
    )
    bound_database = db.get_bind().url.database
    if not bound_database or Path(bound_database).resolve() != configured_path:
        raise RuntimeError("competition seed database binding does not match VELA_COMPETITION_DB_PATH")
    return configured_path


def seed_competition_demo(db: Any) -> int:
    from sqlalchemy.orm.attributes import flag_modified

    from app.capability_packs.registry import get_capability_pack_registry
    from app.core.roles import ROLE_BUSINESS, ROLE_LEGAL
    from app.core.security import get_password_hash
    from app.models.mechanism import ClaimRecord, ResearchItem
    from app.models.scenario import InvestigationScenario
    from app.models.user import User
    from app.schemas.mechanism import (
        ClaimCompileRequest,
        FactRecordCreateRequest,
        MaterialLedgerUpsertRequest,
    )
    from app.schemas.scenario import BusinessSubmitRequest
    from app.services.audit import write_audit_log
    from app.services.mechanism_service import (
        compilation_research_items,
        confirm_claim,
        confirm_fact_record,
        compile_claims,
        create_coverage_proof,
        create_fact_record,
        upsert_material_ledger_entry,
    )
    from app.services.scenario_pipeline import run_confirm_scope_and_generate
    from app.services.scenario_service import create_scenario_materials_only

    _assert_bound_competition_database(db)
    if db.query(User).count() or db.query(InvestigationScenario).count():
        raise RuntimeError("competition seed requires a freshly migrated empty database")

    now = datetime.now(timezone.utc)
    legal = User(
        email="legal@demo.vela",
        full_name="演示法务",
        organization="Aurora 虚构测试企业 · 法务部",
        hashed_password=get_password_hash(DEMO_PASSWORD),
        role=ROLE_LEGAL,
        auth_provider="local",
        is_active=True,
        disclaimer_accepted=True,
        disclaimer_accepted_at=now,
    )
    business = User(
        email="biz@demo.vela",
        full_name="演示业务",
        organization="Aurora 虚构测试企业 · 投资部",
        hashed_password=get_password_hash(DEMO_PASSWORD),
        role=ROLE_BUSINESS,
        auth_provider="local",
        is_active=True,
        disclaimer_accepted=True,
        disclaimer_accepted_at=now,
    )
    db.add_all([legal, business])
    db.commit()
    db.refresh(legal)
    db.refresh(business)

    request = BusinessSubmitRequest(
        project_name=AURORA_PROJECT_NAME,
        country="BR",
        state="sao_paulo",
        city="",
        industry="new_energy_manufacturing",
        action_type="greenfield_plant",
        scope_acknowledged=True,
        scope_notice_version="scope-notice-v2",
        investment_structure="中国投资主体拟设立全资项目公司",
        investment_destination="巴西圣保罗州，市级选址尚未确定",
        project_content_scale="储能系统集成工厂；虚构测试案例参数",
        funding_source="中国投资主体自有资金与拟议项目融资",
        description=(
            "Aurora 为虚构测试企业。本案例用于演示中国投资主体在巴西圣保罗州"
            "投资新能源制造项目并绿地设厂的六维初步协查过程。"
        ),
        known_risks="环境许可为当前研究最深入维度；市级规则未纳入本次演示范围。",
        capacity_notes="储能系统集成产能为演示假设，待项目材料进一步确认。",
        facility_notes="拟新建集成、测试与仓储设施，具体选址与工艺参数尚未确定。",
        remarks="虚构测试案例；不构成正式法律意见。",
    )
    scenario = create_scenario_materials_only(db, business, request)
    proposal_hash = str((scenario.scenario_scope or {}).get("proposed", {}).get("proposal_hash") or "")
    dimensions = list(
        get_capability_pack_registry().list_active()[0].manifest.issue_modules
    )
    scenario = run_confirm_scope_and_generate(
        db,
        legal,
        scenario,
        dimensions,
        expected_proposal_hash=proposal_hash,
        match_threshold=70,
        retrieval_top_k=3,
        include_playbook_suggestions=False,
        selected_issue_codes=[],
        fit_decision="accept_warning",
    )

    checklist_payload = _clean_competition_value(copy.deepcopy(scenario.checklist.payload))
    if checklist_payload is _DROP or not isinstance(checklist_payload, dict):
        raise RuntimeError("competition checklist sanitization failed")
    evidence_ref = _add_safe_environment_source(checklist_payload)
    scenario.checklist.payload = checklist_payload
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    upsert_material_ledger_entry(
        db,
        scenario=scenario,
        block_id="aurora-case-brief:1",
        request=MaterialLedgerUpsertRequest(
            source_document="aurora_competition_case.txt",
            state="verified",
            note="比赛专用虚构测试材料",
            confirmation_note="演示法务已核对材料来源与虚构案例边界。",
        ),
        user=legal,
        is_legal=True,
    )

    fact_specs = [
        ("investor", "origin", "中国投资主体"),
        ("project", "destination_country", "巴西"),
        ("project", "destination_state", "圣保罗州"),
        ("project", "industry", "新能源制造"),
        ("project", "action", "绿地设厂"),
        ("project", "research_focus", "环境许可为当前研究最深入维度"),
    ]
    facts = []
    for subject, attribute, value in fact_specs:
        fact = create_fact_record(
            db,
            scenario=scenario,
            request=FactRecordCreateRequest(
                subject=subject,
                attribute=attribute,
                value=value,
                fact_time="2026-07-19",
                block_id="aurora-case-brief:1",
                fact_pack_version="aurora-competition-facts-v1",
                source_document="aurora_competition_case.txt",
                assertion_polarity="affirmative",
            ),
            user=business,
        )
        facts.append(
            confirm_fact_record(
                db,
                fact=fact,
                scenario=scenario,
                confirmation_note="演示业务确认该项为本次虚构测试案例输入。",
                user=business,
            )
        )

    compilation, claims = compile_claims(
        db,
        scenario=scenario,
        request=ClaimCompileRequest(
            drafts=[
                {
                    "checklist_code": "ENV-001",
                    "statement": (
                        "基于当前已登记事实与圣保罗州官方法源，本项目应在选址及工艺参数"
                        "确定后核定适用的环境许可路径；当前结论不替代当地律师复核。"
                    ),
                    "fact_refs": [facts[1].id, facts[2].id, facts[5].id],
                    "evidence_refs": [evidence_ref],
                }
            ]
        ),
        user=legal,
    )
    if len(claims) != 1 or claims[0].status != "awaiting_human_confirmation":
        raise RuntimeError("Aurora environment Claim did not compile from formal facts and source")
    confirm_claim(
        db,
        claim=claims[0],
        decision="confirmed",
        confirmation_note=(
            "比赛演示法务确认该限定表述；不代表律师认证、客户 UAT 或正式法律意见。"
        ),
        user=legal,
    )
    proof = create_coverage_proof(
        db,
        scenario=scenario,
        compilation=compilation,
        claims=claims,
        denominator_ref="capability-pack:brazil_new_energy_greenfield:fixed-30",
        user=legal,
    )
    write_audit_log(
        db,
        user=legal,
        action="competition.aurora_seed",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"scenario={scenario.id} Aurora competition seed; denominator=30; "
            "CoverageProof=0.2; release=blocked_external"
        ),
        commit=False,
    )
    db.commit()

    research_items = compilation_research_items(db, compilation.id)
    if db.query(User).count() != 2 or db.query(InvestigationScenario).count() != 1:
        raise RuntimeError("competition database must contain exactly two users and one scenario")
    if db.query(ClaimRecord).count() != 1 or db.query(ResearchItem).count() != 30:
        raise RuntimeError("competition mechanism seed must contain one Claim and 30 ResearchItems")
    if len(research_items) != 30 or proof.proof.get("schema_version") != "0.2":
        raise RuntimeError("competition denominator or CoverageProof version is invalid")
    _assert_clean_competition_database(db)
    return scenario.id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reset-database",
        action="store_true",
        help="remove only VELA_COMPETITION_DB_PATH and its SQLite sidecars",
    )
    args = parser.parse_args()
    raw_path = os.environ.get("VELA_COMPETITION_DB_PATH", "")
    if not raw_path:
        raise RuntimeError("VELA_COMPETITION_DB_PATH is required")
    if args.reset_database:
        reset_competition_database(raw_path)
        print(f"RESET_COMPETITION_DATABASE={validated_competition_database_path(raw_path)}")
        return 0

    from app.core.database import SessionLocal

    with SessionLocal() as db:
        scenario_id = seed_competition_demo(db)
    print(f"AURORA_SCENARIO_ID={scenario_id}")
    print(f"AURORA_PROJECT_NAME={AURORA_PROJECT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
