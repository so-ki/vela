"""Fail-closed gate for artifacts intended for final customer delivery.

Draft brief reads intentionally do not call this service.  Delivery exports
must call it immediately before rendering so a stale checklist, fact, evidence
or CoverageProof cannot be hidden by an older legal-review finalization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.mechanism import ClaimCompilation, ClaimRecord, CoverageProof
from app.models.scenario import InvestigationScenario
from app.services.generation_guard import stable_hash
from app.services.mechanism_service import (
    build_coverage_proof_body,
    latest_compilation,
    latest_coverage_proof,
)
from app.services.versioned.registry import (
    UnsupportedVersionError,
    get_compiler_reader,
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
    stored_snapshot = compilation.input_snapshot or {}
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
    if reasons:
        raise _integrity_error(
            "Claim compilation 输入快照完整性校验失败，禁止交付。",
            reasons,
            compilation=compilation,
        )
    current_snapshot = reader.build_input_snapshot(
        db,
        scenario=scenario,
        drafts=drafts,
    )
    if reader.hash_payload(current_snapshot) != compilation.input_hash:
        raise _conflict_error(
            (
                "当前 checklist、双语结论、事实或法源证据已变化，"
                "请重新编译 Claim 并重新生成覆盖证明。"
            ),
            ["compiler_input_snapshot_stale"],
            compilation=compilation,
        )

    items = reader.checklist_items(scenario.checklist.payload if scenario.checklist else {})
    expected_values = reader.build_claim_values(
        items,
        drafts=drafts,
        facts=current_snapshot["facts"],
        evidence=current_snapshot["evidence"],
    )
    if reader.hash_payload(expected_values) != compilation.output_hash:
        reasons.append("compiler_output_hash_invalid")
    if compilation.denominator_count != len(expected_values) or len(claims) != len(expected_values):
        reasons.append("claim_denominator_mismatch")

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

    stored_body = proof.proof or {}
    stored_denominator = list(stored_body.get("denominator") or [])
    stored_uncovered = list(stored_body.get("uncovered") or [])
    integrity_reasons: list[str] = []
    if stable_hash(stored_body) != proof.proof_hash:
        integrity_reasons.append("coverage_proof_stored_hash_invalid")
    if proof.denominator_hash != stable_hash(stored_denominator):
        integrity_reasons.append("coverage_denominator_hash_invalid")
    stored_counts = (
        len(stored_denominator),
        len(stored_body.get("covered_checklist_codes") or []),
        len(stored_uncovered),
        sum(1 for item in stored_uncovered if item.get("status") == "refused"),
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

    denominator, expected_body = build_coverage_proof_body(
        scenario_id=scenario.id,
        compilation=compilation,
        claims=claims,
        denominator_ref=proof.denominator_ref,
    )
    expected_hash = stable_hash(expected_body)
    if (
        proof.proof != expected_body
        or proof.proof_hash != expected_hash
        or proof.denominator_hash != stable_hash(denominator)
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
    return {
        "gate_version": "1.0",
        "decision": "passed",
        "compiler_version": compilation.compiler_version,
        "compilation_id": compilation.id,
        "compiler_input_hash": compilation.input_hash,
        "compiler_output_hash": compilation.output_hash,
        "coverage_proof_id": proof.id,
        "coverage_proof_hash": proof.proof_hash,
        "denominator_hash": proof.denominator_hash,
        "included_conclusion_codes": included_codes,
        "included_conclusions_hash": stable_hash(
            [included[code] for code in included_codes]
        ),
        "supported_included_count": len(included_codes),
        "explicitly_unanswerable_count": proof.unanswerable_count,
        # This is disclosure, never a promotion: only the recorded legal human
        # decision changes a Claim to supported; corpus status remains intact.
        "provisional_evidence_refs": provisional_refs,
        "provisional_evidence_promoted": False,
    }
