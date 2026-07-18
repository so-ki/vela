from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


MaterialState = Literal[
    "missing",
    "received",
    "unreadable",
    "ambiguous",
    "verified",
    "not_applicable",
]


class MaterialLedgerUpsertRequest(BaseModel):
    source_document: str = Field(min_length=1, max_length=512)
    state: MaterialState
    extraction_task_id: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=5000)
    confirmation_note: Optional[str] = Field(default=None, max_length=5000)
    expected_revision: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class MaterialLedgerResponse(BaseModel):
    id: str
    scenario_id: int
    block_id: str
    source_document: str
    state: MaterialState
    state_at: datetime
    extraction_task_id: Optional[str]
    note: Optional[str]
    confirmation_note: Optional[str]
    confirmed_by: Optional[int]
    confirmed_at: Optional[datetime]
    state_history: list[dict]
    revision: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CoverageTaskCreateRequest(BaseModel):
    source: str = Field(min_length=1, max_length=512)
    state: MaterialState
    denominator_ref: str = Field(min_length=1, max_length=1024)
    denominator_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    denominator_items: list[str] = Field(min_length=1, max_length=10_000)
    covered_items: list[str] = Field(default_factory=list, max_length=10_000)
    note: Optional[str] = Field(default=None, max_length=5000)

    model_config = {"extra": "forbid"}

    @field_validator("denominator_items", "covered_items")
    @classmethod
    def normalized_unique_items(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("覆盖项标识不得重复")
        return normalized

    @model_validator(mode="after")
    def covered_must_be_in_denominator(self):
        unknown = sorted(set(self.covered_items) - set(self.denominator_items))
        if unknown:
            raise ValueError(f"covered_items 不在官方分母中: {', '.join(unknown[:5])}")
        return self


class CoverageTaskResponse(BaseModel):
    id: str
    scenario_id: int
    source: str
    state: MaterialState
    denominator_ref: str
    denominator_snapshot_hash: str
    denominator_items: list[str]
    covered_items: list[str]
    denominator_count: int
    covered_count: int
    missing_count: int
    note: Optional[str]
    created_by: int
    created_at: datetime
    updated_at: datetime


class FactRecordCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=512)
    attribute: str = Field(min_length=1, max_length=512)
    value: str = Field(min_length=1, max_length=10_000)
    fact_time: str = Field(min_length=1, max_length=128)
    block_id: str = Field(min_length=1, max_length=255)
    fact_pack_version: str = Field(min_length=1, max_length=64)
    source_document: Optional[str] = Field(default=None, max_length=512)

    model_config = {"extra": "forbid"}

    @field_validator("subject", "attribute", "value", "fact_time", "block_id", "fact_pack_version")
    @classmethod
    def required_values_must_not_be_whitespace(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("事实字段不得为空白")
        return normalized


class FactRecordResponse(BaseModel):
    id: str
    scenario_id: int
    subject: str
    attribute: str
    value: str
    fact_time: str
    block_id: str
    fact_pack_version: str
    source_document: Optional[str]
    status: Literal["submitted", "business_confirmed"]
    confirmation_note: Optional[str]
    business_confirmed_by: Optional[int]
    business_confirmed_at: Optional[datetime]
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FactConfirmRequest(BaseModel):
    confirmation_note: str = Field(min_length=3, max_length=5000)

    model_config = {"extra": "forbid"}


class ClaimDraft(BaseModel):
    checklist_code: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=10_000)
    fact_refs: list[str] = Field(default_factory=list, max_length=200)
    evidence_refs: list[str] = Field(default_factory=list, max_length=200)

    model_config = {"extra": "forbid"}

    @field_validator("fact_refs", "evidence_refs")
    @classmethod
    def unique_refs(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("引用标识不得重复")
        return normalized


class ClaimCompileRequest(BaseModel):
    drafts: list[ClaimDraft] = Field(default_factory=list, max_length=500)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def one_draft_per_checklist_code(self):
        codes = [draft.checklist_code for draft in self.drafts]
        if len(codes) != len(set(codes)):
            raise ValueError("每个 checklist_code 只能提交一条 Claim 草稿")
        return self


class ClaimRecordResponse(BaseModel):
    id: str
    compilation_id: str
    scenario_id: int
    checklist_code: str
    statement: str
    status: Literal["refused", "awaiting_human_confirmation", "supported"]
    fact_refs: list[str]
    evidence_refs: list[str]
    reason_codes: list[str]
    confirmed_by: Optional[int]
    confirmed_at: Optional[datetime]
    confirmation_note: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClaimCompilationResponse(BaseModel):
    id: str
    scenario_id: int
    compiler_version: str
    input_hash: str
    output_hash: str
    denominator_count: int
    ready_count: int
    refused_count: int
    input_snapshot: dict
    created_by: int
    created_at: datetime
    claims: list[ClaimRecordResponse]


class ClaimConfirmRequest(BaseModel):
    decision: Literal["confirmed", "rejected"]
    confirmation_note: str = Field(min_length=3, max_length=5000)

    model_config = {"extra": "forbid"}


class CoverageProofCreateRequest(BaseModel):
    compilation_id: Optional[str] = Field(default=None, max_length=36)
    denominator_ref: str = Field(default="scenario-checklist", min_length=1, max_length=1024)

    model_config = {"extra": "forbid"}


class CoverageProofResponse(BaseModel):
    id: str
    scenario_id: int
    compilation_id: str
    denominator_ref: str
    denominator_hash: str
    denominator_count: int
    covered_count: int
    uncovered_count: int
    unanswerable_count: int
    proof: dict
    proof_hash: str
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}
