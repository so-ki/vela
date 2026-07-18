"""事实五元组服务：主体＋属性＋值＋时间＋出处。

结论只能建立在有出处的事实上。没有出处（source_block_id 为空）
的事实会被记录，但 verification_status 不得为 verified。

法域中立：本模块不得出现任何具体法域/语言内容。
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.fact import FactRecord


def record_facts_from_extract(
    db: Session,
    *,
    scenario_id: int,
    subject: str,
    extract_snapshot: dict[str, Any],
    block_by_name: Optional[dict[str, int]] = None,
    pack_version: Optional[str] = None,
) -> list[FactRecord]:
    """把抽取快照的 facts 数组落为 FactRecord。

    同一 scenario+attribute 的旧事实标记为被新事实取代（superseded_by_id）。
    """
    block_by_name = block_by_name or {}
    default_block = block_by_name.get("__extract__")
    records: list[FactRecord] = []
    for fact in extract_snapshot.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        attribute = str(fact.get("field") or "").strip()
        value = str(fact.get("value") or "").strip()
        if not attribute or not value:
            continue
        source_block_id = block_by_name.get(str(fact.get("source_filename") or "")) or default_block
        status = str(fact.get("verification_status") or "unverified")
        if source_block_id is None and status == "verified":
            status = "unverified"  # 无出处不得为 verified
        record = FactRecord(
            scenario_id=scenario_id,
            subject=subject,
            attribute=attribute,
            value=value,
            source_block_id=source_block_id,
            source_snippet=fact.get("source_snippet"),
            grounding_score=fact.get("grounding_score"),
            verification_status=status,
            extraction_method=str(fact.get("extraction_method") or "rules"),
            fact_pack_version=pack_version,
        )
        db.add(record)
        records.append(record)
    db.flush()

    for record in records:
        stale = (
            db.query(FactRecord)
            .filter(
                FactRecord.scenario_id == scenario_id,
                FactRecord.attribute == record.attribute,
                FactRecord.id != record.id,
                FactRecord.superseded_by_id.is_(None),
            )
            .all()
        )
        for old in stale:
            if old.id < record.id:
                old.superseded_by_id = record.id
    db.flush()
    return records


def active_facts(db: Session, scenario_id: int) -> list[FactRecord]:
    return (
        db.query(FactRecord)
        .filter(FactRecord.scenario_id == scenario_id, FactRecord.superseded_by_id.is_(None))
        .order_by(FactRecord.id)
        .all()
    )


def facts_projection(db: Session, scenario_id: int) -> list[dict[str, Any]]:
    return [
        {
            "fact_id": f.id,
            "subject": f.subject,
            "attribute": f.attribute,
            "value": f.value,
            "asserted_at": f.asserted_at.isoformat() if f.asserted_at else None,
            "source_block_id": f.source_block_id,
            "verification_status": f.verification_status,
            "business_confirmation": f.business_confirmation,
        }
        for f in active_facts(db, scenario_id)
    ]
