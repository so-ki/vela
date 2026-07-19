"""CoverageProof 0.2 -- fixed 30-item Pack denominator dispositions."""

from __future__ import annotations

from typing import Any

from app.services.versioned.canonical_hash import canonical_hash_v1


VERSION = "0.2"
PACK_TOTAL = 30
DISPOSITIONS = (
    "supported",
    "not_applicable",
    "rejected",
    "unanswerable",
    "uncovered",
)


def hash_payload(payload: Any) -> str:
    return canonical_hash_v1(payload)


def build_proof_body(
    *,
    scenario_id: int,
    compilation: Any,
    claims: list[Any],
    research_items: list[Any],
    denominator_ref: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered = sorted(research_items, key=lambda value: value.denominator_order)
    if len(ordered) != PACK_TOTAL:
        raise ValueError("CoverageProof 0.2 分母必须精确为 30")
    codes = [item.checklist_code for item in ordered]
    if len(set(codes)) != PACK_TOTAL:
        raise ValueError("CoverageProof 0.2 分母 code 必须唯一")

    claim_by_id = {claim.id: claim for claim in claims}
    denominator: list[dict[str, Any]] = []
    for item in ordered:
        disposition = item.disposition
        if item.scope_status == "out_of_scope_by_scope":
            if disposition is not None:
                raise ValueError("out_of_scope_by_scope 项不得带 disposition")
        elif disposition not in DISPOSITIONS:
            raise ValueError("in_scope 项必须带已知 disposition")
        if disposition == "supported":
            claim = claim_by_id.get(item.linked_claim_id)
            if claim is None or claim.status != "supported":
                raise ValueError("supported disposition 必须绑定已确认 Claim")
        denominator.append(
            {
                "checklist_code": item.checklist_code,
                "statement": item.title,
                "dimension": item.dimension,
                "scope_status": item.scope_status,
                "screening_status": item.screening_status,
                "disposition": disposition,
                "linked_claim_id": item.linked_claim_id,
                "reason_codes": list(item.reason_codes or []),
                "item_hash": item.item_hash,
            }
        )

    in_scope = [
        item for item in denominator if item["scope_status"] == "in_scope"
    ]
    out_of_scope = [
        item
        for item in denominator
        if item["scope_status"] == "out_of_scope_by_scope"
    ]
    disposition_counts = {
        disposition: sum(item["disposition"] == disposition for item in in_scope)
        for disposition in DISPOSITIONS
    }
    scope_total = len(in_scope)
    if (
        PACK_TOTAL != scope_total + len(out_of_scope)
        or scope_total != sum(disposition_counts.values())
    ):
        raise ValueError("CoverageProof 0.2 分母计数不守恒")

    covered = sorted(
        item["checklist_code"]
        for item in in_scope
        if item["disposition"] == "supported"
    )
    uncovered = sorted(
        (
            {
                "checklist_code": item["checklist_code"],
                "status": item["disposition"],
                "unanswerable_reasons": list(item["reason_codes"]),
            }
            for item in in_scope
            if item["disposition"] != "supported"
        ),
        key=lambda value: value["checklist_code"],
    )
    proof_body = {
        "schema_version": VERSION,
        "scenario_id": scenario_id,
        "compilation_id": compilation.id,
        "compiler_input_hash": compilation.input_hash,
        "compiler_output_hash": compilation.output_hash,
        "denominator_ref": denominator_ref.strip(),
        "denominator": denominator,
        "pack_total": PACK_TOTAL,
        "scope_total": scope_total,
        "out_of_scope_by_scope_count": len(out_of_scope),
        "supported_count": disposition_counts["supported"],
        "not_applicable_count": disposition_counts["not_applicable"],
        "rejected_count": disposition_counts["rejected"],
        "unanswerable_count": disposition_counts["unanswerable"],
        "uncovered_count": disposition_counts["uncovered"],
        "covered_checklist_codes": covered,
        "uncovered": uncovered,
        "out_of_scope_by_scope": [
            item["checklist_code"] for item in out_of_scope
        ],
        "answerability_rule": (
            "Pack 分母固定为 30；Scope 仅标记 in/out；"
            "supported 仅计入经法务人工确认且绑定的 Claim。"
        ),
    }
    return denominator, proof_body


def validate_body_structure(body: dict[str, Any]) -> bool:
    required_counts = (
        "pack_total",
        "scope_total",
        "out_of_scope_by_scope_count",
        "supported_count",
        "not_applicable_count",
        "rejected_count",
        "unanswerable_count",
        "uncovered_count",
    )
    if any(not isinstance(body.get(key), int) for key in required_counts):
        return False
    denominator = body.get("denominator")
    if not isinstance(denominator, list) or len(denominator) != PACK_TOTAL:
        return False
    codes: list[str] = []
    for item in denominator:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("checklist_code"), str):
            return False
        if not isinstance(item.get("statement"), str):
            return False
        if item.get("scope_status") not in {"in_scope", "out_of_scope_by_scope"}:
            return False
        if item.get("scope_status") == "in_scope":
            if item.get("disposition") not in DISPOSITIONS:
                return False
        elif item.get("disposition") is not None:
            return False
        if not isinstance(item.get("reason_codes"), list) or any(
            not isinstance(reason, str) for reason in item["reason_codes"]
        ):
            return False
        codes.append(item["checklist_code"])
    if len(set(codes)) != PACK_TOTAL:
        return False
    if not isinstance(body.get("out_of_scope_by_scope"), list) or any(
        not isinstance(code, str) for code in body["out_of_scope_by_scope"]
    ):
        return False
    return (
        body["pack_total"] == PACK_TOTAL
        and body["pack_total"]
        == body["scope_total"] + body["out_of_scope_by_scope_count"]
        and body["scope_total"]
        == body["supported_count"]
        + body["not_applicable_count"]
        + body["rejected_count"]
        + body["unanswerable_count"]
        + body["uncovered_count"]
    )


def stored_counts(body: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(body["pack_total"]),
        int(body["supported_count"]),
        int(
            body["not_applicable_count"]
            + body["rejected_count"]
            + body["unanswerable_count"]
            + body["uncovered_count"]
        ),
        int(body["unanswerable_count"]),
    )
