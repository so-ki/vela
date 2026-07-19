from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CompetitionBusinessMaterial(BaseModel):
    id: str
    filename: str
    uploaded_at: datetime
    status: str


class CompetitionBusinessFact(BaseModel):
    id: str
    label: str
    value: str
    status: str


class CompetitionBusinessSupplement(BaseModel):
    id: str
    title: str
    why: str
    accepted_materials: list[str]
    status: str


class CompetitionBusinessProgress(BaseModel):
    label: str
    state: Literal["completed", "current", "upcoming"]


class CompetitionBusinessCenterResponse(BaseModel):
    scenario_id: int
    project_name: str
    materials: list[CompetitionBusinessMaterial]
    facts: list[CompetitionBusinessFact]
    supplements: list[CompetitionBusinessSupplement]
    progress: list[CompetitionBusinessProgress]
    current_status: str


class CompetitionBusinessFactConfirmRequest(BaseModel):
    value: str = Field(min_length=1, max_length=10_000)

    model_config = {"extra": "forbid"}
