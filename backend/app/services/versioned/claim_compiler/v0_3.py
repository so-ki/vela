"""Claim compiler 0.3 -- full Pack denominator and independent ResearchItems.

This version is append-only. It resolves the exact frozen Capability Pack,
keeps all 30 rule items in their artifact order and never creates a
ClaimRecord without an actual legal draft.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.capability_packs.registry import get_capability_pack_registry
from app.models.mechanism import FactRecord
from app.models.scenario import InvestigationScenario
from app.services.versioned.canonical_hash import canonical_hash_v1
from app.services.versioned.claim_compiler import v0_2 as compiler_v0_2


VERSION = "0.3"
PACK_TOTAL = 30
_SNAPSHOT_NON_SEMANTIC = {
    "snapshot_hash",
    "generation_input_id",
    "audit_metadata",
    "labels",
    "confirmed_at",
    "confirmed_by",
    "confirmed_by_name",
}


def hash_payload(payload: Any) -> str:
    return canonical_hash_v1(payload)


def checklist_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return compiler_v0_2.checklist_items(payload)


def fact_inventory(db: Session, scenario_id: int) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    facts = (
        db.query(FactRecord)
        .filter(FactRecord.scenario_id == scenario_id)
        .order_by(FactRecord.created_at.asc(), FactRecord.id.asc())
        .all()
    )
    for fact in facts:
        inventory[fact.id] = {
            "ref": fact.id,
            "subject": fact.subject,
            "attribute": fact.attribute,
            "value": fact.value,
            "assertion_polarity": fact.assertion_polarity,
            "fact_time": fact.fact_time,
            "block_id": fact.block_id,
            "fact_pack_version": fact.fact_pack_version,
            "source_document": fact.source_document,
            "verification_status": fact.status,
            "verified": fact.status == "business_confirmed",
        }
    return inventory


def _scope_snapshot(scenario: InvestigationScenario) -> dict[str, Any]:
    payload = scenario.checklist.payload if scenario.checklist else {}
    snapshot = payload.get("scenario_scope_snapshot") or (
        (scenario.scenario_scope or {}).get("snapshot")
    )
    if not isinstance(snapshot, dict) or not snapshot:
        raise ValueError("缺少已冻结的 Capability Pack Scope 快照")
    stored_hash = snapshot.get("snapshot_hash")
    semantic_body = {
        key: value
        for key, value in snapshot.items()
        if key not in _SNAPSHOT_NON_SEMANTIC
    }
    if (
        not isinstance(stored_hash, str)
        or hash_payload(semantic_body) != stored_hash
        or scenario.scope_snapshot_hash != stored_hash
    ):
        raise ValueError("Scope 快照哈希与场景绑定不一致")
    return snapshot


def _frozen_rules(snapshot: dict[str, Any]) -> dict[str, Any]:
    pack = get_capability_pack_registry().get_exact(
        str(snapshot.get("capability_pack_id") or ""),
        str(snapshot.get("capability_pack_version") or ""),
        str(snapshot.get("capability_pack_hash") or ""),
    )
    manifest = pack.manifest
    expected = {
        "rules_artifact_id": manifest.rules_artifact.artifact_id,
        "rules_artifact_version": manifest.rules_artifact.version,
        "rules_artifact_hash": manifest.rules_artifact.content_hash,
        "corpus_artifact_id": manifest.corpus_artifact.artifact_id,
        "corpus_artifact_version": manifest.corpus_artifact.version,
        "corpus_artifact_hash": manifest.corpus_artifact.content_hash,
        "issue_modules": list(manifest.issue_modules),
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise ValueError("Scope 快照与冻结 Capability Pack 制品不一致")
    return pack.rules


def build_denominator(*, scenario: InvestigationScenario) -> list[dict[str, Any]]:
    snapshot = _scope_snapshot(scenario)
    rules = _frozen_rules(snapshot)
    raw_items = list(rules.get("checklist_items") or [])
    codes = [str(item.get("id") or "").strip() for item in raw_items]
    if len(raw_items) != PACK_TOTAL or len(set(codes)) != PACK_TOTAL or not all(codes):
        raise ValueError("冻结 Capability Pack 分母不是 30 个唯一项")

    selected_dimensions = set(snapshot.get("compliance_dimensions") or [])
    valid_dimensions = set((rules.get("dimensions") or {}).keys())
    if not selected_dimensions or selected_dimensions - valid_dimensions:
        raise ValueError("Scope 快照的协查维度无效")
    screened = {
        str(item.get("code") or ""): item
        for item in checklist_items(
            scenario.checklist.payload if scenario.checklist else {}
        )
    }

    denominator: list[dict[str, Any]] = []
    for order, raw in enumerate(raw_items, start=1):
        code = str(raw["id"])
        current = screened.get(code) or {}
        dimension = str(raw["dimension"])
        denominator.append(
            {
                "checklist_code": code,
                "denominator_order": order,
                "title": str(raw.get("title") or raw.get("description") or code),
                "description": str(raw.get("description") or ""),
                "dimension": dimension,
                "priority": str(raw.get("priority") or ""),
                "scope_status": (
                    "in_scope"
                    if dimension in selected_dimensions
                    else "out_of_scope_by_scope"
                ),
                "screening_status": (
                    "selected_by_screening" if code in screened else "screened_out"
                ),
                "screening_relevance_score": current.get("relevance_score"),
                "screening_rationale": current.get("rationale"),
                "pack_item_hash": hash_payload(raw),
            }
        )
    return denominator


def build_input_snapshot(
    db: Session,
    *,
    scenario: InvestigationScenario,
    drafts: list[dict[str, Any]],
    research_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = scenario.checklist.payload if scenario.checklist else {}
    screened_items = checklist_items(payload)
    snapshot = _scope_snapshot(scenario)
    return {
        "scenario_id": scenario.id,
        "scope_snapshot_hash": snapshot["snapshot_hash"],
        "capability_pack": {
            "pack_id": snapshot.get("capability_pack_id"),
            "pack_version": snapshot.get("capability_pack_version"),
            "pack_hash": snapshot.get("capability_pack_hash"),
            "rules_artifact_id": snapshot.get("rules_artifact_id"),
            "rules_artifact_version": snapshot.get("rules_artifact_version"),
            "rules_artifact_hash": snapshot.get("rules_artifact_hash"),
        },
        "pack_denominator": build_denominator(scenario=scenario),
        "brief_conclusions": compiler_v0_2.brief_conclusion_inventory(payload),
        "facts": fact_inventory(db, scenario.id),
        "evidence": compiler_v0_2.evidence_inventory(screened_items),
        "drafts": copy.deepcopy(drafts),
        "research_decisions": copy.deepcopy(research_decisions or []),
    }


def build_claim_values(
    items: list[dict[str, Any]],
    *,
    drafts: list[dict[str, Any]],
    facts: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    draft_by_code = {str(draft["checklist_code"]): draft for draft in drafts}
    claim_values: list[dict[str, Any]] = []
    for item in items:
        code = str(item["checklist_code"])
        draft = draft_by_code.get(code)
        if draft is None:
            continue
        fact_refs = list(draft.get("fact_refs") or [])
        evidence_refs = list(draft.get("evidence_refs") or [])
        reasons = compiler_v0_2.claim_reasons(
            fact_refs,
            evidence_refs,
            facts,
            evidence,
            code,
        )
        claim_values.append(
            {
                "checklist_code": code,
                "statement": str(draft["statement"]),
                "status": "refused" if reasons else "awaiting_human_confirmation",
                "fact_refs": fact_refs,
                "evidence_refs": evidence_refs,
                "reason_codes": reasons,
            }
        )
    return claim_values


def build_research_values(
    items: list[dict[str, Any]],
    *,
    claim_values: list[dict[str, Any]],
    research_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claim_by_code = {value["checklist_code"]: value for value in claim_values}
    decision_by_code = {
        str(value["checklist_code"]): value for value in research_decisions
    }
    values: list[dict[str, Any]] = []
    for item in items:
        code = str(item["checklist_code"])
        scope_status = str(item["scope_status"])
        claim = claim_by_code.get(code)
        decision = decision_by_code.get(code)
        if scope_status == "out_of_scope_by_scope":
            disposition = None
            research_status = "out_of_scope"
            reason_codes = ["out_of_scope_by_scope"]
            missing_facts: list[str] = []
            negative_fact_refs: list[str] = []
        elif decision is not None:
            disposition = str(decision["disposition"])
            research_status = (
                "resolved"
                if disposition in {"not_applicable", "rejected"}
                else "research_open"
            )
            reason_codes = sorted(
                set(
                    list(decision.get("reason_codes") or [])
                    + {
                        "not_applicable": [
                            "business_negative_fact_confirmed",
                            "legal_not_applicable_confirmed",
                        ],
                        "rejected": ["legal_rejected"],
                        "unanswerable": ["legal_unanswerable"],
                        "uncovered": ["legal_research_incomplete"],
                    }[disposition]
                )
            )
            negative_fact_refs = list(decision.get("negative_fact_refs") or [])
            missing_facts = (
                [] if disposition == "not_applicable" else list(negative_fact_refs)
            )
        elif claim is None:
            disposition = "uncovered"
            research_status = "research_open"
            reason_codes = ["legal_claim_draft_missing"]
            missing_facts = []
            negative_fact_refs = []
        elif claim["status"] == "refused":
            disposition = "unanswerable"
            research_status = "research_open"
            reason_codes = list(claim["reason_codes"])
            missing_facts = sorted(
                reason
                for reason in reason_codes
                if reason.startswith("fact_")
            )
            negative_fact_refs = []
        else:
            disposition = "uncovered"
            research_status = "claim_pending"
            reason_codes = ["claim_confirmation_pending"]
            missing_facts = []
            negative_fact_refs = []
        values.append(
            {
                "checklist_code": code,
                "denominator_order": int(item["denominator_order"]),
                "title": str(item["title"]),
                "dimension": str(item["dimension"]),
                "scope_status": scope_status,
                "screening_status": str(item["screening_status"]),
                "disposition": disposition,
                "research_status": research_status,
                "missing_facts": missing_facts,
                "reason_codes": reason_codes,
                "negative_fact_refs": negative_fact_refs,
                "compiler_version": VERSION,
                "item_hash": hash_payload(item),
                "legal_confirmation_note": (
                    str(decision["confirmation_note"]) if decision else None
                ),
            }
        )
    return values


def build_output_payload(
    *,
    claim_values: list[dict[str, Any]],
    research_values: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "claims": copy.deepcopy(claim_values),
        "research_items": copy.deepcopy(research_values),
    }
