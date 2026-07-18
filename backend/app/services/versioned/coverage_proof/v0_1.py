"""Coverage proof 0.1 — HASH-FROZEN reader/writer. DO NOT EDIT.

Byte-semantic copy of build_coverage_proof_body as it existed at commit
efc76e0 (mechanism_service.py), characterized by tests/goldens/versioned/
coverage_proof_v0_1.json. Every key, the denominator/uncovered ordering, the
"human_confirmation_pending" reason and the answerability_rule sentence are
hash-load-bearing. Behavior changes must be added as a new version module.

Pure module: no imports beyond typing/hashing; model instances are read as
plain attributes. Must not import mechanism_service or the gate.
"""

from __future__ import annotations

from typing import Any

from app.services.versioned.canonical_hash import canonical_hash_v1

VERSION = "0.1"


def hash_payload(payload: Any) -> str:
    return canonical_hash_v1(payload)


def build_proof_body(
    *,
    scenario_id: int,
    compilation: Any,
    claims: list[Any],
    denominator_ref: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the deterministic body committed by a CoverageProof (schema 0.1)."""

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
