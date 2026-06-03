from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.document import ExtractedFact


class DimensionInfo(BaseModel):
    id: str
    name: str
    name_pt: str
    description: str
    order: int


class RulesCatalogResponse(BaseModel):
    pack: dict = Field(default_factory=dict)
    jurisdiction: dict
    industries: List[dict]
    action_types: List[dict]
    dimensions: List[DimensionInfo]
    supported_locations: List[dict]


class ScenarioCreateRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=255)
    country: str = Field(default="brazil")
    state: str = Field(default="sao_paulo")
    city: str = Field(default="campinas")
    industry: str = Field(default="new_energy")
    action_type: str = Field(default="greenfield_plant")
    investment_structure: Optional[str] = None
    description: str = Field(min_length=10)
    employee_count: Optional[int] = Field(default=None, ge=1)
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    compliance_dimensions: List[str] = Field(default_factory=list)
    board_date: Optional[date] = None
    start_date: Optional[date] = None
    production_date: Optional[date] = None
    remarks: Optional[str] = None
    document_extract: Optional["DocumentExtractSnapshot"] = None


class BusinessSubmitRequest(BaseModel):
    """业务提交项目材料；协查范围由法务后续确认。"""

    project_name: str = Field(min_length=1, max_length=255)
    country: str = Field(default="brazil")
    state: str = Field(default="sao_paulo")
    city: str = Field(default="campinas")
    industry: str = Field(default="new_energy")
    action_type: str = Field(default="greenfield_plant")
    investment_structure: Optional[str] = None
    description: str = Field(min_length=10)
    employee_count: Optional[int] = Field(default=None, ge=1)
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    board_date: Optional[date] = None
    start_date: Optional[date] = None
    production_date: Optional[date] = None
    remarks: Optional[str] = None
    document_extract: Optional["DocumentExtractSnapshot"] = None


class ScopeConfirmRequest(BaseModel):
    compliance_dimensions: List[str] = Field(min_length=1)
    polish: bool = False


class DocumentExtractSnapshot(BaseModel):
    filename: str = ""
    mode: str = Field(default="rules", description="rules | llm | manual")
    extracted_at: Optional[datetime] = None
    project_name: Optional[str] = None
    investment_structure: Optional[str] = None
    description: Optional[str] = None
    employee_count: Optional[int] = None
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    remarks: Optional[str] = None
    compliance_dimensions: List[str] = Field(default_factory=list)
    facts: List[ExtractedFact] = Field(default_factory=list)
    disclaimer: str = ""
    llm_skipped: Optional[str] = None
    source: str = Field(default="upload", description="upload | manual | demo")


class ChecklistItemResponse(BaseModel):
    code: str
    title: str
    description: str
    priority: str
    relevance_score: int
    rationale: str
    matched_triggers: List[str]
    status: str


class ChecklistSectionResponse(BaseModel):
    dimension_id: str
    dimension_name: str
    dimension_name_pt: str
    description: str
    items: List[ChecklistItemResponse]


class BusinessFeedbackItem(BaseModel):
    code: str
    title: str
    dimension_name: str = ""
    decision: str
    comment: Optional[str] = None
    external_counsel_required: bool = False
    reviewed_at: Optional[str] = None


class BusinessFeedback(BaseModel):
    review_status: str
    is_finalized: bool
    is_returned: bool = False
    approved_count: int
    rejected_count: int
    pending_count: int
    action_required: bool
    summary: str
    return_note: Optional[str] = None
    items: List[BusinessFeedbackItem] = Field(default_factory=list)


class ChecklistResponse(BaseModel):
    id: int
    title: str
    version: str
    total_items: int
    jurisdiction: str
    industry_pack_name: Optional[str] = None
    detected_industry: str
    detected_industry_name: str
    detected_sub_sectors: List[dict] = Field(default_factory=list)
    detected_action_type: str
    detected_action_type_name: str
    selected_dimensions: List[str]
    sections: List[ChecklistSectionResponse]
    disclaimer: str
    created_at: datetime


class ScenarioResponse(BaseModel):
    id: int
    project_name: str
    country: str
    state: str
    city: str
    industry: str
    action_type: str
    investment_structure: Optional[str]
    description: str
    employee_count: Optional[int]
    capacity_notes: Optional[str]
    facility_notes: Optional[str]
    compliance_dimensions: List[str]
    board_date: Optional[date]
    start_date: Optional[date]
    production_date: Optional[date]
    remarks: Optional[str]
    status: str
    created_at: datetime
    checklist: Optional[ChecklistResponse] = None
    business_feedback: Optional[BusinessFeedback] = None
    can_revise: bool = False
    revision_round: int = 0
    document_extract: Optional[DocumentExtractSnapshot] = None

    model_config = {"from_attributes": True}


class ScenarioSummary(BaseModel):
    id: int
    project_name: str
    city: str
    industry: str
    status: str
    total_items: Optional[int] = None
    created_at: datetime
    submitter_name: Optional[str] = None
    submitter_organization: Optional[str] = None
    progress_status: Optional[str] = None
    review_priority: Optional[str] = None
    blocked_count: Optional[int] = None
    passed_count: Optional[int] = None
    legal_rejected_count: Optional[int] = None
    feedback_action_required: Optional[bool] = None
    needs_revision: Optional[bool] = None
    business_archived: bool = False
    legal_deleted: bool = False
    legal_deleted_at: Optional[datetime] = None
    has_document_extract: bool = False

    model_config = {"from_attributes": True}
