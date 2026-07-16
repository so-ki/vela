from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationScenario(Base):
    __tablename__ = "investigation_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(64), default="brazil", nullable=False)
    rules_pack_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scenario_scope: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    scope_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    active_generation_attempt_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    industry: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    investment_structure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    investment_destination: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    project_content_scale: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    funding_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    known_risks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    employee_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    capacity_notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    facility_notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    compliance_dimensions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    board_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    production_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="checklist_generated", nullable=False)
    business_archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    checklist: Mapped[Optional["ComplianceChecklist"]] = relationship(
        back_populates="scenario", uselist=False, cascade="all, delete-orphan"
    )


class ScenarioGenerationAttempt(Base):
    __tablename__ = "scenario_generation_attempts"
    __table_args__ = (UniqueConstraint("scenario_id", "sequence", name="uq_generation_attempt_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("investigation_scenarios.id"), index=True, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    generation_input_id: Mapped[str] = mapped_column(
        ForeignKey("scenario_generation_inputs.id"), index=True, nullable=False
    )
    generation_input_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    lease_acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ScenarioGenerationInput(Base):
    """Immutable, replayable material/context record used by one frozen snapshot."""

    __tablename__ = "scenario_generation_inputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("investigation_scenarios.id"), index=True, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ComplianceChecklist(Base):
    __tablename__ = "compliance_checklists"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_scenarios.id"), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[str] = mapped_column(String(16), default="v0.1", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    scenario: Mapped[InvestigationScenario] = relationship(back_populates="checklist")
