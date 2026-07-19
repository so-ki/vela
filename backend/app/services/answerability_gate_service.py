"""Fail-closed gate for artifacts intended for final customer delivery.

Draft brief reads intentionally do not call this service.  Delivery exports
must call it immediately before rendering so a stale checklist, fact, evidence
or CoverageProof cannot be hidden by an older legal-review finalization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.mechanism import ClaimCompilation, ClaimRecord, CoverageProof, ResearchItem
from app.models.scenario import InvestigationScenario
from app.services.mechanism_service import (
    compilation_research_items,
    latest_compilation,
    latest_coverage_proof,
)
from app.services.versioned.registry import (
    DeliverySnapshotReader,
    UnsupportedCombinationError,
    UnsupportedVersionError,
    current_delivery_snapshot_writer,
    get_compiler_reader,
    get_coverage_reader,
    require_supported_combination,
)


@dataclass(frozen=True)
class AnswerabilityGateError(ValueError):
    """A delivery conflict (409) or stored-integrity failure (422)."""

    message: str
    reason_codes: tuple[str, ...]
    http_status: int = 409
    compilation_id: str | None = None
    coverage_proof_id: str | None = None

    def __str__(self) -> str:
        return self.message

    def detail(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "reason_codes": list(self.reason_codes),
            "compilation_id": self.compilation_id,
            "coverage_proof_id": self.coverage_proof_id,
        }


def _integrity_error(
    message: str,
    reasons: list[str],
    *,
    compilation: ClaimCompilation | None = None,
    proof: CoverageProof | None = None,
) -> AnswerabilityGateError:
    return AnswerabilityGateError(
        message=message,
        reason_codes=tuple(sorted(set(reasons))),
        http_status=422,
        compilation_id=compilation.id if compilation else None,
        coverage_proof_id=proof.id if proof else None,
    )


def _conflict_error(
    message: str,
    reasons: list[str],
    *,
    compilation: ClaimCompilation | None = None,
    proof: CoverageProof | None = None,
) -> AnswerabilityGateError:
    return AnswerabilityGateError(
        message=message,
        reason_codes=tuple(sorted(set(reasons))),
        http_status=409,
        compilation_id=compilation.id if compilation else None,
        coverage_proof_id=proof.id if proof else None,
    )


def _drafts_structure_ok(drafts: list[Any]) -> bool:
    """Every persisted draft must be interpretable by the frozen 0.2 reader."""

    for draft in drafts:
        if not isinstance(draft, dict):
            return False
        if not isinstance(draft.get("checklist_code"), str):
            return False
        if not isinstance(draft.get("statement"), str):
            return False
        for key in ("fact_refs", "evidence_refs"):
            value = draft.get(key)
            # Historical semantics treat a missing/None value as empty.
            if value is not None and (
                not isinstance(value, list)
                or any(not isinstance(ref, str) for ref in value)
            ):
                return False
    return True


def _research_decisions_structure_ok(decisions: list[Any]) -> bool:
    for decision in decisions:
        if not isinstance(decision, dict):
            return False
        if not isinstance(decision.get("checklist_code"), str):
            return False
        if decision.get("disposition") not in {
            "not_applicable",
            "rejected",
            "unanswerable",
            "uncovered",
        }:
            return False
        if not isinstance(decision.get("confirmation_note"), str):
            return False
        if not _string_list(decision.get("negative_fact_refs")):
            return False
        if not _string_list(decision.get("reason_codes")):
            return False
    return True


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _claim_record_json_error(claim: ClaimRecord) -> str | None:
    """Return a stable reason when persisted Claim JSON is not list[str]."""

    if all(
        _string_list(value)
        for value in (claim.fact_refs, claim.evidence_refs, claim.reason_codes)
    ):
        return None
    code = claim.checklist_code
    safe_code = code if isinstance(code, str) and code.strip() else "unknown"
    return f"claim_record_json_invalid:{safe_code}"


def _research_record_json_error(item: ResearchItem) -> str | None:
    if all(
        _string_list(value)
        for value in (item.missing_facts, item.reason_codes, item.negative_fact_refs)
    ):
        return None
    code = item.checklist_code if isinstance(item.checklist_code, str) else "unknown"
    return f"research_item_json_invalid:{code}"


def _research_integrity_reasons(
    *,
    compilation: ClaimCompilation,
    claims: list[ClaimRecord],
    research_items: list[ResearchItem],
    expected_values: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    invalid_json = [
        reason
        for item in research_items
        if (reason := _research_record_json_error(item)) is not None
    ]
    reasons.extend(invalid_json)
    by_code = {item.checklist_code: item for item in research_items}
    if len(by_code) != len(research_items):
        reasons.append("duplicate_research_item_code")
    claim_by_code = {claim.checklist_code: claim for claim in claims}
    expected_by_code = {value["checklist_code"]: value for value in expected_values}
    if len(research_items) != len(expected_values):
        reasons.append("research_denominator_mismatch")
    facts = compilation.input_snapshot.get("facts") or {}
    for code, expected in expected_by_code.items():
        item = by_code.get(code)
        if item is None:
            reasons.append(f"research_item_missing:{code}")
            continue
        for field in (
            "denominator_order",
            "title",
            "dimension",
            "scope_status",
            "screening_status",
            "compiler_version",
            "item_hash",
        ):
            if getattr(item, field) != expected[field]:
                reasons.append(f"research_item_{field}_tampered:{code}")
        claim = claim_by_code.get(code)
        expected_claim_id = claim.id if claim is not None else None
        if item.linked_claim_id != expected_claim_id:
            reasons.append(f"research_item_claim_binding_invalid:{code}")
        if item.scope_status == "out_of_scope_by_scope":
            if item.disposition is not None or item.research_status != "out_of_scope":
                reasons.append(f"out_of_scope_disposition_invalid:{code}")
            continue
        if item.disposition not in {
            "supported",
            "not_applicable",
            "rejected",
            "unanswerable",
            "uncovered",
        }:
            reasons.append(f"research_disposition_invalid:{code}")
            continue
        if claim is None and item.disposition == "supported":
            reasons.append(f"supported_research_claim_missing:{code}")
        if claim is not None:
            if claim.status == "supported" and item.disposition != "supported":
                reasons.append(f"supported_claim_research_mismatch:{code}")
            elif claim.status == "awaiting_human_confirmation" and (
                item.disposition != "uncovered" or item.research_status != "claim_pending"
            ):
                reasons.append(f"pending_claim_research_mismatch:{code}")
            elif claim.status == "refused":
                expected_disposition = (
                    "rejected"
                    if list(claim.reason_codes or []) == ["human_rejected"]
                    else "unanswerable"
                )
                if item.disposition != expected_disposition:
                    reasons.append(f"refused_claim_research_mismatch:{code}")
        if item.disposition in {"supported", "not_applicable", "rejected"} and (
            not item.legal_confirmed_by
            or not item.legal_confirmed_at
            or not (item.legal_confirmation_note or "").strip()
        ):
            reasons.append(f"research_legal_confirmation_missing:{code}")
        if item.disposition == "not_applicable":
            if not item.negative_fact_refs:
                reasons.append(f"not_applicable_negative_fact_missing:{code}")
            for ref in item.negative_fact_refs:
                fact = facts.get(ref) if isinstance(facts, dict) else None
                if (
                    not isinstance(fact, dict)
                    or not fact.get("verified")
                    or fact.get("assertion_polarity") != "negative"
                ):
                    reasons.append(f"not_applicable_negative_fact_invalid:{code}:{ref}")
    return reasons


def _items_structure_ok(items: Any) -> bool:
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        hits = item.get("legal_hits")
        if hits is not None and not isinstance(hits, list):
            return False
        if isinstance(hits, list) and any(not isinstance(hit, dict) for hit in hits):
            return False
    return True


def _sections_structure_ok(sections: Any) -> bool:
    if sections is None:
        return True
    if not isinstance(sections, list):
        return False
    for section in sections:
        if not isinstance(section, dict):
            return False
        items = section.get("items")
        if items is not None and not _items_structure_ok(items):
            return False
    return True


def _checklist_payload_structure_ok(payload: Any) -> bool:
    """The live payload feeds the frozen reader recompute: reject unsupported
    JSON shapes explicitly instead of letting them raise inside the reader."""

    if not isinstance(payload, dict):
        return False
    if not _sections_structure_ok(payload.get("sections_with_legal")):
        return False
    if not _sections_structure_ok(payload.get("sections")):
        return False
    brief = payload.get("brief")
    if brief is not None:
        if not isinstance(brief, dict):
            return False
        if not _sections_structure_ok(brief.get("sections")):
            return False
    return True


def _coverage_proof_body_structure_ok(body: dict[str, Any]) -> bool:
    """Schema-0.1 bodies must be structurally interpretable even when the
    stored proof_hash was recomputed over the malformed body."""

    denominator = body.get("denominator")
    covered = body.get("covered_checklist_codes")
    uncovered = body.get("uncovered")
    if not isinstance(denominator, list) or not isinstance(covered, list):
        return False
    if not isinstance(uncovered, list):
        return False
    for entry in denominator:
        if not isinstance(entry, dict):
            return False
        if not isinstance(entry.get("checklist_code"), str):
            return False
        if not isinstance(entry.get("statement"), str):
            return False
    if any(not isinstance(code, str) for code in covered):
        return False
    for item in uncovered:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("checklist_code"), str):
            return False
        if not isinstance(item.get("status"), str):
            return False
        if not _string_list(item.get("unanswerable_reasons")):
            return False
    return True


def _included_conclusions(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Affirmative brief conclusions; explicit refusals remain deliverable."""

    included: dict[str, dict[str, Any]] = {}
    brief = payload.get("brief") or {}
    for section in brief.get("sections") or []:
        for item in section.get("items") or []:
            code = str(item.get("code") or "").strip()
            if code and item.get("gate_status") == "passed":
                included[code] = {
                    "code": code,
                    "title": item.get("title"),
                    "gate_status": item.get("gate_status"),
                    "risk_zh": item.get("risk_zh"),
                    "risk_pt": item.get("risk_pt"),
                }
    return included


