from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractedFact(BaseModel):
    field: str
    value: str
    source_snippet: Optional[str] = None
    source_filename: Optional[str] = None


class FieldConflictSource(BaseModel):
    filename: str
    value: str


class FieldConflict(BaseModel):
    field: str
    label: str
    sources: List[FieldConflictSource] = Field(default_factory=list)
    merge_note: str = ""


class DocumentExtractResponse(BaseModel):
    filename: str
    mode: str = Field(description="rules | llm")
    project_name: Optional[str] = None
    investment_destination: Optional[str] = None
    investment_structure: Optional[str] = None
    funding_source: Optional[str] = None
    project_content_scale: Optional[str] = None
    description: Optional[str] = None
    employee_count: Optional[int] = None
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    known_risks: Optional[str] = None
    board_date: Optional[str] = None
    start_date: Optional[str] = None
    production_date: Optional[str] = None
    remarks: Optional[str] = None
    compliance_dimensions: List[str] = Field(default_factory=list)
    facts: List[ExtractedFact] = Field(default_factory=list)
    disclaimer: str
    llm_skipped: Optional[str] = None


class DocumentExtractBatchResponse(BaseModel):
    files: List[DocumentExtractResponse]
    merged: DocumentExtractResponse
    failed: List[str] = Field(default_factory=list, description="抽取失败已跳过的文件及原因")
    conflicts: List[FieldConflict] = Field(default_factory=list, description="多文件同字段取值不一致")
