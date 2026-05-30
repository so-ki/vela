from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BriefCitationResponse(BaseModel):
    id: str
    source_label: str
    title_zh: str
    title_pt: str
    url: str
    match_score: float
    requires_review: bool


class BriefItemResponse(BaseModel):
    code: str
    title: str
    priority: str
    gate_status: str
    match_score: float
    requires_review: bool
    block_reason: Optional[str] = None
    risk_zh: str
    risk_pt: str
    citations: List[BriefCitationResponse]


class BriefSectionResponse(BaseModel):
    dimension_id: str
    dimension_name: str
    dimension_name_pt: str
    risk_level: str
    summary_zh: str
    summary_pt: str
    items: List[BriefItemResponse]


class BriefGenerateResponse(BaseModel):
    scenario_id: int
    status: str
    threshold: int
    title_zh: str
    title_pt: str
    summary_zh: str
    summary_pt: str
    sections: List[BriefSectionResponse]
    blocked_items: List[BriefItemResponse]
    passed_count: int
    blocked_count: int
    disclaimer: str
    generated_at: datetime
    mode: str = Field(default="template", description="template | llm")
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_error: Optional[str] = None
    llm_polish_skipped: Optional[str] = None