def _assert_compiler_integrity(
    db: Session,
    *,
    scenario: InvestigationScenario,
    compilation: ClaimCompilation,
    claims: list[ClaimRecord],
) -> None:
    reasons: list[str] = []
    stored_snapshot = compilation.input_snapshot
    # Persisted JSON is attacker-writable via raw SQL: validate its structure
    # explicitly BEFORE any attribute access or reader call so malformed
    # shapes fail closed with 422 instead of raising an uncaught 500 — even
    # when the stored hash was recomputed over the malformed body.
    if not isinstance(stored_snapshot, dict):
        raise _integrity_error(
            "Claim compilation 输入快照不是对象，禁止交付。",
            ["compiler_input_snapshot_invalid"],
            compilation=compilation,
        )
    # Dispatch on the persisted compiler version — never on the current write
    # default (D-0008/D-0014). Unknown persisted versions are unexplainable
    # stored identities, not "stale" state: fail closed with 422.
    try:
        reader = get_compiler_reader(compilation.compiler_version)
    except UnsupportedVersionError:
        raise _integrity_error(
            "Claim compilation 使用了未注册的编译器版本，禁止交付。",
            ["compiler_version_unsupported"],
            compilation=compilation,
        ) from None
    if reader.hash_payload(stored_snapshot) != compilation.input_hash:
        reasons.append("compiler_input_hash_invalid")

    drafts = stored_snapshot.get("drafts")
    if not isinstance(drafts, list):
        reasons.append("compiler_drafts_missing")
        drafts = []
    elif not _drafts_structure_ok(drafts):
        reasons.append("compiler_input_snapshot_invalid")
        drafts = []
    research_decisions = stored_snapshot.get("research_decisions", [])
    if reader.build_research_values is not None:
        if not isinstance(research_decisions, list) or not _research_decisions_structure_ok(
            research_decisions
        ):
            reasons.append("compiler_input_snapshot_invalid")
            research_decisions = []
    elif research_decisions not in (None, []):
        reasons.append("compiler_input_snapshot_invalid")
    if reasons:
        raise _integrity_error(
            "Claim compilation 输入快照完整性校验失败，禁止交付。",
            reasons,
            compilation=compilation,
        )
    current_payload = scenario.checklist.payload if scenario.checklist else {}
    if not _checklist_payload_structure_ok(current_payload):
        raise _integrity_error(
            "当前 checklist payload 结构损坏，禁止交付。",
            ["compiler_current_payload_invalid"],
            compilation=compilation,
        )
    snapshot_kwargs = {"scenario": scenario, "drafts": drafts}
    if reader.build_research_values is not None:
        snapshot_kwargs["research_decisions"] = research_decisions
    try:
        current_snapshot = reader.build_input_snapshot(db, **snapshot_kwargs)
    except ValueError as exc:
        raise _integrity_error(
            f"当前冻结 Pack 分母无法由持久版本重建：{exc}",
            ["compiler_current_denominator_invalid"],
            compilation=compilation,
        ) from exc
    if reader.hash_payload(current_snapshot) != compilation.input_hash:
        raise _conflict_error(
            (
                "当前 checklist、双语结论、事实或法源证据已变化，"
                "请重新编译 Claim 并重新生成覆盖证明。"
            ),
            ["compiler_input_snapshot_stale"],
            compilation=compilation,
        )

    items = (
        reader.build_denominator(scenario=scenario)
        if reader.build_denominator is not None
        else reader.checklist_items(
            scenario.checklist.payload if scenario.checklist else {}
        )
    )
    expected_values = reader.build_claim_values(
        items,
        drafts=drafts,
        facts=current_snapshot["facts"],
        evidence=current_snapshot["evidence"],
    )
    invalid_claim_json = [
        reason
        for claim in claims
        if (reason := _claim_record_json_error(claim)) is not None
    ]
    if invalid_claim_json:
        raise _integrity_error(
            "Claim 记录的引用或原因字段结构非法，禁止交付。",
            invalid_claim_json,
            compilation=compilation,
        )
    if reader.build_research_values is not None:
        expected_research_values = reader.build_research_values(
            items,
            claim_values=expected_values,
            research_decisions=research_decisions,
        )
        expected_output = reader.build_output_payload(
            claim_values=expected_values,
            research_values=expected_research_values,
        )
        research_items = compilation_research_items(db, compilation.id)
        reasons.extend(
            _research_integrity_reasons(
                compilation=compilation,
                claims=claims,
                research_items=research_items,
                expected_values=expected_research_values,
            )
        )
        if compilation.denominator_count != len(expected_research_values):
            reasons.append("research_denominator_mismatch")
        if len(claims) != len(expected_values):
            reasons.append("claim_count_mismatch")
    else:
        expected_output = expected_values
        if (
            compilation.denominator_count != len(expected_values)
            or len(claims) != len(expected_values)
        ):
            reasons.append("claim_denominator_mismatch")
    if reader.hash_payload(expected_output) != compilation.output_hash:
        reasons.append("compiler_output_hash_invalid")

    claims_by_code = {claim.checklist_code: claim for claim in claims}
    if len(claims_by_code) != len(claims):
        reasons.append("duplicate_claim_code")
    for expected in expected_values:
        claim = claims_by_code.get(expected["checklist_code"])
        if claim is None:
            reasons.append(f"claim_missing:{expected['checklist_code']}")
            continue
        for field in ("statement", "fact_refs", "evidence_refs"):
            if getattr(claim, field) != expected[field]:
                reasons.append(f"claim_{field}_tampered:{claim.checklist_code}")
        if expected["status"] == "refused":
            if claim.status != "refused" or list(claim.reason_codes or []) != expected["reason_codes"]:
                reasons.append(f"compiler_refusal_tampered:{claim.checklist_code}")
        elif claim.status not in {"awaiting_human_confirmation", "supported", "refused"}:
            reasons.append(f"claim_status_invalid:{claim.checklist_code}")
        elif claim.status == "supported":
            if (
                not claim.confirmed_by
                or not claim.confirmed_at
                or not (claim.confirmation_note or "").strip()
            ):
                reasons.append(f"supported_claim_missing_human_confirmation:{claim.checklist_code}")
            if list(claim.reason_codes or []):
                reasons.append(f"supported_claim_has_refusal_reason:{claim.checklist_code}")
        elif claim.status == "refused" and list(claim.reason_codes or []) != ["human_rejected"]:
            reasons.append(f"human_refusal_reason_invalid:{claim.checklist_code}")

    if reasons:
        raise _integrity_error(
            "Claim compilation 或 Claim 记录完整性校验失败，禁止交付。",
            reasons,
            compilation=compilation,
        )


