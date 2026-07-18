from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


SourceVersionStatus = Literal["candidate", "reviewed", "active", "rejected"]


class SourceRelation(BaseModel):
    relation_type: str = Field(min_length=1, max_length=64)
    target_canonical_id: str = Field(min_length=1, max_length=512)
    target_urn: Optional[str] = Field(default=None, max_length=1024)
    note: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class ArticleSnapshot(BaseModel):
    article_id: str = Field(min_length=1, max_length=256)
    heading: Optional[str] = Field(default=None, max_length=1000)
    normalized_text: str = Field(min_length=1, max_length=500_000)
    relations: list[SourceRelation] = Field(default_factory=list, max_length=500)

    model_config = {"extra": "forbid"}


class LegalSourceCandidateCreateRequest(BaseModel):
    canonical_id: str = Field(min_length=1, max_length=512)
    citation_id: str = Field(min_length=1, max_length=1024)
    urn: Optional[str] = Field(default=None, max_length=1024)
    source_authority: str = Field(min_length=1, max_length=512)
    official_domain: str = Field(min_length=1, max_length=255)
    official_source_basis: str = Field(min_length=3, max_length=5000)
    source_url: str = Field(min_length=1, max_length=2048)
    fetched_at: datetime
    etag: Optional[str] = Field(default=None, max_length=1024)
    last_modified: Optional[datetime] = None
    raw_content: str = Field(min_length=1, max_length=5_000_000)
    normalized_content: str = Field(min_length=1, max_length=5_000_000)
    parser_version: str = Field(min_length=1, max_length=64)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    relations: list[SourceRelation] = Field(default_factory=list, max_length=5000)
    articles: list[ArticleSnapshot] = Field(min_length=1, max_length=10_000)
    previous_version_id: Optional[str] = Field(default=None, max_length=36)

    model_config = {"extra": "forbid"}

    @field_validator("source_url")
    @classmethod
    def official_source_must_use_https(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("官方来源必须使用带主机名的 HTTPS URL")
        return value.strip()

    @field_validator("official_domain")
    @classmethod
    def official_domain_is_a_hostname(cls, value: str) -> str:
        normalized = value.strip().lower().rstrip(".")
        parsed = urlparse(f"https://{normalized}")
        if not normalized or parsed.hostname != normalized or "/" in normalized:
            raise ValueError("official_domain 必须是主机名，不得包含路径")
        return normalized

    @field_validator("articles")
    @classmethod
    def article_ids_are_unique(cls, values: list[ArticleSnapshot]) -> list[ArticleSnapshot]:
        article_ids = [item.article_id.strip() for item in values]
        if len(article_ids) != len(set(article_ids)):
            raise ValueError("同一来源版本的 article_id 不得重复")
        return values

    @model_validator(mode="after")
    def valid_period_is_ordered(self):
        hostname = (urlparse(self.source_url).hostname or "").lower().rstrip(".")
        if hostname != self.official_domain and not hostname.endswith(f".{self.official_domain}"):
            raise ValueError("source_url 主机必须等于 official_domain 或其子域名")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to 不得早于 valid_from")
        return self


class ArticleDiffResponse(BaseModel):
    article_id: str
    change_type: Literal["added", "removed", "modified"]
    previous_hash: Optional[str]
    current_hash: Optional[str]
    relation_changes: dict


class LegalChangeEventResponse(BaseModel):
    id: str
    source_version_id: str
    previous_version_id: Optional[str]
    canonical_id: str
    change_type: Literal["initial", "content_changed", "format_only"]
    article_diff: list[ArticleDiffResponse]
    relation_diff: dict
    raw_hash_before: Optional[str]
    raw_hash_after: str
    normalized_hash_before: Optional[str]
    normalized_hash_after: str
    detected_at: datetime
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LegalSourceVersionResponse(BaseModel):
    id: str
    canonical_id: str
    citation_id: str
    urn: Optional[str]
    source_authority: str
    official_domain: str
    official_source_basis: str
    source_url: str
    fetched_at: datetime
    etag: Optional[str]
    last_modified: Optional[datetime]
    raw_hash: str
    normalized_hash: str
    parser_version: str
    valid_from: Optional[date]
    valid_to: Optional[date]
    status: SourceVersionStatus = Field(
        description=(
            "人工审查生命周期；active 仅表示 registry-approved snapshot，"
            "不表示唯一当前法源版本，也不会发布 capability-pack corpus"
        )
    )
    relations: list[dict]
    article_snapshots: list[dict]
    previous_version_id: Optional[str]
    decision_history: list[dict]
    reviewed_by: Optional[int]
    reviewed_at: Optional[datetime]
    activated_by: Optional[int]
    activated_at: Optional[datetime]
    rejected_by: Optional[int]
    rejected_at: Optional[datetime]
    decision_note: Optional[str]
    created_by: int
    created_at: datetime
    release_scope: Literal["source_registry_only"] = "source_registry_only"
    capability_pack_corpus_updated: Literal[False] = False
    current_version_designation: Literal["not_assigned"] = "not_assigned"

    model_config = {"from_attributes": True}


class LegalSourceCandidateResponse(BaseModel):
    version: LegalSourceVersionResponse
    change_event: LegalChangeEventResponse


class LegalSourceDecisionRequest(BaseModel):
    decision: Literal["reviewed", "active", "rejected"]
    note: str = Field(min_length=3, max_length=5000)

    model_config = {"extra": "forbid"}
