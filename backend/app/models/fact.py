from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow


class FactRecord(Base):
    """事实五元组：主体 + 属性 + 值 + 时间 + 出处（材料块）。

    结论只能建立在有出处的事实上；没有 source_block_id 的事实
    不得支撑 Claim（见 claim_compiler）。
    """

    __tablename__ = "fact_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("investigation_scenarios.id"), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)      # 事实主体（默认=项目主体）
    attribute: Mapped[str] = mapped_column(String(255), index=True, nullable=False)  # 属性（字段 key）
    value: Mapped[str] = mapped_column(Text, nullable=False)               # 值
    asserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)  # 时间
    source_block_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material_blocks.id"), nullable=True)  # 出处
    source_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grounding_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(32), default="rules", nullable=False)  # rules / llm
    business_confirmation: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending/confirmed/disputed
    fact_pack_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    superseded_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fact_records.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
