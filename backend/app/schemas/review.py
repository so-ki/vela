from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ReviewItemUpdateRequest(BaseModel):
    decision: str = Field(description="approved | rejected | pending")
    comment: Optional[str] = None


class ReviewItemResponse(BaseModel):
    code: str
    title: str
    dimension_name: str
    gate_status: str
    match_score: float
    decision: str
    comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class ReviewResponse(BaseModel):
    scenario_id: int
    status: str
    reviewer_name: str
    started_at: datetime
    finalized_at: Optional[datetime] = None
    items: List[ReviewItemResponse]
    approved_count: int
    rejected_count: int
    pending_count: int
    can_finalize: bool
    can_export: bool
