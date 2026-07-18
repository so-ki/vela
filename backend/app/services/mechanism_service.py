from __future__ import annotations

import copy
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


MATERIAL_STATES = {
    "missing",
    "received",
    "unreadable",
    "ambiguous",
    "verified",
    "not_applicable",
}
HUMAN_CONFIRMED_MATERIAL_STATES = {"verified", "not_applicable"}
COMPILER_VERSION = "0.2"


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
    sections = payload.get("sections_with_legal") or payload.get("sections") or []
    by_code: dict[str, dict[str, Any]] = {}
    for section in sections:
        for item in section.get("items") or []:
            code = str(item.get("code") or "").strip()
            if code and code not in by_code:
                by_code[code] = copy.deepcopy(item)
    return list(by_code.values())


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


def _fact_inventory(db: Session, scenario_id: int) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for fact in list_fact_records(db, scenario_id):
        inventory[fact.id] = {
            "ref": fact.id,
            "subject": fact.subject,
            "attribute": fact.attribute,
            "value": fact.value,
            "fact_time": fact.fact_time,
            "block_id": fact.block_id,
            "fact_pack_version": fact.fact_pack_version,
            "source_document": fact.source_document,
            "verification_status": fact.status,
            "verified": fact.status == "business_confirmed",
        }
    return inventory


def _evidence_inventory(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for item in items:
        code = str(item.get("code") or "")
        for hit in item.get("legal_hits") or []:
            hit_id = str(hit.get("id") or hit.get("urn") or "").strip()
            if not hit_id:
                continue
            ref = f"{code}:{hit_id}"
            grounded = bool(hit.get("grounded")) or hit.get("citation_status") == "grounded"
            review_status = str(hit.get("review_status") or "pending")
            inventory[ref] = {
                "ref": ref,
                "checklist_code": code,
                "hit_id": hit_id,
                "urn": hit.get("urn"),
                "url": hit.get("url"),
                "pinpoint": hit.get("pinpoint"),
                "grounded": grounded,
                "review_status": review_status,
                "requires_review": bool(hit.get("requires_review", review_status != "expert_verified")),
                # Make any post-compilation change to the retrieved evidence
                # visible to the delivery gate, including excerpts and
                # validity metadata that are not repeated in this inventory.
                "source_hash": stable_hash(hit),
                # A grounded but provisional source can be examined by the
                # legal confirmer.  It must never become supported until that
                # explicit human decision is recorded below.
                "eligible": grounded,
            }
    return inventory


def _checklist_inventory(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the semantic checklist denominator used by the compiler.

    Legal hits are hashed independently in the evidence inventory.  Everything
    else on an item is covered by ``item_hash`` so changing a description,
    tier, exception or other rule field invalidates a delivery compilation.
    """

    inventory: list[dict[str, Any]] = []
    for item in items:
        item_without_hits = {
            key: copy.deepcopy(value)
            for key, value in item.items()
            if key != "legal_hits"
        }
        inventory.append(
            {
                "code": str(item.get("code") or ""),
                "title": item.get("title"),
                "priority": item.get("priority"),
                "item_hash": stable_hash(item_without_hits),
            }
        )
    return inventory


def _brief_conclusion_inventory(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind the exact bilingual text that a delivery artifact will render."""

    inventory: list[dict[str, Any]] = []
    brief = payload.get("brief") or {}
    for section in brief.get("sections") or []:
        for item in section.get("items") or []:
            body = {
                "code": str(item.get("code") or ""),
                "title": item.get("title"),
                "gate_status": item.get("gate_status"),
                "risk_zh": item.get("risk_zh"),
                "risk_pt": item.get("risk_pt"),
            }
            if body["code"]:
                inventory.append({**body, "conclusion_hash": stable_hash(body)})
    return inventory


def build_compiler_input_snapshot(
    db: Session,
    *,
    scenario: InvestigationScenario,
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the current checklist/fact/evidence snapshot for Claim compilation."""

    payload = scenario.checklist.payload if scenario.checklist else {}
    items = _checklist_items(payload)
    return {
        "scenario_id": scenario.id,
        "checklist": _checklist_inventory(items),
        "brief_conclusions": _brief_conclusion_inventory(payload),
        "facts": _fact_inventory(db, scenario.id),
        "evidence": _evidence_inventory(items),
        "drafts": copy.deepcopy(drafts),
    }


def _claim_reasons(
    fact_refs: list[str],
    evidence_refs: list[str],
    facts: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    checklist_code: str,
) -> list[str]:
    reasons: list[str] = []
    if not fact_refs:
        reasons.append("fact_reference_required")
    if not evidence_refs:
        reasons.append("evidence_reference_required")
    for ref in fact_refs:
        fact = facts.get(ref)
        if fact is None:
            reasons.append(f"fact_reference_not_found:{ref}")
        elif not fact["verified"]:
            reasons.append(f"fact_not_verified:{ref}")
    for ref in evidence_refs:
        item = evidence.get(ref)
        if item is None:
            reasons.append(f"evidence_reference_not_found:{ref}")
            continue
        if item["checklist_code"] != checklist_code:
            reasons.append(f"evidence_wrong_checklist_item:{ref}")
        if not item["grounded"]:
            reasons.append(f"evidence_not_grounded:{ref}")
    return sorted(set(reasons))


def build_compiler_claim_values(
    items: list[dict[str, Any]],
    *,
    drafts: list[dict[str, Any]],
    facts: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pure deterministic compiler output before any human decision."""

    draft_by_code = {str(draft["checklist_code"]): draft for draft in drafts}
    claim_values: list[dict[str, Any]] = []
    for item in items:
        code = str(item["code"])
        draft = draft_by_code.get(code)
        fact_refs = list(draft.get("fact_refs") or []) if draft else []
        evidence_refs = list(draft.get("evidence_refs") or []) if draft else []
        reasons = _claim_reasons(fact_refs, evidence_refs, facts, evidence, code)
        claim_values.append(
            {
                "checklist_code": code,
                "statement": (
                    str(draft["statement"])
                    if draft
                    else f"待核验事项：{item.get('title') or item.get('description') or code}"
                ),
                "status": "refused" if reasons else "awaiting_human_confirmation",
                "fact_refs": fact_refs,
                "evidence_refs": evidence_refs,
                "reason_codes": reasons,
            }
        )
    return claim_values


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

    input_hash = stable_hash(input_snapshot)
    output_hash = stable_hash(claim_values)
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
