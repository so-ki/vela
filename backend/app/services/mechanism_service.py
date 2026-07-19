from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.mechanism import (
    ClaimCompilation,
    ClaimRecord,
    CoverageProof,
    CoverageTask,
    FactRecord,
    MaterialLedgerEntry,
    ResearchItem,
)
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.mechanism import (
    ClaimCompileRequest,
    CoverageTaskCreateRequest,
    FactRecordCreateRequest,
    MaterialLedgerUpsertRequest,
    ResearchItemDecisionRequest,
)
from app.services.generation_guard import stable_hash
from app.services.versioned import registry as versioned_registry


MATERIAL_STATES = {
    "missing",
    "received",
    "unreadable",
    "ambiguous",
    "verified",
    "not_applicable",
}
HUMAN_CONFIRMED_MATERIAL_STATES = {"verified", "not_applicable"}
# Compat read-only alias for legacy callers. It must NOT be used to persist
# a database identity: compile_claims() writes writer.version, the single
# source of truth from the versioned registry (C3-A.1).
COMPILER_VERSION = versioned_registry.CURRENT_COMPILER_WRITE_VERSION


class MechanismConflict(ValueError):
    pass


class MechanismValidationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_material_ledger_entry(
    db: Session,
    *,
    scenario: InvestigationScenario,
    block_id: str,
    request: MaterialLedgerUpsertRequest,
    user: User,
    is_legal: bool,
) -> MaterialLedgerEntry:
    block_id = block_id.strip()
    if not block_id:
        raise MechanismValidationError("block_id 不得为空")
    if request.state in HUMAN_CONFIRMED_MATERIAL_STATES:
        if not is_legal:
            raise MechanismValidationError("verified/not_applicable 必须由法务人工确认")
        if not (request.confirmation_note or "").strip():
            raise MechanismValidationError("人工确认状态必须填写 confirmation_note")

    now = _now()
    entry = (
        db.query(MaterialLedgerEntry)
        .filter(
            MaterialLedgerEntry.scenario_id == scenario.id,
            MaterialLedgerEntry.block_id == block_id,
        )
        .first()
    )
    event = {
        "state": request.state,
        "at": now.isoformat(),
        "by": user.id,
        "note": request.note,
        "confirmation_note": request.confirmation_note,
    }
    if entry is None:
        if request.expected_revision not in (None, 0):
            raise MechanismConflict("材料账本版本冲突，请刷新后重试")
        entry = MaterialLedgerEntry(
            id=str(uuid4()),
            scenario_id=scenario.id,
            block_id=block_id,
            source_document=request.source_document.strip(),
            state=request.state,
            state_at=now,
            extraction_task_id=request.extraction_task_id,
            note=request.note,
            confirmation_note=(request.confirmation_note if request.state in HUMAN_CONFIRMED_MATERIAL_STATES else None),
            confirmed_by=(user.id if request.state in HUMAN_CONFIRMED_MATERIAL_STATES else None),
            confirmed_at=(now if request.state in HUMAN_CONFIRMED_MATERIAL_STATES else None),
            state_history=[event],
            revision=0,
            created_by=user.id,
        )
        db.add(entry)
        db.flush()
        return entry

    if entry.state in HUMAN_CONFIRMED_MATERIAL_STATES and not is_legal:
        raise MechanismValidationError("法务已确认的材料状态只能由法务更正")
    if request.expected_revision is None:
        raise MechanismConflict("更新材料账本必须提供 expected_revision")
    if request.expected_revision != entry.revision:
        raise MechanismConflict("材料账本版本冲突，请刷新后重试")
    history = list(entry.state_history or []) + [event]
    values = {
        "source_document": request.source_document.strip(),
        "state": request.state,
        "state_at": now,
        "extraction_task_id": request.extraction_task_id,
        "note": request.note,
        "confirmation_note": (
            request.confirmation_note if request.state in HUMAN_CONFIRMED_MATERIAL_STATES else None
        ),
        "confirmed_by": user.id if request.state in HUMAN_CONFIRMED_MATERIAL_STATES else None,
        "confirmed_at": now if request.state in HUMAN_CONFIRMED_MATERIAL_STATES else None,
        "state_history": history,
        "revision": entry.revision + 1,
        "updated_at": now,
    }
    result = db.execute(
        update(MaterialLedgerEntry)
        .where(MaterialLedgerEntry.id == entry.id, MaterialLedgerEntry.revision == entry.revision)
        .values(**values)
    )
    if result.rowcount != 1:
        raise MechanismConflict("材料账本版本冲突，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(MaterialLedgerEntry, entry.id)


def list_material_ledger_entries(db: Session, scenario_id: int) -> list[MaterialLedgerEntry]:
    return (
        db.query(MaterialLedgerEntry)
        .filter(MaterialLedgerEntry.scenario_id == scenario_id)
        .order_by(MaterialLedgerEntry.block_id.asc())
        .all()
    )


def create_coverage_task(
    db: Session,
    *,
    scenario: InvestigationScenario,
    request: CoverageTaskCreateRequest,
    user: User,
) -> CoverageTask:
    # A coverage task is a quantified assertion.  Sources without an official,
    # hash-pinned denominator must remain an unanswerable Claim instead.
    source = request.source.strip()
    denominator_ref = request.denominator_ref.strip()
    expected_snapshot_hash = stable_hash(
        {
            "source": source,
            "denominator_ref": denominator_ref,
            "denominator_items": list(request.denominator_items),
        }
    )
    if request.denominator_snapshot_hash != expected_snapshot_hash:
        raise MechanismValidationError(
            "denominator_snapshot_hash 必须是 source、denominator_ref 和 denominator_items 的稳定 SHA-256 哈希"
        )
    task = CoverageTask(
        id=str(uuid4()),
        scenario_id=scenario.id,
        source=source,
        state=request.state,
        denominator_ref=denominator_ref,
        denominator_snapshot_hash=request.denominator_snapshot_hash,
        denominator_items=list(request.denominator_items),
        covered_items=list(request.covered_items),
        note=request.note,
        created_by=user.id,
    )
    db.add(task)
    db.flush()
    return task


def list_coverage_tasks(db: Session, scenario_id: int) -> list[CoverageTask]:
    return (
        db.query(CoverageTask)
        .filter(CoverageTask.scenario_id == scenario_id)
        .order_by(CoverageTask.created_at.desc())
        .all()
    )


def _checklist_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Write-path view of the checklist denominator (current write version)."""

    return versioned_registry.current_compiler_writer().checklist_items(payload)


def create_fact_record(
    db: Session,
    *,
    scenario: InvestigationScenario,
    request: FactRecordCreateRequest,
    user: User,
) -> FactRecord:
    if scenario.user_id != user.id:
        raise MechanismValidationError("只有场景业务提交人可以登记事实")
    fact = FactRecord(
        id=str(uuid4()),
        scenario_id=scenario.id,
        subject=request.subject,
        attribute=request.attribute,
        value=request.value,
        fact_time=request.fact_time,
        block_id=request.block_id,
        fact_pack_version=request.fact_pack_version,
        source_document=request.source_document.strip() if request.source_document else None,
        assertion_polarity=request.assertion_polarity,
        status="submitted",
        created_by=user.id,
    )
    db.add(fact)
    db.flush()
    return fact


def list_fact_records(db: Session, scenario_id: int) -> list[FactRecord]:
    return (
        db.query(FactRecord)
        .filter(FactRecord.scenario_id == scenario_id)
        .order_by(FactRecord.created_at.asc(), FactRecord.id.asc())
        .all()
    )


def confirm_fact_record(
    db: Session,
    *,
    fact: FactRecord,
    scenario: InvestigationScenario,
    confirmation_note: str,
    user: User,
) -> FactRecord:
    if scenario.user_id != user.id or fact.created_by != user.id:
        raise MechanismValidationError("只有事实登记人可以确认业务事实")
    now = _now()
    result = db.execute(
        update(FactRecord)
        .where(FactRecord.id == fact.id, FactRecord.status == "submitted")
        .values(
            status="business_confirmed",
            confirmation_note=confirmation_note.strip(),
            business_confirmed_by=user.id,
            business_confirmed_at=now,
        )
    )
    if result.rowcount != 1:
        raise MechanismConflict("该事实已被确认，不能重复确认")
    db.flush()
    return db.get(FactRecord, fact.id)


# The compiler inventories (facts/evidence/checklist/brief) are hash-frozen in
# app/services/versioned/claim_compiler/; the write path always goes through
# the current write version via the versioned registry.


def build_compiler_input_snapshot(
    db: Session,
    *,
    scenario: InvestigationScenario,
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the current checklist/fact/evidence snapshot (current write version)."""

    return versioned_registry.current_compiler_writer().build_input_snapshot(
        db, scenario=scenario, drafts=drafts
    )




def build_compiler_claim_values(
    items: list[dict[str, Any]],
    *,
    drafts: list[dict[str, Any]],
    facts: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pure deterministic compiler output (current write version)."""

    return versioned_registry.current_compiler_writer().build_claim_values(
        items, drafts=drafts, facts=facts, evidence=evidence
    )


def compile_claims(
    db: Session,
    *,
    scenario: InvestigationScenario,
    request: ClaimCompileRequest,
    user: User,
) -> tuple[ClaimCompilation, list[ClaimRecord]]:
    payload = scenario.checklist.payload if scenario.checklist else {}
    writer = versioned_registry.current_compiler_writer()
    items = (
        writer.build_denominator(scenario=scenario)
        if writer.build_denominator is not None
        else writer.checklist_items(payload)
    )
    if not items:
        raise MechanismValidationError("场景没有可编译的 checklist 分母")
    item_by_code = {
        str(item.get("checklist_code") or item.get("code")): item for item in items
    }
    draft_by_code = {draft.checklist_code: draft for draft in request.drafts}
    unknown_codes = sorted(set(draft_by_code) - set(item_by_code))
    if unknown_codes:
        raise MechanismValidationError(
            f"Claim 草稿引用了不在当前清单中的 code: {', '.join(unknown_codes[:10])}"
        )
    out_of_scope_drafts = sorted(
        code
        for code in draft_by_code
        if item_by_code[code].get("scope_status") == "out_of_scope_by_scope"
    )
    if out_of_scope_drafts:
        raise MechanismValidationError(
            "out_of_scope_by_scope 项不得创建 Claim: "
            + ", ".join(out_of_scope_drafts[:10])
        )

    drafts = [draft.model_dump(mode="json") for draft in request.drafts]
    research_decisions = [
        decision.model_dump(mode="json") for decision in request.research_decisions
    ]
    if writer.build_research_values is not None:
        _validate_research_decisions(
            db,
            scenario=scenario,
            items=item_by_code,
            decisions=research_decisions,
        )
        input_snapshot = writer.build_input_snapshot(
            db,
            scenario=scenario,
            drafts=drafts,
            research_decisions=research_decisions,
        )
    else:
        if research_decisions:
            raise MechanismValidationError("当前 compiler 不支持 ResearchItem 决定")
        input_snapshot = writer.build_input_snapshot(
            db,
            scenario=scenario,
            drafts=drafts,
        )
    claim_values = writer.build_claim_values(
        items,
        drafts=drafts,
        facts=input_snapshot["facts"],
        evidence=input_snapshot["evidence"],
    )

    research_values: list[dict[str, Any]] = []
    if writer.build_research_values is not None:
        research_values = writer.build_research_values(
            items,
            claim_values=claim_values,
            research_decisions=research_decisions,
        )

    input_hash = writer.hash_payload(input_snapshot)
    output_payload = (
        writer.build_output_payload(
            claim_values=claim_values,
            research_values=research_values,
        )
        if writer.build_output_payload is not None
        else claim_values
    )
    output_hash = writer.hash_payload(output_payload)
    compilation = ClaimCompilation(
        id=str(uuid4()),
        scenario_id=scenario.id,
        compiler_version=writer.version,
        input_hash=input_hash,
        output_hash=output_hash,
        input_snapshot=input_snapshot,
        denominator_count=(len(research_values) if research_values else len(claim_values)),
        ready_count=sum(1 for value in claim_values if value["status"] == "awaiting_human_confirmation"),
        refused_count=sum(1 for value in claim_values if value["status"] == "refused"),
        created_by=user.id,
    )
    db.add(compilation)
    db.flush()
    claims = [
        ClaimRecord(
            id=str(uuid4()),
            compilation_id=compilation.id,
            scenario_id=scenario.id,
            **value,
        )
        for value in claim_values
    ]
    db.add_all(claims)
    db.flush()
    claim_by_code = {claim.checklist_code: claim for claim in claims}
    decision_by_code = {
        decision["checklist_code"]: decision for decision in research_decisions
    }
    research_items = [
        ResearchItem(
            id=str(uuid4()),
            compilation_id=compilation.id,
            scenario_id=scenario.id,
            linked_claim_id=(
                claim_by_code[value["checklist_code"]].id
                if value["checklist_code"] in claim_by_code
                else None
            ),
            legal_confirmed_by=(
                user.id if value["checklist_code"] in decision_by_code else None
            ),
            legal_confirmed_at=(
                _now() if value["checklist_code"] in decision_by_code else None
            ),
            **value,
        )
        for value in research_values
    ]
    if research_items:
        db.add_all(research_items)
        db.flush()
    return compilation, claims


def _validate_research_decisions(
    db: Session,
    *,
    scenario: InvestigationScenario,
    items: dict[str, dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> None:
    unknown = sorted(
        str(decision["checklist_code"])
        for decision in decisions
        if str(decision["checklist_code"]) not in items
    )
    if unknown:
        raise MechanismValidationError(
            f"研究决定引用了不在 Pack 分母中的 code: {', '.join(unknown[:10])}"
        )
    out_of_scope = sorted(
        str(decision["checklist_code"])
        for decision in decisions
        if items[str(decision["checklist_code"])].get("scope_status")
        == "out_of_scope_by_scope"
    )
    if out_of_scope:
        raise MechanismValidationError(
            "out_of_scope_by_scope 项只能保持 Scope 状态，不得设置 disposition: "
            + ", ".join(out_of_scope[:10])
        )

    negative_refs = {
        ref
        for decision in decisions
        if decision["disposition"] == "not_applicable"
        for ref in decision.get("negative_fact_refs") or []
    }
    if not negative_refs:
        return
    facts = {
        fact.id: fact
        for fact in db.query(FactRecord)
        .filter(FactRecord.id.in_(negative_refs))
        .all()
    }
    for ref in sorted(negative_refs):
        fact = facts.get(ref)
        if fact is None or fact.scenario_id != scenario.id:
            raise MechanismValidationError(
                f"not_applicable 否定事实不存在或与场景不匹配: {ref}"
            )
        if fact.status != "business_confirmed":
            raise MechanismValidationError(
                f"not_applicable 否定事实未经业务确认: {ref}"
            )
        if fact.assertion_polarity != "negative":
            raise MechanismValidationError(
                f"not_applicable 必须引用 assertion_polarity=negative 的事实: {ref}"
            )


def compilation_claims(db: Session, compilation_id: str) -> list[ClaimRecord]:
    return (
        db.query(ClaimRecord)
        .filter(ClaimRecord.compilation_id == compilation_id)
        .order_by(ClaimRecord.checklist_code.asc())
        .all()
    )


def compilation_research_items(
    db: Session, compilation_id: str
) -> list[ResearchItem]:
    return (
        db.query(ResearchItem)
        .filter(ResearchItem.compilation_id == compilation_id)
        .order_by(ResearchItem.denominator_order.asc())
        .all()
    )


def latest_compilation(
    db: Session, scenario_id: int
) -> tuple[ClaimCompilation, list[ClaimRecord]] | None:
    compilation = (
        db.query(ClaimCompilation)
        .filter(ClaimCompilation.scenario_id == scenario_id)
        .order_by(ClaimCompilation.created_at.desc())
        .first()
    )
    if compilation is None:
        return None
    return compilation, compilation_claims(db, compilation.id)


def confirm_claim(
    db: Session,
    *,
    claim: ClaimRecord,
    decision: str,
    confirmation_note: str,
    user: User,
) -> ClaimRecord:
    now = _now()
    result = db.execute(
        update(ClaimRecord)
        .where(ClaimRecord.id == claim.id, ClaimRecord.status == "awaiting_human_confirmation")
        .values(
            status="supported" if decision == "confirmed" else "refused",
            reason_codes=[] if decision == "confirmed" else ["human_rejected"],
            confirmed_by=user.id,
            confirmed_at=now,
            confirmation_note=confirmation_note.strip(),
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        raise MechanismConflict("只有 awaiting_human_confirmation 的 Claim 可被确认或驳回")
    db.execute(
        update(ResearchItem)
        .where(ResearchItem.linked_claim_id == claim.id)
        .values(
            disposition="supported" if decision == "confirmed" else "rejected",
            research_status="resolved",
            reason_codes=[] if decision == "confirmed" else ["legal_rejected"],
            legal_confirmed_by=user.id,
            legal_confirmed_at=now,
            legal_confirmation_note=confirmation_note.strip(),
            updated_at=now,
        )
    )
    db.flush()
    return db.get(ClaimRecord, claim.id)


def decide_research_item(
    db: Session,
    *,
    scenario: InvestigationScenario,
    item: ResearchItem,
    request: ResearchItemDecisionRequest,
    user: User,
) -> ResearchItem:
    if item.scenario_id != scenario.id:
        raise MechanismValidationError("ResearchItem 与场景不匹配")
    if item.scope_status != "in_scope":
        raise MechanismValidationError(
            "out_of_scope_by_scope 项不得设置 in-scope disposition"
        )
    if item.linked_claim_id is not None:
        raise MechanismValidationError(
            "已绑定真实 Claim 的 ResearchItem 必须通过 Claim 审核决定"
        )
    decision = {
        "checklist_code": item.checklist_code,
        **request.model_dump(mode="json"),
    }
    _validate_research_decisions(
        db,
        scenario=scenario,
        items={item.checklist_code: {"scope_status": item.scope_status}},
        decisions=[decision],
    )
    now = _now()
    reasons = sorted(
        set(
            list(request.reason_codes)
            + {
                "not_applicable": [
                    "business_negative_fact_confirmed",
                    "legal_not_applicable_confirmed",
                ],
                "rejected": ["legal_rejected"],
                "unanswerable": ["legal_unanswerable"],
                "uncovered": ["legal_research_incomplete"],
            }[request.disposition]
        )
    )
    db.execute(
        update(ResearchItem)
        .where(ResearchItem.id == item.id)
        .values(
            disposition=request.disposition,
            research_status=(
                "resolved"
                if request.disposition in {"not_applicable", "rejected"}
                else "research_open"
            ),
            reason_codes=reasons,
            negative_fact_refs=list(request.negative_fact_refs),
            legal_confirmed_by=user.id,
            legal_confirmed_at=now,
            legal_confirmation_note=request.confirmation_note.strip(),
            updated_at=now,
        )
    )
    db.flush()
    return db.get(ResearchItem, item.id)


def build_coverage_proof_body(
    *,
    scenario_id: int,
    compilation: ClaimCompilation,
    claims: list[ClaimRecord],
    research_items: list[ResearchItem] | None,
    denominator_ref: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the CoverageProof body (current write version)."""

    try:
        writer = versioned_registry.coverage_proof_writer_for_compiler(
            compilation.compiler_version
        )
    except versioned_registry.UnsupportedCombinationError as exc:
        raise MechanismValidationError(str(exc)) from exc
    kwargs = {
        "scenario_id": scenario_id,
        "compilation": compilation,
        "claims": claims,
        "denominator_ref": denominator_ref,
    }
    if writer.requires_research_items:
        kwargs["research_items"] = list(research_items or [])
    return writer.build_proof_body(**kwargs)


def create_coverage_proof(
    db: Session,
    *,
    scenario: InvestigationScenario,
    compilation: ClaimCompilation,
    claims: list[ClaimRecord],
    denominator_ref: str,
    user: User,
) -> CoverageProof:
    if compilation.scenario_id != scenario.id:
        raise MechanismValidationError("Claim compilation 与场景不匹配")
    try:
        writer = versioned_registry.coverage_proof_writer_for_compiler(
            compilation.compiler_version
        )
    except versioned_registry.UnsupportedCombinationError as exc:
        raise MechanismValidationError(str(exc)) from exc
    research_items = (
        compilation_research_items(db, compilation.id)
        if writer.requires_research_items
        else []
    )
    denominator, proof_body = build_coverage_proof_body(
        scenario_id=scenario.id,
        compilation=compilation,
        claims=claims,
        research_items=research_items,
        denominator_ref=denominator_ref,
    )
    covered = list(proof_body["covered_checklist_codes"])
    uncovered = list(proof_body["uncovered"])
    counts = (
        writer.stored_counts(proof_body)
        if writer.stored_counts is not None
        else (
            len(denominator),
            len(covered),
            len(uncovered),
            sum(1 for item in uncovered if item.get("status") == "refused"),
        )
    )
    proof = CoverageProof(
        id=str(uuid4()),
        scenario_id=scenario.id,
        compilation_id=compilation.id,
        denominator_ref=denominator_ref.strip(),
        denominator_hash=writer.hash_payload(denominator),
        denominator_count=counts[0],
        covered_count=counts[1],
        uncovered_count=counts[2],
        unanswerable_count=counts[3],
        proof=proof_body,
        proof_hash=writer.hash_payload(proof_body),
        created_by=user.id,
    )
    db.add(proof)
    db.flush()
    return proof


def latest_coverage_proof(db: Session, scenario_id: int) -> CoverageProof | None:
    return (
        db.query(CoverageProof)
        .filter(CoverageProof.scenario_id == scenario_id)
        .order_by(CoverageProof.created_at.desc())
        .first()
    )
