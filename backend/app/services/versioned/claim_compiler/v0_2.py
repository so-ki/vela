"""Claim compiler 0.2 — HASH-FROZEN reader/writer. DO NOT EDIT.

Byte-semantic copy of the compiler builders as they existed at commit efc76e0
(mechanism_service.py), characterized by tests/goldens/versioned/
compiler_v0_2.json. Every dict key, string literal (including the
"待核验事项：" placeholder prefix, status values and reason codes), the fact
query ordering and the ref formats are hash-load-bearing: changing any of them
breaks every stored ClaimCompilation input/output hash. Behavior changes must
be added as a new version module, never by editing this one.

This module must not import mechanism_service or answerability_gate_service.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.models.mechanism import FactRecord
from app.models.scenario import InvestigationScenario
from app.services.versioned.canonical_hash import canonical_hash_v1

VERSION = "0.2"


def hash_payload(payload: Any) -> str:
    return canonical_hash_v1(payload)


def checklist_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sections = payload.get("sections_with_legal") or payload.get("sections") or []
    by_code: dict[str, dict[str, Any]] = {}
    for section in sections:
        for item in section.get("items") or []:
            code = str(item.get("code") or "").strip()
            if code and code not in by_code:
                by_code[code] = copy.deepcopy(item)
    return list(by_code.values())


def _list_fact_records(db: Session, scenario_id: int) -> list[FactRecord]:
    # Frozen private copy: the iteration order below is snapshot-semantic.
    return (
        db.query(FactRecord)
        .filter(FactRecord.scenario_id == scenario_id)
        .order_by(FactRecord.created_at.asc(), FactRecord.id.asc())
        .all()
    )


def fact_inventory(db: Session, scenario_id: int) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for fact in _list_fact_records(db, scenario_id):
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


def evidence_inventory(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
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
                "source_hash": canonical_hash_v1(hit),
                "eligible": grounded,
            }
    return inventory


def checklist_inventory(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "item_hash": canonical_hash_v1(item_without_hits),
            }
        )
    return inventory


def brief_conclusion_inventory(payload: dict[str, Any]) -> list[dict[str, Any]]:
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
                inventory.append({**body, "conclusion_hash": canonical_hash_v1(body)})
    return inventory


def build_input_snapshot(
    db: Session,
    *,
    scenario: InvestigationScenario,
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = scenario.checklist.payload if scenario.checklist else {}
    items = checklist_items(payload)
    return {
        "scenario_id": scenario.id,
        "checklist": checklist_inventory(items),
        "brief_conclusions": brief_conclusion_inventory(payload),
        "facts": fact_inventory(db, scenario.id),
        "evidence": evidence_inventory(items),
        "drafts": copy.deepcopy(drafts),
    }


def claim_reasons(
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
        code = str(item["code"])
        draft = draft_by_code.get(code)
        fact_refs = list(draft.get("fact_refs") or []) if draft else []
        evidence_refs = list(draft.get("evidence_refs") or []) if draft else []
        reasons = claim_reasons(fact_refs, evidence_refs, facts, evidence, code)
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
