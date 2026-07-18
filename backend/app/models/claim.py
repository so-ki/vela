from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.user import utcnow


class Claim(Base):
    """简报结论的编译产物：每条对外结论必须编译为一条 Claim，
    verdict 由证据链决定，无证据的结论只能是 blocked 或 unanswerable。"""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("investigation_scenarios.id"), index=True, nullable=False)
    checklist_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    statement_primary: Mapped[str] = mapped_column(Text, nullable=False)          # 主语言结论文本
    statement_secondary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 次语言结论文本
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)              # ClaimVerdict
    verdict_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gate_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)    # 编译时的门控快照
    compiled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    evidences: Mapped[list["ClaimEvidence"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ClaimEvidence.id"
    )


class ClaimEvidence(Base):
    """Claim 的证据条目：事实（FactRecord）或法源命中（hit_ref）。"""

    __tablename__ = "claim_evidences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # fact / legal_hit / rule_finding
    fact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fact_records.id"), nullable=True)
    hit_ref: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {citation_id, url, source, content_hash}
    grounding_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    citation_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    claim: Mapped[Claim] = relationship(back_populates="evidences")
