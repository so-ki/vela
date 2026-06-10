from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.document import ExtractedFact


class DimensionInfo(BaseModel):
    id: str
    name: str
    name_pt: str
    description: str
    order: int


class RulesPackSummary(BaseModel):
    id: str
    name: Optional[str] = None
    version: Optional[str] = None
    region: Optional[str] = None
    primary_country: Optional[str] = None
    industry_focus: Optional[str] = None
    focus: Optional[str] = None
    status: str = "active"


class RulesClassificationResponse(BaseModel):
    schema_version: str
    default_pack_id: str
    regions: List[dict]
    packs: List[RulesPackSummary]


class RulesCatalogResponse(BaseModel):
    rules_pack_id: str = Field(default="brazil_new_energy")
    pack: dict = Field(default_factory=dict)
    jurisdiction: dict
    industries: List[dict]
    action_types: List[dict]
    dimensions: List[DimensionInfo]
    supported_locations: List[dict]
    scene_defaults: dict = Field(default_factory=dict)
    material_fields: List[dict] = Field(default_factory=list)
    ui_groups: List[dict] = Field(default_factory=list)
    material_intake_policy: dict = Field(default_factory=dict)
    dimension_field_requirements: dict[str, List[str]] = Field(default_factory=dict)


class ScenarioCreateRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=255)
    rules_pack_id: Optional[str] = None
    country: str = Field(default="brazil")
    state: str = Field(default="sao_paulo")
    city: str = Field(default="campinas")
    industry: str = Field(default="new_energy")
    action_type: str = Field(default="greenfield_plant")
    investment_structure: Optional[str] = None
    investment_destination: Optional[str] = None
    project_content_scale: Optional[str] = None
    funding_source: Optional[str] = None
    description: str = Field(min_length=10)
    known_risks: Optional[str] = None
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
    rules_pack_id: Optional[str] = None
    country: str = Field(default="brazil")
    state: str = Field(default="sao_paulo")
    city: str = Field(default="campinas")
    industry: str = Field(default="new_energy")
    action_type: str = Field(default="greenfield_plant")
    investment_structure: Optional[str] = None
    investment_destination: Optional[str] = None
    project_content_scale: Optional[str] = None
    funding_source: Optional[str] = None
    description: str = Field(min_length=10)
    known_risks: Optional[str] = None
    employee_count: Optional[int] = Field(default=None, ge=1)
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    board_date: Optional[date] = None
    start_date: Optional[date] = None
    production_date: Optional[date] = None
    remarks: Optional[str] = None
    document_extract: Optional["DocumentExtractSnapshot"] = None


class ScopeConfirmRequest(BaseModel):
    compliance_dimensions: List[str] = Field(default_factory=list)
    polish: bool = False
    match_threshold: int = Field(default=70, ge=50, le=95, description="条目匹配度门控阈值")
    retrieval_top_k: int = Field(default=3, ge=1, le=10, description="每条核查题绑定的法条数量")
    include_playbook_suggestions: bool = Field(
        default=False,
        description="显式为 true 时，将 Playbook 建议核查项并入清单（不修改规则 JSON）",
    )


class ArchivedMaterialFile(BaseModel):
    id: str
    filename: str
    stored_name: str
    size: int = 0
    content_type: str = "application/octet-stream"
    archived_at: Optional[datetime] = None


class DocumentExtractFileSnapshot(BaseModel):
    filename: str = ""
    mode: str = Field(default="rules", description="rules | llm | manual")
    project_name: Optional[str] = None
    investment_destination: Optional[str] = None
    investment_structure: Optional[str] = None
    funding_source: Optional[str] = None
    project_content_scale: Optional[str] = None
    description: Optional[str] = None
    known_risks: Optional[str] = None
    employee_count: Optional[int] = None
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    board_date: Optional[str] = None
    start_date: Optional[str] = None
    production_date: Optional[str] = None
    remarks: Optional[str] = None
    compliance_dimensions: List[str] = Field(default_factory=list)
    facts: List[ExtractedFact] = Field(default_factory=list)
    disclaimer: str = ""
    llm_skipped: Optional[str] = None


class CustomReviewFieldSnapshot(BaseModel):
    id: str
    label: str
    value: str = ""
    layout: str = "standalone"
    merge_target_key: Optional[str] = None
    merge_target_label: Optional[str] = None