def _assert_coverage_integrity(
    db: Session,
    *,
    scenario: InvestigationScenario,
    compilation: ClaimCompilation,
    claims: list[ClaimRecord],
    proof: CoverageProof,
) -> None:
    if proof.compilation_id != compilation.id or proof.scenario_id != scenario.id:
        raise _conflict_error(
            "最新 CoverageProof 不属于当前 Claim compilation，请重新生成覆盖证明。",
            ["coverage_proof_compilation_mismatch"],
            compilation=compilation,
            proof=proof,
        )

    stored_body = proof.proof
    # A proof body that is not a JSON object has no readable schema identity:
    # fail closed with 422 before any attribute access, even when proof_hash
    # was recomputed over the malformed value (would otherwise raise a 500).
    if not isinstance(stored_body, dict):
        raise _integrity_error(
            "CoverageProof 存储体不是对象，无法解释其 schema 版本，禁止交付。",
            ["coverage_proof_schema_unsupported"],
            compilation=compilation,
            proof=proof,
        )
    # Dispatch on the persisted proof schema version (D-0014). A missing,
    # non-string or unregistered version is an unexplainable stored identity:
    # fail closed with 422, never fall back to the current reader and never
    # treat it as recompilable staleness.
    stored_proof_version = stored_body.get("schema_version")
    try:
        proof_reader = get_coverage_reader(stored_proof_version)
    except UnsupportedVersionError:
        raise _integrity_error(
            "CoverageProof 使用了未注册的 schema 版本，禁止交付。",
            ["coverage_proof_schema_unsupported"],
            compilation=compilation,
            proof=proof,
        ) from None
    try:
        require_supported_combination(compilation.compiler_version, proof_reader.version)
    except UnsupportedCombinationError:
        raise _integrity_error(
            "Claim compiler 与 CoverageProof 的版本组合不受支持，禁止交付。",
            [
                "version_combination_unsupported:"
                f"{compilation.compiler_version}+{proof_reader.version}"
            ],
            compilation=compilation,
            proof=proof,
        ) from None

    if not _coverage_proof_body_structure_ok(stored_body) or (
        proof_reader.validate_body_structure is not None
        and not proof_reader.validate_body_structure(stored_body)
    ):
        raise _integrity_error(
            "CoverageProof 存储体结构非法，禁止交付。",
            ["coverage_proof_body_invalid"],
            compilation=compilation,
            proof=proof,
        )

    stored_denominator = list(stored_body.get("denominator") or [])
    stored_uncovered = list(stored_body.get("uncovered") or [])
    integrity_reasons: list[str] = []
    if proof_reader.hash_payload(stored_body) != proof.proof_hash:
        integrity_reasons.append("coverage_proof_stored_hash_invalid")
    if proof.denominator_hash != proof_reader.hash_payload(stored_denominator):
        integrity_reasons.append("coverage_denominator_hash_invalid")
    stored_counts = (
        proof_reader.stored_counts(stored_body)
        if proof_reader.stored_counts is not None
        else (
            len(stored_denominator),
            len(stored_body.get("covered_checklist_codes") or []),
            len(stored_uncovered),
            sum(1 for item in stored_uncovered if item.get("status") == "refused"),
        )
    )
    actual_counts = (
        proof.denominator_count,
        proof.covered_count,
        proof.uncovered_count,
        proof.unanswerable_count,
    )
    if actual_counts != stored_counts:
        integrity_reasons.append("coverage_proof_counts_invalid")
    if (
        stored_body.get("scenario_id") != scenario.id
        or stored_body.get("compilation_id") != compilation.id
        or stored_body.get("compiler_input_hash") != compilation.input_hash
        or stored_body.get("compiler_output_hash") != compilation.output_hash
        or stored_body.get("denominator_ref") != proof.denominator_ref
    ):
        integrity_reasons.append("coverage_proof_binding_invalid")
    if integrity_reasons:
        raise _integrity_error(
            "CoverageProof 存储哈希、绑定或计数完整性校验失败，禁止交付。",
            integrity_reasons,
            compilation=compilation,
            proof=proof,
        )

    proof_kwargs = {
        "scenario_id": scenario.id,
        "compilation": compilation,
        "claims": claims,
        "denominator_ref": proof.denominator_ref,
    }
    if proof_reader.requires_research_items:
        proof_kwargs["research_items"] = compilation_research_items(
            db, compilation.id
        )
    denominator, expected_body = proof_reader.build_proof_body(**proof_kwargs)
    expected_hash = proof_reader.hash_payload(expected_body)
    if (
        proof.proof != expected_body
        or proof.proof_hash != expected_hash
        or proof.denominator_hash != proof_reader.hash_payload(denominator)
    ):
        raise _conflict_error(
            "CoverageProof 已落后于当前 Claim 状态，请重新生成覆盖证明。",
            ["coverage_proof_stale"],
            compilation=compilation,
            proof=proof,
        )


