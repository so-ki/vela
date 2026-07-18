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
)
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.mechanism import (
    ClaimCompileRequest,
    CoverageTaskCreateRequest,
    FactRecordCreateRequest,
    MaterialLedgerUpsertRequest,
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
# Write default; readers dispatch on the persisted version, never on this.
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
    items = _checklist_items(payload)
    if not items:
        raise MechanismValidationError("场景没有可编译的 checklist 分母")
    item_by_code = {str(item["code"]): item for item in items}
    draft_by_code = {draft.checklist_code: draft for draft in request.drafts}
    unknown_codes = sorted(set(draft_by_code) - set(item_by_code))
    if unknown_codes:
        raise MechanismValidationError(
            f"Claim 草稿引用了不在当前清单中的 code: {', '.join(unknown_codes[:10])}"
        )

    drafts = [draft.model_dump(mode="json") for draft in request.drafts]
    input_snapshot = build_compiler_input_snapshot(
        db,
        scenario=scenario,
        drafts=drafts,
    )
    claim_values = build_compiler_claim_values(
        items,
        drafts=drafts,
        facts=input_snapshot["facts"],
        evidence=input_snapshot["evidence"],
    )

    writer = versioned_registry.current_compiler_writer()
    input_hash = writer.hash_payload(input_snapshot)
    output_hash = writer.hash_payload(claim_values)
    compilation = ClaimCompilation(
        id=str(uuid4()),
        scenario_id=scenario.id,
        compiler_version=COMPILER_VERSION,
        input_hash=input_hash,
        output_hash=output_hash,
        input_snapshot=input_snapshot,
        denominator_count=len(claim_values),
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
    return compilation, claims


def compilation_claims(db: Session, compilation_id: str) -> list[ClaimRecord]:
    return (
        db.query(ClaimRecord)
        .filter(ClaimRecord.compilation_id == compilation_id)
        .order_by(ClaimRecord.checklist_code.asc())
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
    db.flush()
    return db.get(ClaimRecord, claim.id)


def build_coverage_proof_body(
    *,
    scenario_id: int,
    compilation: ClaimCompilation,
    claims: list[ClaimRecord],
    denominator_ref: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the deterministic body committed by a CoverageProof."""

    denominator = [
        {"checklist_code": claim.checklist_code, "statement": claim.statement}
        for claim in sorted(claims, key=lambda value: value.checklist_code)
    ]
    covered = [claim.checklist_code for claim in claims if claim.status == "supported"]
    uncovered = [
        {
            "checklist_code": claim.checklist_code,
            "status": claim.status,
            "unanswerable_reasons": (
                list(claim.reason_codes)
                if claim.status == "refused"
                else ["human_confirmation_pending"]
            ),
        }
        for claim in claims
        if claim.status != "supported"
    ]
    proof_body = {
        "schema_version": "0.1",
        "scenario_id": scenario_id,
        "compilation_id": compilation.id,
        "compiler_input_hash": compilation.input_hash,
        "compiler_output_hash": compilation.output_hash,
        "denominator_ref": denominator_ref.strip(),
        "denominator": denominator,
        "covered_checklist_codes": sorted(covered),
        "uncovered": sorted(uncovered, key=lambda item: item["checklist_code"]),
        "answerability_rule": (
            "covered 仅计入经法务人工确认的 supported Claim；"
            "awaiting/refused 均不得作为已覆盖结论。"
        ),
    }
    return denominator, proof_body


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
    denominator, proof_body = build_coverage_proof_body(
        scenario_id=scenario.id,
        compilation=compilation,
        claims=claims,
        denominator_ref=denominator_ref,
    )
    covered = list(proof_body["covered_checklist_codes"])
    uncovered = list(proof_body["uncovered"])
    proof = CoverageProof(
        id=str(uuid4()),
        scenario_id=scenario.id,
        compilation_id=compilation.id,
        denominator_ref=denominator_ref.strip(),
        denominator_hash=stable_hash(denominator),
        denominator_count=len(denominator),
        covered_count=len(covered),
        uncovered_count=len(uncovered),
        unanswerable_count=sum(1 for claim in claims if claim.status == "refused"),
        proof=proof_body,
        proof_hash=stable_hash(proof_body),
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
