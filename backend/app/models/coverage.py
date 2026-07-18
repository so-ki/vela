from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.user import utcnow


class CoverageTask(Base):
    """覆盖任务：一条"该查而尚未闭环"的工作单。

    status=enumerated_absent（目录穷举后未见）只允许在 denominator_source
    非空时设置——没有官方分母的来源不得宣称穷举。
    """

    __tablename__ = "coverage_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("investigation_scenarios.id"), index=True, nullable=False)
    dimension: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    element_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    checklist_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)   # material_gap / retrieval_gap / element_gap
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)  # CoverageTaskStatus
    origin: Mapped[str] = mapped_column(String(32), nullable=False)  # gate_a / adequacy / zero_hit / red_team
    denominator_source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CoverageProof(Base):
    """覆盖证明：分母来自 manifest 声明的官方来源，
    不允许用"检索到多少算多少"当分母。"""

    __tablename__ = "coverage_proofs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("investigation_scenarios.id"), index=True, nullable=False)
    denominator_source: Mapped[str] = mapped_column(String(128), nullable=False)
    denominator_count: Mapped[int] = mapped_column(Integer, nullable=False)
    covered_count: Mapped[int] = mapped_column(Integer, nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {claim_ids, fact_ids, task_ids, corpus_version}
    proof_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