def require_delivery_answerability(
    db: Session,
    *,
    scenario: InvestigationScenario,
    snapshot_reader: DeliverySnapshotReader | None = None,
) -> dict[str, Any]:
    """Validate and return the proof record attached to delivery audit output."""

    latest = latest_compilation(db, scenario.id)
    if latest is None:
        raise _conflict_error(
            (
                "尚无 Claim compilation；草稿可预览，"
                "但正式交付前必须编译并人工确认 Claim。"
            ),
            ["claim_compilation_missing"],
        )
    compilation, claims = latest
    _assert_compiler_integrity(
        db,
        scenario=scenario,
        compilation=compilation,
        claims=claims,
    )

    proof = latest_coverage_proof(db, scenario.id)
    if proof is None:
        raise _conflict_error(
            "尚无 CoverageProof；草稿可预览，但正式交付前必须生成覆盖证明。",
            ["coverage_proof_missing"],
            compilation=compilation,
        )
    _assert_coverage_integrity(
        db,
        scenario=scenario,
        compilation=compilation,
        claims=claims,
        proof=proof,
    )

    included = _included_conclusions(
        scenario.checklist.payload if scenario.checklist else {}
    )
    included_codes = sorted(included)
    claim_by_code = {claim.checklist_code: claim for claim in claims}
    unsupported = [
        code
        for code in included_codes
        if claim_by_code.get(code) is None or claim_by_code[code].status != "supported"
    ]
    if unsupported:
        raise _conflict_error(
            "存在未由法务人工确认支持的交付结论，禁止导出正式制品。",
            [f"included_claim_not_supported:{code}" for code in unsupported],
            compilation=compilation,
            proof=proof,
        )

    unbound_text = [
        code
        for code in included_codes
        if not str(included[code].get("risk_zh") or "").strip()
        or claim_by_code[code].statement != included[code]["risk_zh"]
    ]
    if unbound_text:
        raise _conflict_error(
            (
                "交付简报文字未与法务确认的 Claim statement 精确绑定，"
                "请按当前简报重新编译。"
            ),
            [f"included_conclusion_text_unbound:{code}" for code in unbound_text],
            compilation=compilation,
            proof=proof,
        )

    provisional_refs = sorted(
        {
            ref
            for claim in claims
            if claim.checklist_code in included_codes and claim.status == "supported"
            for ref in list(claim.evidence_refs or [])
            if (compilation.input_snapshot.get("evidence", {}).get(ref) or {}).get(
                "review_status"
            )
            != "expert_verified"
        }
    )
    reader = snapshot_reader or current_delivery_snapshot_writer()
    return reader.build_gate_payload(
        compiler_version=compilation.compiler_version,
        compilation_id=compilation.id,
        compiler_input_hash=compilation.input_hash,
        compiler_output_hash=compilation.output_hash,
        coverage_proof_id=proof.id,
        coverage_proof_hash=proof.proof_hash,
        denominator_hash=proof.denominator_hash,
        included_conclusion_codes=included_codes,
        included_conclusions=[included[code] for code in included_codes],
        explicitly_unanswerable_count=proof.unanswerable_count,
        # Disclosure only; this never promotes evidence or a Claim.
        provisional_evidence_refs=provisional_refs,
    )
