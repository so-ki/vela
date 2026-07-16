from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MANIFEST_SCHEMA_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE = re.compile(r"^(rules|corpus|fixture)://[A-Za-z0-9][A-Za-z0-9._/-]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactReference(StrictModel):
    artifact_id: str
    version: str
    content_hash: str
    resource: str

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("artifact_id 格式无效")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not value.strip() or len(value) > 64:
            raise ValueError("artifact version 格式无效")
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        value = value.lower()
        if not _SHA256.fullmatch(value):
            raise ValueError("artifact content_hash 必须为 SHA-256")
        return value

    @field_validator("resource")
    @classmethod
    def validate_resource(cls, value: str) -> str:
        if not _RESOURCE.fullmatch(value) or ".." in value.split("://", 1)[1].split("/"):
            raise ValueError("artifact resource 非法或包含路径穿越")
        return value


class ArtifactBinding(StrictModel):
    country: str
    industry: str
    action_type: str


class RoutingHints(StrictModel):
    country: list[str]
    industry: list[str]
    action_type: list[str]

    @field_validator("country", "industry", "action_type")
    @classmethod
    def normalize_hints(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip() for item in value if item.strip()})
        if not normalized:
            raise ValueError("routing hints 不能为空")
        return normalized


class RetrievalConfig(StrictModel):
    match_threshold_default: int = Field(ge=50, le=95)
    match_threshold_min: int = Field(ge=50, le=95)
    match_threshold_max: int = Field(ge=50, le=95)
    top_k_default: int = Field(ge=0, le=10)
    top_k_min: int = Field(ge=0, le=10)
    top_k_max: int = Field(ge=0, le=10)
    expansion_enabled: bool
    expansion_candidate_extra: int = Field(ge=0, le=10)
    expansion_min_keyword_score: float = Field(ge=0, le=100)
    expansion_context_limit: int = Field(ge=0, le=5000)

    @model_validator(mode="after")
    def validate_ranges(self) -> "RetrievalConfig":
        if not self.match_threshold_min <= self.match_threshold_default <= self.match_threshold_max:
            raise ValueError("match threshold default 不在允许范围")
        if not self.top_k_min <= self.top_k_default <= self.top_k_max:
            raise ValueError("top-k default 不在允许范围")
        return self


class OutputProfile(StrictModel):
    profile_id: str
    version: str
    brief_languages: list[str]
    brief_title: str
    export_template: Literal["legacy", "law_school"]
    disclaimer: str

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("output profile id 格式无效")
        return value

    @field_validator("brief_languages")
    @classmethod
    def validate_languages(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip().lower() for item in value if item.strip()})
        if not normalized:
            raise ValueError("output profile 至少需要一种语言")
        return normalized


class CapabilityPackManifest(StrictModel):
    manifest_schema_version: str
    pack_id: str
    version: str
    status: Literal["active", "inactive"]
    display_name: str
    description: str
    country: str
    industry: str
    action_type: str
    languages: list[str]
    issue_modules: list[str]
    rules_artifact: ArtifactReference
    corpus_artifact: ArtifactReference
    artifact_binding: ArtifactBinding
    routing_hints: RoutingHints
    retrieval_config: RetrievalConfig
    output_profile: OutputProfile
    semantic_hash: str

    @field_validator("manifest_schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"不支持的 Capability Pack manifest schema：{value}")
        return value

    @field_validator("pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("pack_id 格式无效")
        return value

    @field_validator("version")
    @classmethod
    def validate_pack_version(cls, value: str) -> str:
        if not _SEMVER.fullmatch(value):
            raise ValueError("Capability Pack version 必须使用 semver")
        return value

    @field_validator("semantic_hash")
    @classmethod
    def validate_semantic_hash_format(cls, value: str) -> str:
        value = value.lower()
        if not _SHA256.fullmatch(value):
            raise ValueError("semantic_hash 必须为 SHA-256")
        return value

    @field_validator("languages", "issue_modules")
    @classmethod
    def normalize_semantic_lists(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip() for item in value if item.strip()})
        if not normalized:
            raise ValueError("Capability Pack 列表字段不能为空")
        return normalized

    def semantic_payload(self) -> dict[str, Any]:
        """Only generation semantics; labels, status and load metadata stay outside."""
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "pack_id": self.pack_id,
            "version": self.version,
            "country": self.country,
            "industry": self.industry,
            "action_type": self.action_type,
            "languages": sorted(self.languages),
            "issue_modules": sorted(self.issue_modules),
            "rules_artifact": self.rules_artifact.model_dump(mode="json"),
            "corpus_artifact": self.corpus_artifact.model_dump(mode="json"),
            "artifact_binding": self.artifact_binding.model_dump(mode="json"),
            "routing_hints": self.routing_hints.model_dump(mode="json"),
            "retrieval_config": self.retrieval_config.model_dump(mode="json"),
            "output_profile": self.output_profile.model_dump(mode="json"),
        }

    def canonical_semantic_hash(self) -> str:
        raw = json.dumps(
            self.semantic_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def public_summary(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "version": self.version,
            "pack_hash": self.semantic_hash,
            "status": self.status,
            "display_name": self.display_name,
            "description": self.description,
            "country": self.country,
            "industry": self.industry,
            "action_type": self.action_type,
            "languages": list(self.languages),
        }
