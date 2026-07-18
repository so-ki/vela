from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.statuses import MaterialBlockState
from app.models.user import utcnow


def _new_block_uid() -> str:
    return uuid.uuid4().hex


class MaterialBlock(Base):
    """材料账本条目：每份进入协查的材料块必须在账本上有唯一状态。"""

    __tablename__ = "material_blocks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    block_uid: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=_new_block_uid, nullable=False)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("investigation_scenarios.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # file / field_set / extract_snapshot
    filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    stored_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default=MaterialBlockState.RAW_ARCHIVED.value, nullable=False)
    pack_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    superseded_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material_blocks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    transitions: Mapped[list["MaterialBlockTransition"]] = relationship(
        back_populates="block", cascade="all, delete-orphan", order_by="MaterialBlockTransition.id"
    )


class MaterialBlockTransition(Base):
    """账本状态迁移流水：谁、何时、为何把块从 A 态推到 B 态。"""

    __tablename__ = "material_block_transitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("material_blocks.id"), index=True, nullable=False)
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    block: Mapped[MaterialBlock] = relationship(back_populates="transitions")
