from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LegalSourceVersion(Base):
    """Immutable official-source capture with a human-controlled review lifecycle.

    ``active`` means approved in this source-version registry only.  This model
    deliberately has no relationship to, or write path into, a capability-pack
    corpus artifact.
    """

    __tablename__ = "legal_source_versions"
    __table_args__ = (
        UniqueConstraint(
            "canonical_id",
            "raw_hash",
            "normalized_hash",
            name="uq_legal_source_version_content",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_id: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    citation_id: Mapped[str] = mapped_column(String(1024), index=True, nullable=False)
    urn: Mapped[Optional[str]] = mapped_column(String(1024), index=True, nullable=True)
    source_authority: Mapped[str] = mapped_column(String(512), nullable=False)
    official_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    official_source_basis: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    etag: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    last_modified: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    normalized_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    relations: Mapped[list] = mapped_column(JSON, nullable=False)
    article_snapshots: Mapped[list] = mapped_column(JSON, nullable=False)
    previous_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("legal_source_versions.id"), index=True, nullable=True
    )
    decision_history: Mapped[list] = mapped_column(JSON, nullable=False)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LegalChangeEvent(Base):
    """Immutable structured diff emitted for exactly one captured source version."""

    __tablename__ = "legal_change_events"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id", name="uq_legal_change_event_source_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("legal_source_versions.id"), index=True, nullable=False
    )
    previous_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("legal_source_versions.id"), index=True, nullable=True
    )
    canonical_id: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    article_diff: Mapped[list] = mapped_column(JSON, nullable=False)
    relation_diff: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_hash_before: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_hash_after: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_hash_before: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    normalized_hash_after: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


_VERSION_IMMUTABLE_FIELDS = {
    "canonical_id",
    "citation_id",
    "urn",
    "source_authority",
    "official_domain",
    "official_source_basis",
    "source_url",
    "fetched_at",
    "etag",
    "last_modified",
    "raw_content",
    "normalized_content",
    "raw_hash",
    "normalized_hash",
    "parser_version",
    "valid_from",
    "valid_to",
    "relations",
    "article_snapshots",
    "previous_version_id",
    "created_by",
    "created_at",
}


@event.listens_for(LegalSourceVersion, "before_update")
def prevent_source_capture_mutation(_mapper, _connection, target: LegalSourceVersion) -> None:
    state = inspect(target)
    changed = sorted(
        field for field in _VERSION_IMMUTABLE_FIELDS if state.attrs[field].history.has_changes()
    )
    if changed:
        raise ValueError(f"法规来源版本为不可变记录，不得修改: {', '.join(changed)}")


@event.listens_for(LegalChangeEvent, "before_update")
def prevent_change_event_mutation(_mapper, _connection, target: LegalChangeEvent) -> None:
    state = inspect(target)
    changed = sorted(
        attr.key
        for attr in state.mapper.column_attrs
        if attr.key != "id" and state.attrs[attr.key].history.has_changes()
    )
    if changed:
        raise ValueError(f"法规变化事件为不可变记录，不得修改: {', '.join(changed)}")
