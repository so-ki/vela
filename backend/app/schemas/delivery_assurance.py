from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator


def _non_placeholder_sha256(value: str) -> str:
    # A cryptographic digest with fewer than four distinct hexadecimal symbols
    # is for all practical purposes a fixture/placeholder, not external evidence.
    if len(value) == 64 and len(set(value)) < 4:
        raise ValueError("证据 SHA-256 不能使用全零或重复字符占位值")
    return value


Sha256 = Annotated[str, AfterValidator(_non_placeholder_sha256)]
DeliveryEvidenceKind = Literal[
    "oab_submission",
    "oab_verification_report",
    "iti_signature_artifact",
    "iti_validation_report",
    "uat_test_plan",
    "uat_test_evidence",
    "content_primary_signature",
    "content_primary_validation_report",
    "content_secondary_signature",
    "content_secondary_validation_report",
    "gold_dataset",
    "evaluation_policy",
    "evaluation_run",
    "build_artifact_descriptor",
    "build_artifact_receipt",
    "sbom",
    "security_report",
    "provenance",
    "runtime_probe",
    "config_schema",
]


def _https(value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("证据引用必须是带主机名的 HTTPS URL")
    return normalized


class DeliveryEvidenceObjectResponse(BaseModel):
    id: str
    scenario_id: Optional[int]
    evidence_kind: DeliveryEvidenceKind
    filename: str
    media_type: str
    content_sha256: str
    content_length: int
    source_url: Optional[str]
    status: Literal["available", "revoked"]
    uploaded_by: int
    uploaded_at: datetime
    expires_at: Optional[datetime]
    revoked_by: Optional[int]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CredentialCreateRequest(BaseModel):
    holder_name: str = Field(min_length=2, max_length=255)
    jurisdiction: str = Field(min_length=2, max_length=64)
    authority: str = Field(min_length=2, max_length=255)
    registration_number: str = Field(min_length=2, max_length=128)
    official_register_url: str = Field(min_length=1, max_length=2048)
    submitted_evidence_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = {"extra": "forbid"}

    @field_validator("official_register_url")
    @classmethod
    def register_url_is_https(cls, value: str) -> str:
        return _https(value)


class CredentialDecisionRequest(BaseModel):
    decision: Literal["verified", "rejected", "revoked"]
    expected_revision: int = Field(ge=0)
    note: str = Field(min_length=10, max_length=5000)
    verification_reference: Optional[str] = Field(default=None, max_length=2048)
    verification_evidence_hash: Optional[Sha256] = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    registration_status: Optional[Literal["regular"]] = None
    valid_until: Optional[datetime] = None

    model_config = {"extra": "forbid"}

    @field_validator("verification_reference")
    @classmethod
    def reference_is_https(cls, value: Optional[str]) -> Optional[str]:
        return _https(value) if value else None

    @model_validator(mode="after")
    def verified_requires_external_evidence(self):
        if self.decision == "verified" and (
            not self.verification_reference
            or not self.verification_evidence_hash
            or self.registration_status != "regular"
            or self.valid_until is None
        ):
            raise ValueError("verified 决定必须提供官方核验引用、证据哈希和有效期")
        return self


class CredentialResponse(BaseModel):
    id: str
    user_id: int
    holder_name: str
    jurisdiction: str
    authority: str
    registration_number: str
    official_register_url: str
    submitted_evidence_hash: str
    status: Literal["pending", "verified", "rejected", "revoked"]
    verification_reference: Optional[str]
    verification_evidence_hash: Optional[str]
    registration_status: Optional[str]
    decision_note: Optional[str]
    verified_by: Optional[int]
    verified_at: Optional[datetime]
    valid_until: Optional[datetime]
    revoked_by: Optional[int]
    revoked_at: Optional[datetime]
    revision: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    verification_boundary: Literal["external_human_assertion"] = "external_human_assertion"

    model_config = {"from_attributes": True}


class ExpertAttestationCreateRequest(BaseModel):
    credential_id: str = Field(min_length=36, max_length=36)
    artifact_ids: list[str] = Field(min_length=3, max_length=3)
    signed_artifact_manifest_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    signature_format: Literal["PAdES", "CAdES", "XAdES"]
    signature_artifact_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    signature_validation_url: str = Field(min_length=1, max_length=2048)
    signature_validation_report_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    certificate_subject: str = Field(min_length=3, max_length=512)
    certificate_serial: str = Field(min_length=3, max_length=255)
    certificate_valid_until: datetime
    statement: str = Field(min_length=50, max_length=20_000)
    limitations: str = Field(min_length=20, max_length=20_000)
    expires_at: datetime

    model_config = {"extra": "forbid"}

    @field_validator("artifact_ids")
    @classmethod
    def artifacts_are_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(len(value) != 36 for value in values):
            raise ValueError("必须提交三个不同的冻结制品 ID")
        return values

    @field_validator("signature_validation_url")
    @classmethod
    def validation_url_is_iti(cls, value: str) -> str:
        normalized = _https(value)
        if (urlparse(normalized).hostname or "").lower() != "validar.iti.gov.br":
            raise ValueError("巴西数字签名验证必须引用 ITI VALIDAR 官方域名")
        return normalized


class ExpertAttestationResponse(BaseModel):
    id: str
    scenario_id: int
    credential_id: str
    signed_by: int
    snapshot: dict
    snapshot_hash: str
    artifact_manifest: list[dict]
    artifact_manifest_hash: str
    signature_format: str
    signature_artifact_hash: str
    signature_validation_url: str
    signature_validation_report_hash: str
    signature_validation_status: Literal["submitted", "approved", "rejected"]
    signature_verified_by: Optional[int]
    signature_verified_at: Optional[datetime]
    signature_verification_note: Optional[str]
    certificate_subject: str
    certificate_serial: str
    certificate_valid_until: datetime
    statement: str
    limitations: str
    status: Literal["pending_validation", "active", "superseded", "rejected", "revoked"]
    signed_at: datetime
    expires_at: datetime
    revoked_by: Optional[int]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class UATAcceptanceCreateRequest(BaseModel):
    expert_attestation_id: str = Field(min_length=36, max_length=36)
    customer_organization: str = Field(min_length=2, max_length=255)
    test_plan_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    test_evidence_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_reference: str = Field(min_length=1, max_length=2048)
    environment: Literal["customer_acceptance"] = "customer_acceptance"
    target_environment_id: str = Field(min_length=3, max_length=255)
    acceptance_statement: str = Field(min_length=50, max_length=20_000)
    expires_at: datetime

    model_config = {"extra": "forbid"}

    @field_validator("evidence_reference")
    @classmethod
    def evidence_url_is_https(cls, value: str) -> str:
        return _https(value)


class UATAcceptanceResponse(BaseModel):
    id: str
    scenario_id: int
    expert_attestation_id: str
    accepted_by: int
    customer_organization: str
    snapshot_hash: str
    test_plan_hash: str
    test_evidence_hash: str
    evidence_reference: str
    environment: str
    target_environment_id: str
    acceptance_statement: str
    status: Literal["accepted", "superseded", "withdrawn"]
    accepted_at: datetime
    expires_at: datetime
    withdrawn_at: Optional[datetime]
    withdrawal_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DeliveryArtifactCreateRequest(BaseModel):
    artifact_types: list[Literal["docx", "pdf", "audit_bundle"]] = Field(
        default_factory=lambda: ["docx", "pdf", "audit_bundle"],
        min_length=3,
        max_length=3,
    )

    model_config = {"extra": "forbid"}

    @field_validator("artifact_types")
    @classmethod
    def exact_delivery_set(cls, values: list[str]) -> list[str]:
        if set(values) != {"docx", "pdf", "audit_bundle"} or len(values) != 3:
            raise ValueError("交付制品必须同时冻结 docx、pdf 与 audit_bundle")
        return values


class DeliveryArtifactResponse(BaseModel):
    id: str
    scenario_id: int
    artifact_type: Literal["docx", "pdf", "audit_bundle"]
    snapshot_hash: str
    content_sha256: str
    content_length: int
    media_type: str
    filename: str
    renderer_version: str
    status: Literal["candidate", "superseded", "released", "revoked"]
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DeliveryArtifactManifestResponse(BaseModel):
    scenario_id: int
    snapshot_hash: str
    artifact_manifest: list[dict]
    artifact_manifest_hash: str


class SignatureDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=20, max_length=5000)

    model_config = {"extra": "forbid"}


