from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractedFact(BaseModel):
    field: str
    value: str
    source_snippet: Optional[str] = None


class DocumentExtractResponse(BaseModel):
    filename: str
    mode: str = Field(description="rules | llm")
    project_name: Optional[str] = None
    investment_structure: Optional[str] = None
    description: Optional[str] = None
    employee_count: Optional[int] = None
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    remarks: Optional[str] = None
    compliance_dimensions: List[str] = Field(default_factory=list)
    facts: List[ExtractedFact] = Field(default_factory=list)
    disclaimer: str
    llm_skipped: Optional[str] = None
