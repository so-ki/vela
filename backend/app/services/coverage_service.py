"""覆盖任务与覆盖证明：回答"该查的都查了吗，凭什么这么说"。

分母纪律：CoverageProof 的分母必须来自能力包 manifest 声明的
官方分母来源；"检索到多少算多少"不构成分母。
"目录穷举后未见"（enumerated_absent）只允许用于声明了分母的来源。

法域中立：本模块不得出现任何具体法域/语言内容。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.statuses import CoverageTaskStatus
from app.models.coverage import CoverageProof, CoverageTask


class DenominatorRequiredError(Exception):
    """没有官方分母的来源不得宣称穷举。"""


def upsert_task(
    db: Session,
    *,
    scenario_id: int,
    kind: str,
    origin: str,
    dimension: Optional[str] = None,
    element_id: Optional[str] = None,
    checklist_code: Optional[str] = None,
    status: CoverageTaskStatus = CoverageTaskStatus.OPEN,
    denominator_source: Optional[str] = None,
    note: Optional[str] = None,
) -> CoverageTask:
    if status == CoverageTaskStatus.ENUMERATED_ABSENT and not denominator_source:
        raise DenominatorRequiredError(
            "enumerated_absent requires an official denominator_source declared by the pack"
        )
    existing = (
        db.query(CoverageTask)
        .filter(
            CoverageTask.scenario_id == scenario_id,
            CoverageTask.kind == kind,
            CoverageTask.dimension == dimension,
            CoverageTask.element_id == element_id,
            CoverageTask.checklist_code == checklist_code,
        )
        .first()
    )
    if existing:
        existing.status = status.value
        existing.origin = origin
        existing.denominator_source = denominator_source
        existing.note = note
        db.flush()
        return existing
    task = CoverageTask(
        scenario_id=scenario_id,
        kind=kind,
        origin=origin,
        dimension=dimension,
        element_id=element_id,
        checklist_code=checklist_code,
        status=status.value,
        denominator_source=denominator_source,
        note=note,
    )
    db.add(task)
    db.flush()
    return task


def sync_tasks_from_payload(db: Session, scenario_id: int, payload: dict[str, Any]) -> int:
    """从充分性评估与简报派生覆盖任务。返回任务总数。"""
    count = 0
    adequacy = payload.get("investigation_adequacy") or {}
    for dim in adequacy.get("dimensions") or []:
        dim_id = dim.get("dimension_id") or dim.get("id")
        for element in dim.get("elements") or []:
            status_raw = str(element.get("status") or "")
            if status_raw in ("missing", "at_risk"):
                upsert_task(
                    db,
                    scenario_id=scenario_id,
                    kind="material_gap" if status_raw == "missing" else "element_gap",
                    origin="adequacy",
                    dimension=str(dim_id) if dim_id else None,
                    element_id=str(element.get("id") or "") or None,
                    status=CoverageTaskStatus.OPEN,
                    note=element.get("note"),
                )
                count += 1
            elif status_raw == "covered" and element.get("id"):
                upsert_task(
                    db,
                    scenario_id=scenario_id,
                    kind="element_gap",
                    origin="adequacy",
                    dimension=str(dim_id) if dim_id else None,
                    element_id=str(element.get("id")),
                    status=CoverageTaskStatus.SATISFIED,
                )
                count += 1

    brief = payload.get("brief") or {}
    for section in brief.get("sections") or []:
        for item in section.get("items") or []:
            if not item.get("citations"):
                upsert_task(
                    db,
                    scenario_id=scenario_id,
                    kind="retrieval_gap",
                    origin="zero_hit",
                    checklist_code=str(item.get("code") or "") or None,
                    status=CoverageTaskStatus.OPEN,
                    note=item.get("block_reason"),
                )
                count += 1
    return count


def build_proof(
    db: Session,
    *,
    scenario_id: int,
    denominator_source: str,
    denominator_count: int,
    covered_count: int,
    evidence: Optional[dict[str, Any]] = None,
) -> CoverageProof:
    """生成一条覆盖证明（append-only：历史证明不删除）。"""
    open_count = (
        db.query(CoverageTask)
        .filter(
            CoverageTask.scenario_id == scenario_id,
            CoverageTask.status == CoverageTaskStatus.OPEN.value,
        )
        .count()
    )
    body = {
        "scenario_id": scenario_id,
        "denominator_source": denominator_source,
        "denominator_count": denominator_count,
        "covered_count": covered_count,
        "open_count": open_count,
        "evidence": evidence or {},
    }
    proof = CoverageProof(
        scenario_id=scenario_id,
        denominator_source=denominator_source,
        denominator_count=denominator_count,
        covered_count=covered_count,
        open_count=open_count,
        evidence=evidence,
        proof_hash=hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    )
    db.add(proof)
    db.flush()
    return proof


def build_scenario_proof(
    db: Session,
    scenario_id: int,
    payload: dict[str, Any],
    *,
    claim_projections: Optional[list[dict[str, Any]]] = None,
) -> Optional[CoverageProof]:
    """场景级覆盖证明：分母 = 所选维度下能力包声明的全部要件。

    没有充分性评估（即没有包声明的要件全集）时不生成证明——
    宁可没有证明，也不用检索结果自证分母。
    """
    adequacy = payload.get("investigation_adequacy") or {}
    dimensions = adequacy.get("dimensions") or []
    if not dimensions:
        return None
    denominator = 0
    covered = 0
    for dim in dimensions:
        for element in dim.get("elements") or []:
            denominator += 1
            if str(element.get("status") or "") == "covered":
                covered += 1
    if denominator == 0:
        return None
    return build_proof(
        db,
        scenario_id=scenario_id,
        denominator_source="pack_dimension_elements",
        denominator_count=denominator,
        covered_count=covered,
        evidence={
            "claim_ids": [p["claim_id"] for p in (claim_projections or [])],
            "grounding_rate": (payload.get("grounding_report") or {}).get("grounding_rate"),
        },
    )


def coverage_projection(db: Session, scenario_id: int) -> dict[str, Any]:
    tasks = (
        db.query(CoverageTask)
        .filter(CoverageTask.scenario_id == scenario_id)
        .order_by(CoverageTask.id)
        .all()
    )
    latest_proof = (
        db.query(CoverageProof)
        .filter(CoverageProof.scenario_id == scenario_id)
        .order_by(CoverageProof.id.desc())
        .first()
    )
    return {
        "tasks": [
            {
                "task_id": t.id,
                "kind": t.kind,
                "origin": t.origin,
                "dimension": t.dimension,
                "element_id": t.element_id,
                "checklist_code": t.checklist_code,
                "status": t.status,
            }
            for t in tasks
        ],
        "open_count": sum(1 for t in tasks if t.status == CoverageTaskStatus.OPEN.value),
        "proof": (
            {
                "proof_id": latest_proof.id,
                "denominator_source": latest_proof.denominator_source,
                "denominator_count": latest_proof.denominator_count,
                "covered_count": latest_proof.covered_count,
                "open_count": latest_proof.open_count,
                "proof_hash": latest_proof.proof_hash,
                "generated_at": latest_proof.generated_at.isoformat() if latest_proof.generated_at else None,
            }
            if latest_proof
            else None
        ),
    }