class LegalContentCertificationCreateRequest(BaseModel):
    capability_pack_id: str = Field(min_length=1, max_length=128)
    capability_pack_version: str = Field(min_length=1, max_length=64)
    capability_pack_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    rules_artifact_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_artifact_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    gold_dataset_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_policy_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_run_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    regression_status: Literal["passed"]
    primary_credential_id: str = Field(min_length=36, max_length=36)
    secondary_credential_id: str = Field(min_length=36, max_length=36)
    primary_signature_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    primary_certificate_subject: str = Field(min_length=3, max_length=512)
    primary_certificate_serial: str = Field(min_length=3, max_length=255)
    primary_validation_url: str = Field(min_length=1, max_length=2048)
    primary_validation_report_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    secondary_signature_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    secondary_certificate_subject: str = Field(min_length=3, max_length=512)
    secondary_certificate_serial: str = Field(min_length=3, max_length=255)
    secondary_validation_url: str = Field(min_length=1, max_length=2048)
    secondary_validation_report_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    signed_content_manifest_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: str = Field(min_length=20, max_length=20_000)
    expires_at: datetime

    model_config = {"extra": "forbid"}

    @field_validator("primary_validation_url", "secondary_validation_url")
    @classmethod
    def signature_validation_is_official(cls, value: str) -> str:
        normalized = _https(value)
        if (urlparse(normalized).hostname or "").lower() != "validar.iti.gov.br":
            raise ValueError("内容发布签名必须引用 ITI VALIDAR 官方域名")
        return normalized

    @model_validator(mode="after")
    def reviewers_are_distinct(self):
        if self.primary_credential_id == self.secondary_credential_id:
            raise ValueError("生产法律内容必须由两名不同专家独立认证")
        return self


