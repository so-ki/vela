from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
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
