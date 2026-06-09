from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ReviewItemUpdateRequest(BaseModel):
    decision: str = Field(description="approved | rejected | pending")
    comment: Optional[str] = None
    external_counsel_required: Optional[bool] = Field(
        default=None,
        description="标记需外聘当地律所补充意见",
    )


class ReviewReturnRequest(BaseModel):
    note: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="退回说明（可选，会展示给业务）",
    )


class ReviewLegalHitSummary(BaseModel):
    id: str
    source_label: str
    title_zh: Optional[str] = None
    title_pt: Optional[str] = None
    excerpt_pt: Optional[str] = None
    excerpt_zh: Optional[str] = None
    url: str
    match_score: float
    requires_review: bool = False


class ReviewItemResponse(BaseModel):
    code: str
    title: str
    dimension_name: str
    gate_status: str
    match_score: float
    decision: str
    comment: Optional[str] = None
    external_counsel_required: bool = False
    legal_hits: List[ReviewLegalHitSummary] = Field(default_factory=list)
    reviewed_at: Optional[datetime] = None
    carry_forward: bool = False
    invalidated: bool = False


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
    can_return_to_business: bool = False
    version_label: Optional[str] = None