class LegalContentManifestRequest(BaseModel):
    capability_pack_id: str = Field(min_length=1, max_length=128)
    capability_pack_version: str = Field(min_length=1, max_length=64)
    capability_pack_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    rules_artifact_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_artifact_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    gold_dataset_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_policy_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_run_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    regression_status: Literal["passed"]
    primary_credential_id: str = Field(min_length=36, max_length=36)
    secondary_credential_id: str = Field(min_length=36, max_length=36)
    limitations: str = Field(min_length=20, max_length=20_000)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def reviewers_are_distinct(self):
        if self.primary_credential_id == self.secondary_credential_id:
            raise ValueError("生产法律内容必须由两名不同专家独立认证")
        return self


class LegalContentManifestResponse(BaseModel):
    manifest: dict
    manifest_hash: str


class LegalContentCertificationResponse(BaseModel):
    id: str
    capability_pack_id: str
    capability_pack_version: str
    capability_pack_hash: str
    rules_artifact_hash: str
    corpus_artifact_hash: str
    gold_dataset_sha256: str
    evaluation_policy_sha256: str
    evaluation_run_sha256: str
    regression_status: Literal["passed"]
    primary_credential_id: str
    secondary_credential_id: str
    primary_signature_hash: str
    primary_certificate_subject: str
    primary_certificate_serial: str
    primary_validation_url: str
    primary_validation_report_hash: str
    secondary_signature_hash: str
    secondary_certificate_subject: str
    secondary_certificate_serial: str
    secondary_validation_url: str
    secondary_validation_report_hash: str
    certification_manifest_hash: str
    limitations: str
    status: Literal["certified", "revoked"]
    certified_by: int
    certified_at: datetime
    expires_at: datetime
    revoked_by: Optional[int]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DeploymentEvidenceCreateRequest(BaseModel):
    legal_content_certification_id: str = Field(min_length=36, max_length=36)
    environment: Literal["staging", "production"]
    target_environment_id: str = Field(min_length=3, max_length=255)
    commit_sha: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    migration_head: str = Field(min_length=3, max_length=128)
    ci_run_url: str = Field(min_length=1, max_length=2048)
    artifact_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_receipt_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    sbom_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    security_evidence_url: str = Field(min_length=1, max_length=2048)
    security_evidence_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_url: str = Field(min_length=1, max_length=2048)
    provenance_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_probe_url: str = Field(min_length=1, max_length=2048)
    runtime_probe_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    backend_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    frontend_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    database_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    config_schema_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    capability_pack_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    rules_artifact_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_artifact_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    gold_dataset_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_policy_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_run_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    regression_status: Literal["passed"]
    verification_note: str = Field(min_length=20, max_length=10_000)
    expires_at: datetime

    model_config = {"extra": "forbid"}

    @field_validator("ci_run_url", "security_evidence_url", "provenance_url", "runtime_probe_url")
    @classmethod
    def evidence_urls_are_https(cls, value: str) -> str:
        return _https(value)

    @field_validator("commit_sha")
    @classmethod
    def commit_is_not_placeholder(cls, value: str) -> str:
        if len(set(value)) < 4:
            raise ValueError("commit SHA 不能使用重复字符占位值")
        return value

    @field_validator("backend_image_digest", "frontend_image_digest", "database_image_digest")
    @classmethod
    def image_digest_is_not_placeholder(cls, value: str) -> str:
        _non_placeholder_sha256(value.removeprefix("sha256:"))
        return value


