from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DimensionInfo(BaseModel):
    id: str
    name: str
    name_pt: str
    description: str
    order: int


class RulesCatalogResponse(BaseModel):
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
    compliance_dimensions: List[str] = Field(min_length=1)
    board_date: Optional[date] = None
    start_date: Optional[date] = None
    production_date: Optional[date] = None
    remarks: Optional[str] = None


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


class ChecklistResponse(BaseModel):
    id: int
    title: str
    version: str
    total_items: int
    jurisdiction: str
    detected_industry: str
    detected_industry_name: str
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

    model_config = {"from_attributes": True}
