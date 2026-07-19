from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MaterialLedgerEntry(Base):
    """One source block's review state, separate from extracted legal content."""

    __tablename__ = "material_ledger_entries"
    __table_args__ = (
        UniqueConstraint("scenario_id", "block_id", name="uq_material_ledger_scenario_block"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    block_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_document: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    state_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extraction_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    state_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CoverageTask(Base):
    """Coverage work is allowed only against an identified official denominator."""

    __tablename__ = "coverage_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    denominator_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    denominator_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    denominator_items: Mapped[list] = mapped_column(JSON, nullable=False)
    covered_items: Mapped[list] = mapped_column(JSON, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class FactRecord(Base):
    """An immutable business fact with the required provenance tuple.

    Extracted document text is deliberately not a fact record: it becomes
    usable by the Claim Compiler only after the scenario owner has supplied
    and confirmed this record.
    """

    __tablename__ = "fact_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    attribute: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    fact_time: Mapped[str] = mapped_column(String(128), nullable=False)
    block_id: Mapped[str] = mapped_column(String(255), nullable=False)
    fact_pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_document: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    assertion_polarity: Mapped[str] = mapped_column(
        String(16), default="unspecified", nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    confirmation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_confirmed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    business_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClaimCompilation(Base):
    """Immutable compiler run over a checklist/fact/evidence snapshot."""

    __tablename__ = "claim_compilations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    compiler_version: Mapped[str] = mapped_column(String(16), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    denominator_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False)
    refused_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClaimRecord(Base):
    """A claim never becomes supported without an explicit legal confirmation."""

    __tablename__ = "claim_records"
    __table_args__ = (
        UniqueConstraint("compilation_id", "checklist_code", name="uq_claim_compilation_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    compilation_id: Mapped[str] = mapped_column(
        ForeignKey("claim_compilations.id"), index=True, nullable=False
    )
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    checklist_code: Mapped[str] = mapped_column(String(128), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    fact_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    confirmed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ResearchItem(Base):
    """One immutable Pack-denominator item with an independently reviewable disposition."""

    __tablename__ = "research_items"
    __table_args__ = (
        UniqueConstraint(
            "compilation_id",
            "checklist_code",
            name="uq_research_item_compilation_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    compilation_id: Mapped[str] = mapped_column(
        ForeignKey("claim_compilations.id"), index=True, nullable=False
    )
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    checklist_code: Mapped[str] = mapped_column(String(128), nullable=False)
    denominator_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    scope_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    screening_status: Mapped[str] = mapped_column(String(32), nullable=False)
    disposition: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    research_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    missing_facts: Mapped[list] = mapped_column(JSON, nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    negative_fact_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    linked_claim_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("claim_records.id"), index=True, nullable=True
    )
    compiler_version: Mapped[str] = mapped_column(String(16), nullable=False)
    item_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_confirmed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    legal_confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    legal_confirmation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CoverageProof(Base):
    """Immutable denominator-based proof produced from one compilation snapshot."""

    __tablename__ = "coverage_proofs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), index=True, nullable=False
    )
    compilation_id: Mapped[str] = mapped_column(
        ForeignKey("claim_compilations.id"), index=True, nullable=False
    )
    denominator_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    denominator_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    denominator_count: Mapped[int] = mapped_column(Integer, nullable=False)
    covered_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uncovered_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unanswerable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    proof: Mapped[dict] = mapped_column(JSON, nullable=False)
    proof_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