class DeploymentEvidenceResponse(BaseModel):
    id: str
    legal_content_certification_id: str
    environment: Literal["staging", "production"]
    target_environment_id: str
    commit_sha: str
    migration_head: str
    ci_run_url: str
    artifact_sha256: str
    artifact_receipt_hash: Optional[str]
    sbom_sha256: str
    security_evidence_url: str
    security_evidence_sha256: Optional[str]
    provenance_url: str
    provenance_sha256: str
    runtime_probe_url: str
    runtime_probe_sha256: str
    backend_image_digest: str
    frontend_image_digest: str
    database_image_digest: str
    config_schema_sha256: str
    capability_pack_hash: str
    rules_artifact_hash: str
    corpus_artifact_hash: str
    gold_dataset_sha256: str
    evaluation_policy_sha256: str
    evaluation_run_sha256: str
    regression_status: Literal["passed"]
    verification_note: str
    status: Literal["verified", "revoked"]
    verified_by: int
    verified_at: datetime
    expires_at: datetime
    revoked_by: Optional[int]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DeliveryReleaseCreateRequest(BaseModel):
    expert_attestation_id: str = Field(min_length=36, max_length=36)
    uat_acceptance_id: str = Field(min_length=36, max_length=36)
    deployment_evidence_id: str = Field(min_length=36, max_length=36)
    release_note: str = Field(min_length=20, max_length=10_000)
    expires_at: datetime

    model_config = {"extra": "forbid"}


class DeliveryReleaseResponse(BaseModel):
    id: str
    scenario_id: int
    expert_attestation_id: str
    uat_acceptance_id: str
    deployment_evidence_id: str
    schema_version: str
    snapshot_hash: str
    release_hash: str
    release_note: str
    status: Literal["active", "superseded", "revoked"]
    released_by: int
    released_at: datetime
    expires_at: datetime
    revoked_by: Optional[int]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=5000)

    model_config = {"extra": "forbid"}


class DeliveryGateStatusResponse(BaseModel):
    schema_version: Literal["1.1"]
    scenario_id: int
    evaluated_at: datetime
    delivery_allowed: bool
    blocking_reasons: list[str]
    snapshot_hash: Optional[str]
    release_id: Optional[str]
    release_hash: Optional[str]
    release_schema_version: Optional[str]
    expert_attestation_id: Optional[str]
    uat_acceptance_id: Optional[str]
    deployment_evidence_id: Optional[str]
    boundary: str
