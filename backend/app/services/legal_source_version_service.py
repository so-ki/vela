from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.roles import is_legal_role
from app.models.legal_source_version import LegalChangeEvent, LegalSourceVersion
from app.models.user import User
from app.schemas.legal_source_version import (
    LegalSourceCandidateCreateRequest,
    LegalSourceDecisionRequest,
)


class SourceVersionConflict(ValueError):
    pass


class SourceVersionValidationError(ValueError):
    pass


class SourceVersionPermissionError(PermissionError):
    pass


_ALLOWED_TRANSITIONS = {
    "candidate": {"reviewed", "rejected"},
    "reviewed": {"active", "rejected"},
    "active": set(),
    "rejected": set(),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_legal(user: User) -> None:
    if not is_legal_role(user):
        raise SourceVersionPermissionError("法规来源版本的写操作必须由法务人工执行")


def _article_records(request: LegalSourceCandidateCreateRequest) -> list[dict]:
    records: list[dict] = []
    for article in request.articles:
        item = article.model_dump(mode="json")
        item["article_id"] = article.article_id.strip()
        item["content_hash"] = _sha256(article.normalized_text)
        records.append(item)
    return sorted(records, key=lambda item: item["article_id"])


def _relation_diff(previous: list[dict], current: list[dict]) -> dict:
    before = {_stable_json(item): item for item in previous}
    after = {_stable_json(item): item for item in current}
    return {
        "added": [after[key] for key in sorted(set(after) - set(before))],
        "removed": [before[key] for key in sorted(set(before) - set(after))],
    }


def _article_diff(previous: list[dict], current: list[dict]) -> list[dict]:
    before = {item["article_id"]: item for item in previous}
    after = {item["article_id"]: item for item in current}
    changes: list[dict] = []
    for article_id in sorted(set(before) | set(after)):
        old = before.get(article_id)
        new = after.get(article_id)
        if old is None:
            changes.append(
                {
                    "article_id": article_id,
                    "change_type": "added",
                    "previous_hash": None,
                    "current_hash": new["content_hash"],
                    "relation_changes": _relation_diff([], new.get("relations") or []),
                }
            )
        elif new is None:
            changes.append(
                {
                    "article_id": article_id,
                    "change_type": "removed",
                    "previous_hash": old["content_hash"],
                    "current_hash": None,
                    "relation_changes": _relation_diff(old.get("relations") or [], []),
                }
            )
        elif old["content_hash"] != new["content_hash"] or _stable_json(
            old.get("relations") or []
        ) != _stable_json(new.get("relations") or []):
            changes.append(
                {
                    "article_id": article_id,
                    "change_type": "modified",
                    "previous_hash": old["content_hash"],
                    "current_hash": new["content_hash"],
                    "relation_changes": _relation_diff(
                        old.get("relations") or [], new.get("relations") or []
                    ),
                }
            )
    return changes


def create_source_candidate(
    db: Session,
    *,
    request: LegalSourceCandidateCreateRequest,
    user: User,
) -> tuple[LegalSourceVersion, LegalChangeEvent]:
    """Persist a capture and diff without publishing any capability-pack data."""

    _require_legal(user)
    raw_hash = _sha256(request.raw_content)
    normalized_hash = _sha256(request.normalized_content)
    duplicate = (
        db.query(LegalSourceVersion.id)
        .filter(
            LegalSourceVersion.canonical_id == request.canonical_id.strip(),
            LegalSourceVersion.raw_hash == raw_hash,
            LegalSourceVersion.normalized_hash == normalized_hash,
        )
        .first()
    )
    if duplicate is not None:
        raise SourceVersionConflict("相同 canonical_id 与内容哈希的不可变版本已存在")

    previous: Optional[LegalSourceVersion] = None
    if request.previous_version_id:
        previous = db.get(LegalSourceVersion, request.previous_version_id)
        if previous is None:
            raise SourceVersionValidationError("previous_version_id 不存在")
        if previous.canonical_id != request.canonical_id.strip():
            raise SourceVersionValidationError("前后版本的 canonical_id 必须一致")
        if request.urn and previous.urn and previous.urn != request.urn.strip():
            raise SourceVersionValidationError("前后版本的 URN 不一致")
        if _as_utc(request.fetched_at) <= _as_utc(previous.fetched_at):
            raise SourceVersionValidationError("新版本 fetched_at 必须晚于前一版本")
        if previous.raw_hash == raw_hash and previous.normalized_hash == normalized_hash:
            raise SourceVersionValidationError("未发现内容哈希变化，不得创建变化候选")

    now = _now()
    relations = [item.model_dump(mode="json") for item in request.relations]
    articles = _article_records(request)
    version = LegalSourceVersion(
        id=str(uuid4()),
        canonical_id=request.canonical_id.strip(),
        citation_id=request.citation_id.strip(),
        urn=request.urn.strip() if request.urn else None,
        source_authority=request.source_authority.strip(),
        official_domain=request.official_domain,
        official_source_basis=request.official_source_basis.strip(),
        source_url=request.source_url,
        fetched_at=request.fetched_at,
        etag=request.etag,
        last_modified=request.last_modified,
        raw_content=request.raw_content,
        normalized_content=request.normalized_content,
        raw_hash=raw_hash,
        normalized_hash=normalized_hash,
        parser_version=request.parser_version.strip(),
        valid_from=request.valid_from,
        valid_to=request.valid_to,
        status="candidate",
        relations=relations,
        article_snapshots=articles,
        previous_version_id=previous.id if previous else None,
        decision_history=[],
        created_by=user.id,
        created_at=now,
    )
    previous_articles = list(previous.article_snapshots or []) if previous else []
    previous_relations = list(previous.relations or []) if previous else []
    article_diff = _article_diff(previous_articles, articles)
    if previous is None:
        change_type = "initial"
    elif previous.normalized_hash != normalized_hash:
        change_type = "content_changed"
    else:
        change_type = "format_only"
    change_event = LegalChangeEvent(
        id=str(uuid4()),
        source_version_id=version.id,
        previous_version_id=previous.id if previous else None,
        canonical_id=version.canonical_id,
        change_type=change_type,
        article_diff=article_diff,
        relation_diff=_relation_diff(previous_relations, relations),
        raw_hash_before=previous.raw_hash if previous else None,
        raw_hash_after=raw_hash,
        normalized_hash_before=previous.normalized_hash if previous else None,
        normalized_hash_after=normalized_hash,
        detected_at=request.fetched_at,
        created_by=user.id,
        created_at=now,
    )
    db.add_all([version, change_event])
    db.flush()
    return version, change_event


def decide_source_version(
    db: Session,
    *,
    version: LegalSourceVersion,
    request: LegalSourceDecisionRequest,
    user: User,
) -> LegalSourceVersion:
    _require_legal(user)
    allowed = _ALLOWED_TRANSITIONS.get(version.status, set())
    if request.decision not in allowed:
        raise SourceVersionValidationError(
            f"法规版本状态不得从 {version.status} 直接变更为 {request.decision}"
        )
    now = _now()
    history = list(version.decision_history or [])
    history.append(
        {
            "from": version.status,
            "to": request.decision,
            "by": user.id,
            "at": now.isoformat(),
            "note": request.note.strip(),
            "release_scope": "source_registry_only",
            "capability_pack_corpus_updated": False,
        }
    )
    values = {
        "status": request.decision,
        "decision_history": history,
        "decision_note": request.note.strip(),
    }
    if request.decision == "reviewed":
        values.update({"reviewed_by": user.id, "reviewed_at": now})
    elif request.decision == "active":
        values.update({"activated_by": user.id, "activated_at": now})
    else:
        values.update({"rejected_by": user.id, "rejected_at": now})
    result = db.execute(
        update(LegalSourceVersion)
        .where(
            LegalSourceVersion.id == version.id,
            LegalSourceVersion.status == version.status,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.expire_all()
        raise SourceVersionConflict("法规版本状态已被其他会话更新，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(LegalSourceVersion, version.id)


def list_source_versions(
    db: Session,
    *,
    canonical_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[LegalSourceVersion]:
    query = db.query(LegalSourceVersion)
    if canonical_id:
        query = query.filter(LegalSourceVersion.canonical_id == canonical_id.strip())
    if status:
        query = query.filter(LegalSourceVersion.status == status)
    return query.order_by(LegalSourceVersion.fetched_at.desc()).limit(limit).all()


def list_change_events(
    db: Session,
    *,
    canonical_id: Optional[str] = None,
    limit: int = 100,
) -> list[LegalChangeEvent]:
    query = db.query(LegalChangeEvent)
    if canonical_id:
        query = query.filter(LegalChangeEvent.canonical_id == canonical_id.strip())
    return query.order_by(LegalChangeEvent.detected_at.desc()).limit(limit).all()