class DocumentExtractSnapshot(BaseModel):
    filename: str = ""
    file_count: int = Field(default=1, ge=0)
    files: List[DocumentExtractFileSnapshot] = Field(default_factory=list)
    mode: str = Field(default="rules", description="rules | llm | manual")
    extracted_at: Optional[datetime] = None
    project_name: Optional[str] = None
    investment_destination: Optional[str] = None
    investment_structure: Optional[str] = None
    funding_source: Optional[str] = None
    project_content_scale: Optional[str] = None
    description: Optional[str] = None
    known_risks: Optional[str] = None
    employee_count: Optional[int] = None
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    board_date: Optional[str] = None
    start_date: Optional[str] = None
    production_date: Optional[str] = None
    remarks: Optional[str] = None
    compliance_dimensions: List[str] = Field(default_factory=list)
    facts: List[ExtractedFact] = Field(default_factory=list)
    disclaimer: str = ""
    llm_skipped: Optional[str] = None
    source: str = Field(default="upload", description="upload | manual | demo")
    field_conflicts: List[dict] = Field(default_factory=list)
    hidden_field_keys: List[str] = Field(default_factory=list)
    custom_fields: List[CustomReviewFieldSnapshot] = Field(default_factory=list)
    field_display_order: List[str] = Field(default_factory=list)
    archived_files: List[ArchivedMaterialFile] = Field(default_factory=list)


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


class MaterialFeedbackItem(BaseModel):
    field_key: str
    label: str
    dimensions: List[str] = Field(default_factory=list)


class MaterialElementFeedbackItem(BaseModel):
    element_id: str
    label: str
    dimensions: List[str] = Field(default_factory=list)


class MaterialFeedback(BaseModel):
    return_kind: str = "materials"
    is_returned: bool = False
    action_required: bool = False
    summary: str
    return_note: Optional[str] = None
    selected_dimensions: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    missing_elements: List[str] = Field(default_factory=list)
    missing_by_dimension: dict[str, List[str]] = Field(default_factory=dict)
    missing_elements_by_dimension: dict[str, List[str]] = Field(default_factory=dict)
    field_labels: dict[str, str] = Field(default_factory=dict)
    element_labels: dict[str, str] = Field(default_factory=dict)
    items: List[MaterialFeedbackItem] = Field(default_factory=list)
    element_items: List[MaterialElementFeedbackItem] = Field(default_factory=list)


class MaterialReviewPreviewRequest(BaseModel):
    compliance_dimensions: List[str] = Field(default_factory=list)


class MaterialReturnRequest(BaseModel):
    compliance_dimensions: List[str] = Field(min_length=1)
    missing_fields: List[str] = Field(default_factory=list)
    missing_elements: List[str] = Field(default_factory=list)
    note: Optional[str] = None

    @model_validator(mode="after")
    def require_missing_targets(self) -> MaterialReturnRequest:
        if not self.missing_fields and not self.missing_elements:
            raise ValueError("请至少指定一项需补充的构成要件或字段")
        return self


class ChecklistResponse(BaseModel):
    id: int
    title: str
    version: str
    total_items: int
    jurisdiction: str
    industry_pack_id: Optional[str] = None
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
    rules_pack_id: Optional[str] = None
    country: str
    state: str
    city: str
    industry: str
    action_type: str
    investment_structure: Optional[str]
    investment_destination: Optional[str]
    project_content_scale: Optional[str]
    funding_source: Optional[str]
    description: str
    known_risks: Optional[str]
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
    material_feedback: Optional[MaterialFeedback] = None
    material_scope_dimensions: List[str] = Field(default_factory=list)
    can_revise: bool = False
    revision_round: int = 0
    document_extract: Optional[DocumentExtractSnapshot] = None
    investigation_adequacy: Optional[dict] = None
    gate_a_allows_review: bool = True
    can_return_materials: bool = False
    incremental_regen: Optional[dict] = None
    conflict_flags: List[dict] = Field(default_factory=list)
    investigation_settings: Optional[dict] = None
    grounding_report: Optional[dict] = None
    verification_report: Optional[dict] = None
    playbook_deviations: List[dict] = Field(default_factory=list)

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
