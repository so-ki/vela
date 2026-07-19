"""Frozen delivery snapshot 1.0 and embedded Answerability Gate 1.0 shapes."""

from __future__ import annotations

from typing import Any

from app.services.versioned.canonical_hash.v1 import canonical_hash_v1

VERSION = "1.0"
GATE_VERSION = "1.0"


def hash_payload(payload: Any) -> str:
    return canonical_hash_v1(payload)


def build_gate_payload(
    *,
    compiler_version: str,
    compilation_id: str,
    compiler_input_hash: str,
    compiler_output_hash: str,
    coverage_proof_id: str,
    coverage_proof_hash: str,
    denominator_hash: str,
    included_conclusion_codes: list[str],
    included_conclusions: list[dict[str, Any]],
    explicitly_unanswerable_count: int,
    provisional_evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "gate_version": GATE_VERSION,
        "decision": "passed",
        "compiler_version": compiler_version,
        "compilation_id": compilation_id,
        "compiler_input_hash": compiler_input_hash,
        "compiler_output_hash": compiler_output_hash,
        "coverage_proof_id": coverage_proof_id,
        "coverage_proof_hash": coverage_proof_hash,
        "denominator_hash": denominator_hash,
        "included_conclusion_codes": included_conclusion_codes,
        "included_conclusions_hash": hash_payload(included_conclusions),
        "supported_included_count": len(included_conclusion_codes),
        "explicitly_unanswerable_count": explicitly_unanswerable_count,
        "provisional_evidence_refs": provisional_evidence_refs,
        "provisional_evidence_promoted": False,
    }


def build_mechanism_payload(
    *,
    compilation: Any,
    claims_snapshot: list[dict[str, Any]],
    proof: Any,
    gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "compilation_id": compilation.id,
        "compiler_version": compilation.compiler_version,
        "compiler_input_hash": compilation.input_hash,
        "compiler_output_hash": compilation.output_hash,
        "confirmed_claims_hash": hash_payload(claims_snapshot),
        "claim_count": len(claims_snapshot),
        "coverage_proof_id": proof.id,
        "coverage_proof_hash": proof.proof_hash,
        "coverage_denominator_hash": proof.denominator_hash,
        "answerability_gate": gate,
    }


def build_snapshot_payload(
    *,
    scenario: Any,
    payload: dict[str, Any],
    review: dict[str, Any],
    generation_config: Any,
    mechanism: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "scenario_id": scenario.id,
        "scope_snapshot_hash": scenario.scope_snapshot_hash,
        "checklist_id": scenario.checklist.id,
        "checklist_revision": scenario.checklist.revision,
        "checklist_payload_hash": hash_payload(payload),
        "review": {
            "status": review.get("status"),
            "revision": review.get("revision"),
            "finalized_at": review.get("finalized_at"),
            "finalized_by_id": review.get("finalized_by_id"),
        },
        "generation": {
            "attempt_id": generation_config.attempt_id,
            "snapshot_hash": generation_config.snapshot_hash,
            "config_hash": generation_config.config_hash,
            "generation_input_hash": generation_config.generation_input_hash,
            "capability_pack_id": generation_config.capability_pack_id,
            "capability_pack_version": generation_config.capability_pack_version,
            "capability_pack_hash": generation_config.capability_pack_hash,
            "rules_artifact_id": generation_config.rules_artifact_id,
            "rules_artifact_version": generation_config.rules_artifact_version,
            "rules_artifact_hash": generation_config.rules_artifact_hash,
            "corpus_artifact_id": generation_config.corpus_artifact_id,
            "corpus_artifact_version": generation_config.corpus_artifact_version,
            "corpus_artifact_hash": generation_config.corpus_artifact_hash,
        },
        "mechanism": mechanism,
    }
