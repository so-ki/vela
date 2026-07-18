from __future__ import annotations

import json
from typing import Annotated, Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from pydantic.types import StringConstraints


SESSION_ID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
QUESTION_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
MAX_INTERVIEW_ANSWER_CHARS = 20_000
MAX_INTERVIEW_LIST_ITEMS = 16
MAX_INTERVIEW_LIST_ITEM_CHARS = 256
MAX_INTERVIEW_ANSWER_KEYS = 16
MAX_INTERVIEW_SYNC_BYTES = 64 * 1024

SessionId = Annotated[
    str,
    StringConstraints(
        min_length=36,
        max_length=36,
        pattern=SESSION_ID_PATTERN,
        strict=True,
    ),
]
QuestionId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=QUESTION_ID_PATTERN,
        strict=True,
    ),
]
InterviewAnswerValue = StrictStr | Annotated[
    list[Annotated[StrictStr, Field(max_length=MAX_INTERVIEW_LIST_ITEM_CHARS)]],
    Field(max_length=MAX_INTERVIEW_LIST_ITEMS),
]


class InterviewAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: QuestionId
    answer: InterviewAnswerValue

    @field_validator("answer")
    @classmethod
    def bound_serialized_answer(cls, value: InterviewAnswerValue) -> InterviewAnswerValue:
        if isinstance(value, str) and len(value) > MAX_INTERVIEW_ANSWER_CHARS:
            raise ValueError(f"单项访谈答案不能超过 {MAX_INTERVIEW_ANSWER_CHARS} 个字符")
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_INTERVIEW_SYNC_BYTES:
            raise ValueError("访谈答案序列化后过大")
        return value


class InterviewSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[QuestionId, InterviewAnswerValue] = Field(
        default_factory=dict,
        max_length=MAX_INTERVIEW_ANSWER_KEYS,
    )

    @field_validator("answers")
    @classmethod
    def bound_serialized_answers(
        cls,
        value: dict[str, InterviewAnswerValue],
    ) -> dict[str, InterviewAnswerValue]:
        for answer in value.values():
            if isinstance(answer, str) and len(answer) > MAX_INTERVIEW_ANSWER_CHARS:
                raise ValueError(f"单项访谈答案不能超过 {MAX_INTERVIEW_ANSWER_CHARS} 个字符")
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_INTERVIEW_SYNC_BYTES:
            raise ValueError(f"批量同步答案不能超过 {MAX_INTERVIEW_SYNC_BYTES // 1024}KB")
        return value


class InterviewCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: SessionId


class PlaybookProfileResponse(BaseModel):
    completed: bool
    user_id: Optional[int] = None
    profile_schema_version: Optional[str] = None
    profile_version: Optional[str] = None
    profile_source: Optional[str] = None
    completed_at: Optional[str] = None
    org_name: Optional[str] = None
    primary_jurisdiction: Optional[str] = None
    industry_focus: List[str] = Field(default_factory=list)
    default_compliance_dimensions: List[str] = Field(default_factory=list)
    suggested_checklist_codes: List[str] = Field(default_factory=list)
    output_language: Optional[str] = None
    risk_tolerance: Optional[str] = None
    match_threshold_adjustment: int = 0
    contract_house_rules: Optional[str] = None
    brief_template_style: Optional[str] = None
    external_counsel_triggers: Optional[str] = None
    playbook_md: Optional[str] = None
    message: Optional[str] = None


class OnboardingStatusResponse(BaseModel):
    completed: bool
    required: bool
    role: str


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
