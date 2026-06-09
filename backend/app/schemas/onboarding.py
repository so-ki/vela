from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class InterviewAnswerRequest(BaseModel):
    question_id: str
    answer: Any


class InterviewCompleteRequest(BaseModel):
    session_id: str


class PlaybookProfileResponse(BaseModel):
    completed: bool
    user_id: Optional[int] = None
    org_name: Optional[str] = None
    primary_jurisdiction: Optional[str] = None
    industry_focus: List[str] = Field(default_factory=list)
    output_language: Optional[str] = None
    risk_tolerance: Optional[str] = None
    match_threshold_adjustment: int = 0
    contract_house_rules: Optional[str] = None
    brief_template_style: Optional[str] = None
    external_counsel_triggers: Optional[str] = None
    playbook_md: Optional[str] = None
    message: Optional[str] = None


class InterviewStartResponse(BaseModel):
    session_id: str
    script: dict[str, Any]
    completed_steps: int
    total_steps: int


class ContractUploadResponse(BaseModel):
    doc_id: str
    filename: str
    contract_type: str
    status: str


class ContractAnalyzeRequest(BaseModel):
    doc_id: str


class DiligenceUploadResponse(BaseModel):
    doc_id: str
    filename: str
    categories: List[str]


class ProjectHubResponse(BaseModel):
    project_id: int
    project_name: str
    status: str
    location: dict[str, Any]
    modules: dict[str, Any]
    context_preview: dict[str, Any]
    routes: dict[str, str]
