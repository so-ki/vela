from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.roles import ROLE_ADMIN, ROLE_LEGAL
from app.models.delivery_assurance import (
    DELIVERY_EVIDENCE_KINDS,
    DeploymentEvidence,
    DeliveryEvidenceObject,
    LegalContentCertification,
    LegalExpertCredential,
    ScenarioDeliveryRelease,
    ScenarioDeliveryArtifact,
    ScenarioExpertAttestation,
    ScenarioUATAcceptance,
)
from app.models.mechanism import ClaimRecord, CoverageProof
from app.models.legal_source_version import LegalChangeEvent, LegalSourceVersion
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.services.generation_guard import GenerationConfig, stable_hash
from app.services.upload_security import (
    MAX_DELIVERY_EVIDENCE_BYTES_PER_INSTANCE,
    MAX_DELIVERY_EVIDENCE_BYTES_PER_USER,
    MAX_DELIVERY_EVIDENCE_OBJECTS_PER_INSTANCE,
    MAX_DELIVERY_EVIDENCE_OBJECTS_PER_USER,
    MAX_FILE_BYTES,
    validate_evidence_container,
)
from app.services import mechanism_service
from app.services.answerability_gate_service import (
    AnswerabilityGateError,
    require_delivery_answerability,
)
from app.services.audit_bundle_service import build_audit_bundle
from app.services.export_service import build_sample_docx, build_sample_pdf


class DeliveryAssuranceError(ValueError):
    pass


class DeliveryAssuranceConflict(DeliveryAssuranceError):
    pass


class DeliveryAssurancePermissionError(PermissionError):
    pass


class DeliveryGateBlocked(DeliveryAssuranceError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        reasons = report.get("blocking_reasons") or ["delivery_release_missing"]
        super().__init__("真实客户交付门禁未通过：" + "; ".join(reasons))


_SCENARIO_EVIDENCE_KINDS = {
    "iti_signature_artifact",
    "iti_validation_report",
    "uat_test_plan",
    "uat_test_evidence",
}
_EVIDENCE_KINDS_BY_ROLE = {
    "business": {"uat_test_plan", "uat_test_evidence"},
    ROLE_LEGAL: {
        "oab_submission",
        "iti_signature_artifact",
        "iti_validation_report",
        "content_primary_signature",
        "content_primary_validation_report",
        "content_secondary_signature",
        "content_secondary_validation_report",
    },
    ROLE_ADMIN: {
        "oab_verification_report",
        "iti_validation_report",
        "content_primary_validation_report",
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
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_live(status: str, expires_at: datetime, *, now: datetime | None = None) -> bool:
    return status in {"verified", "active", "accepted", "certified"} and _as_utc(
        expires_at
    ) > (now or _now())


def create_delivery_evidence_object(
    db: Session,
    *,
    evidence_kind: str,
    filename: str,
    media_type: str,
    content: bytes,
    source_url: str | None,
    expires_at: datetime | None,
    user: User,
    scenario: InvestigationScenario | None = None,
) -> DeliveryEvidenceObject:
    if evidence_kind not in DELIVERY_EVIDENCE_KINDS:
        raise DeliveryAssuranceError("未知的客户交付证据类型")
    if evidence_kind not in _EVIDENCE_KINDS_BY_ROLE.get(user.role, set()):
        raise DeliveryAssurancePermissionError("当前角色不得上传该类客户交付证据")
    requires_scenario = evidence_kind in _SCENARIO_EVIDENCE_KINDS
    if requires_scenario != (scenario is not None):
        raise DeliveryAssuranceError("该证据类型的场景绑定不正确")
    if scenario is not None:
        if user.role == "business" and scenario.user_id != user.id:
            raise DeliveryAssurancePermissionError("只能为本人提交的场景上传 UAT 证据")
        if user.role == ROLE_LEGAL and evidence_kind == "iti_signature_artifact":
            _require_scenario_counsel(scenario, user)
    if not content:
        raise DeliveryAssuranceError("证据原件不能为空")
    if len(content) > MAX_FILE_BYTES:
        raise DeliveryAssuranceError("单个证据文件不能超过 25MB")
    try:
        validate_evidence_container(filename, content)
    except ValueError as exc:
        raise DeliveryAssuranceError(str(exc)) from exc
    suffix = Path(filename).suffix.lower()
    signature_kinds = {
        "iti_signature_artifact",
        "content_primary_signature",
        "content_secondary_signature",
    }
    if evidence_kind in signature_kinds and suffix not in {".p7s", ".pdf", ".sig"}:
        raise DeliveryAssuranceError("数字签名原件必须是 P7S、PDF 或 SIG")
    if evidence_kind in {"build_artifact_descriptor", "build_artifact_receipt"} and suffix != ".json":
        raise DeliveryAssuranceError("构建描述符与回执必须是 JSON")
    now = _now()
    if expires_at is not None and _as_utc(expires_at) <= now:
        raise DeliveryAssuranceError("证据原件有效期必须晚于当前时间")
    official_report_kinds = {
        "oab_verification_report",
        "iti_validation_report",
        "content_primary_validation_report",
        "content_secondary_validation_report",
    }
    if evidence_kind in official_report_kinds and not source_url:
        raise DeliveryAssuranceError("官方核验报告必须记录官方 HTTPS 来源")
    if source_url:
        parsed_source = urlparse(source_url)
        host = (parsed_source.hostname or "").lower().rstrip(".")
        if parsed_source.scheme != "https" or not host:
            raise DeliveryAssuranceError("证据来源必须是 HTTPS URL")
        if evidence_kind == "oab_verification_report" and host not in {
            "consulta.oab.org.br",
            "confirmadv.oab.org.br",
        }:
            raise DeliveryAssuranceError("OAB 核验证据来源必须是 CNA 或 ConfirmADV")
        if evidence_kind in {
            "iti_validation_report",
            "content_primary_validation_report",
            "content_secondary_validation_report",
        } and host != "validar.iti.gov.br":
            raise DeliveryAssuranceError("签名核验证据来源必须是 ITI VALIDAR")
    # Serialize quota checks for one uploader on databases that support row
    # locks. SQLite ignores FOR UPDATE but still serializes writes.
    db.query(User.id).filter(User.id == user.id).with_for_update().one()
    digest = hashlib.sha256(content).hexdigest()
    existing = (
        db.query(DeliveryEvidenceObject)
        .filter(
            DeliveryEvidenceObject.evidence_kind == evidence_kind,
            DeliveryEvidenceObject.content_sha256 == digest,
        )
        .first()
    )
    if existing is not None:
        if (
            existing.status == "available"
            and existing.uploaded_by == user.id
            and existing.scenario_id == (scenario.id if scenario else None)
        ):
            return existing
        raise DeliveryAssuranceConflict("相同证据 bytes 已由其他主体或状态记录")
    user_count, user_bytes = (
        db.query(
            func.count(DeliveryEvidenceObject.id),
            func.coalesce(func.sum(DeliveryEvidenceObject.content_length), 0),
        )
        .filter(DeliveryEvidenceObject.uploaded_by == user.id)
        .one()
    )
    if (
        int(user_count) >= MAX_DELIVERY_EVIDENCE_OBJECTS_PER_USER
        or int(user_bytes) + len(content) > MAX_DELIVERY_EVIDENCE_BYTES_PER_USER
    ):
        raise DeliveryAssuranceError("当前上传人的证据对象或总字节配额已用尽")
    instance_count, instance_bytes = db.query(
        func.count(DeliveryEvidenceObject.id),
        func.coalesce(func.sum(DeliveryEvidenceObject.content_length), 0),
    ).one()
    if (
        int(instance_count) >= MAX_DELIVERY_EVIDENCE_OBJECTS_PER_INSTANCE
        or int(instance_bytes) + len(content)
        > MAX_DELIVERY_EVIDENCE_BYTES_PER_INSTANCE
    ):
        raise DeliveryAssuranceError("当前实例的证据对象或总字节配额已用尽")
    evidence = DeliveryEvidenceObject(
        id=str(uuid4()),
        scenario_id=scenario.id if scenario else None,
        evidence_kind=evidence_kind,
        filename=filename,
        media_type=media_type,
        content_sha256=digest,
        content_length=len(content),
        content=content,
        source_url=source_url,
        status="available",
        uploaded_by=user.id,
        uploaded_at=now,
        expires_at=expires_at,
    )
    db.add(evidence)
    db.flush()
    return evidence


def require_delivery_evidence_object(
    db: Session,
    *,
    evidence_kind: str,
    content_sha256: str,
    scenario_id: int | None = None,
    uploaded_by: int | None = None,
    now: datetime | None = None,
) -> DeliveryEvidenceObject:
    evidence = (
        db.query(DeliveryEvidenceObject)
        .filter(
            DeliveryEvidenceObject.evidence_kind == evidence_kind,
            DeliveryEvidenceObject.content_sha256 == content_sha256,
        )
        .first()
    )
    checked_at = now or _now()
    if (
        evidence is None
        or evidence.status != "available"
        or evidence.scenario_id != scenario_id
        or (uploaded_by is not None and evidence.uploaded_by != uploaded_by)
        or (evidence.expires_at is not None and _as_utc(evidence.expires_at) <= checked_at)
        or hashlib.sha256(evidence.content).hexdigest() != evidence.content_sha256
        or len(evidence.content) != evidence.content_length
    ):
        raise DeliveryAssuranceError(
            f"缺少当前有效且 bytes 可重算的 {evidence_kind} 证据原件"
        )
    return evidence


def _require_expiry_covered_by_evidence(
    expires_at: datetime,
    evidence_objects: list[DeliveryEvidenceObject],
) -> None:
    if any(
        item.expires_at is not None
        and _as_utc(expires_at) > _as_utc(item.expires_at)
        for item in evidence_objects
    ):
        raise DeliveryAssuranceError("业务证据有效期不得超过所引用证据原件有效期")


def _require_release_evidence_objects(
    db: Session,
    *,
    scenario: InvestigationScenario,
    attestation: ScenarioExpertAttestation,
    acceptance: ScenarioUATAcceptance,
    deployment: DeploymentEvidence,
    content_certification: LegalContentCertification,
    scenario_credential: LegalExpertCredential,
    primary_credential: LegalExpertCredential,
    secondary_credential: LegalExpertCredential,
    now: datetime,
) -> list[DeliveryEvidenceObject]:
    objects: list[DeliveryEvidenceObject] = []
    credential_records = {
        item.id: item
        for item in (scenario_credential, primary_credential, secondary_credential)
    }
    for credential in credential_records.values():
        objects.append(
            require_delivery_evidence_object(
                db,
                evidence_kind="oab_submission",
                content_sha256=credential.submitted_evidence_hash,
                uploaded_by=credential.user_id,
                now=now,
            )
        )
        if credential.verification_evidence_hash is None or credential.verified_by is None:
            raise DeliveryAssuranceError("律师凭证缺少可追溯的 OAB 核验证据")
        objects.append(
            require_delivery_evidence_object(
                db,
                evidence_kind="oab_verification_report",
                content_sha256=credential.verification_evidence_hash,
                uploaded_by=credential.verified_by,
                now=now,
            )
        )
    objects.extend(
        [
            require_delivery_evidence_object(
                db,
                evidence_kind="iti_signature_artifact",
                content_sha256=attestation.signature_artifact_hash,
                scenario_id=scenario.id,
                uploaded_by=attestation.signed_by,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="iti_validation_report",
                content_sha256=attestation.signature_validation_report_hash,
                scenario_id=scenario.id,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="uat_test_plan",
                content_sha256=acceptance.test_plan_hash,
                scenario_id=scenario.id,
                uploaded_by=acceptance.accepted_by,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="uat_test_evidence",
                content_sha256=acceptance.test_evidence_hash,
                scenario_id=scenario.id,
                uploaded_by=acceptance.accepted_by,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="content_primary_signature",
                content_sha256=content_certification.primary_signature_hash,
                uploaded_by=primary_credential.user_id,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="content_primary_validation_report",
                content_sha256=content_certification.primary_validation_report_hash,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="content_secondary_signature",
                content_sha256=content_certification.secondary_signature_hash,
                uploaded_by=secondary_credential.user_id,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="content_secondary_validation_report",
                content_sha256=content_certification.secondary_validation_report_hash,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="gold_dataset",
                content_sha256=deployment.gold_dataset_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="evaluation_policy",
                content_sha256=deployment.evaluation_policy_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="evaluation_run",
                content_sha256=deployment.evaluation_run_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="build_artifact_descriptor",
                content_sha256=deployment.artifact_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="build_artifact_receipt",
                content_sha256=deployment.artifact_receipt_hash,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="sbom",
                content_sha256=deployment.sbom_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="security_report",
                content_sha256=deployment.security_evidence_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="provenance",
                content_sha256=deployment.provenance_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="runtime_probe",
                content_sha256=deployment.runtime_probe_sha256,
                now=now,
            ),
            require_delivery_evidence_object(
                db,
                evidence_kind="config_schema",
                content_sha256=deployment.config_schema_sha256,
                now=now,
            ),
        ]
    )
    unique = {item.id: item for item in objects}
    return list(unique.values())


def revoke_delivery_evidence_object(
    db: Session,
    *,
    evidence: DeliveryEvidenceObject,
    reason: str,
    user: User,
) -> DeliveryEvidenceObject:
    if user.id != evidence.uploaded_by and user.role != ROLE_ADMIN:
        raise DeliveryAssurancePermissionError("只有原上传人或管理员可撤回证据原件")
    if evidence.status != "available":
        raise DeliveryAssuranceError("只有 available 证据原件可被撤回")
    now = _now()
    result = db.execute(
        update(DeliveryEvidenceObject)
        .where(
            DeliveryEvidenceObject.id == evidence.id,
            DeliveryEvidenceObject.status == "available",
        )
        .values(
            status="revoked",
            revoked_by=user.id,
            revoked_at=now,
            revocation_reason=reason.strip(),
        )
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("证据原件状态已变化，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(DeliveryEvidenceObject, evidence.id)


def _require_admin(user: User) -> None:
    if user.role != ROLE_ADMIN:
        raise DeliveryAssurancePermissionError("只有发布管理员可执行该操作")


def _require_legal(user: User) -> None:
    if user.role != ROLE_LEGAL:
        raise DeliveryAssurancePermissionError(
            "只有独立 legal 角色可作为法律专家，管理员不得代签"
        )


def _scenario_counsel_id(scenario: InvestigationScenario) -> int:
    review = (
        (scenario.checklist.payload or {}).get("review") if scenario.checklist else None
    )
    finalized_by_id = (review or {}).get("finalized_by_id")
    if isinstance(finalized_by_id, bool) or not isinstance(finalized_by_id, int):
        raise DeliveryAssuranceError("法务定稿缺少可审计的 finalized_by_id")
    return finalized_by_id


def _require_scenario_counsel(scenario: InvestigationScenario, user: User) -> None:
    _require_legal(user)
    if user.id != _scenario_counsel_id(scenario):
        raise DeliveryAssurancePermissionError(
            "只有该场景法务定稿的主审律师可冻结或签署交付制品"
        )


def _jurisdiction_matches(scenario_country: str, jurisdiction: str) -> bool:
    aliases = {
        "br": "brazil",
        "bra": "brazil",
        "brasil": "brazil",
        "brazil": "brazil",
    }
    country = aliases.get(
        scenario_country.strip().lower(), scenario_country.strip().lower()
    )
    expert = aliases.get(jurisdiction.strip().lower(), jurisdiction.strip().lower())
    return country == expert


def _require_brazil_official_registry_url(value: str) -> None:
    host = (urlparse(value).hostname or "").lower().rstrip(".")
    if host not in {"consulta.oab.org.br", "confirmadv.oab.org.br"}:
        raise DeliveryAssuranceError(
            "巴西律师凭证必须引用 OAB CNA 或 ConfirmADV 官方域名"
        )


def _content_certification_manifest(
    certification: LegalContentCertification,
) -> dict[str, Any]:
    return build_legal_content_manifest(
        capability_pack_id=certification.capability_pack_id,
        capability_pack_version=certification.capability_pack_version,
        capability_pack_hash=certification.capability_pack_hash,
        rules_artifact_hash=certification.rules_artifact_hash,
        corpus_artifact_hash=certification.corpus_artifact_hash,
        gold_dataset_sha256=certification.gold_dataset_sha256,
        evaluation_policy_sha256=certification.evaluation_policy_sha256,
        evaluation_run_sha256=certification.evaluation_run_sha256,
        regression_status=certification.regression_status,
        primary_credential_id=certification.primary_credential_id,
        secondary_credential_id=certification.secondary_credential_id,
        limitations=certification.limitations,
    )


def _content_certification_signers_are_current(
    db: Session,
    certification: LegalContentCertification,
    *,
    now: datetime,
) -> bool:
    primary = db.get(LegalExpertCredential, certification.primary_credential_id)
    secondary = db.get(LegalExpertCredential, certification.secondary_credential_id)
    if primary is None or secondary is None:
        return False
    if primary.id == secondary.id or primary.user_id == secondary.user_id:
        return False
    for credential, certificate_subject in (
        (primary, certification.primary_certificate_subject),
        (secondary, certification.secondary_certificate_subject),
    ):
        holder = db.get(User, credential.user_id)
        if (
            holder is None
            or holder.role != ROLE_LEGAL
            or credential.registration_status != "regular"
            or credential.valid_until is None
            or not _is_live(credential.status, credential.valid_until, now=now)
            or not _jurisdiction_matches("brazil", credential.jurisdiction)
            or credential.holder_name.casefold() not in certificate_subject.casefold()
        ):
            return False
    return True


def require_current_legal_content_signers(
    db: Session,
    *,
    primary_credential: LegalExpertCredential,
    secondary_credential: LegalExpertCredential,
    now: datetime | None = None,
) -> None:
    checked_at = now or _now()
    if (
        primary_credential.id == secondary_credential.id
        or primary_credential.user_id == secondary_credential.user_id
    ):
        raise DeliveryAssuranceError("生产法律内容必须由两名不同律师独立认证")
    for credential in (primary_credential, secondary_credential):
        holder = db.get(User, credential.user_id)
        if (
            holder is None
            or holder.role != ROLE_LEGAL
            or credential.registration_status != "regular"
            or credential.valid_until is None
            or not _is_live(credential.status, credential.valid_until, now=checked_at)
        ):
            raise DeliveryAssuranceError(
                "双专家认证引用了无效、过期、非 regular 或非 legal 凭证"
            )
        if not _jurisdiction_matches("brazil", credential.jurisdiction):
            raise DeliveryAssuranceError("巴西法律内容认证必须由巴西法域律师完成")


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def _credential_evidence(credential: LegalExpertCredential) -> dict[str, Any]:
    return {
        "id": credential.id,
        "user_id": credential.user_id,
        "holder_name": credential.holder_name,
        "jurisdiction": credential.jurisdiction,
        "authority": credential.authority,
        "registration_number": credential.registration_number,
        "official_register_url": credential.official_register_url,
        "submitted_evidence_hash": credential.submitted_evidence_hash,
        "verification_reference": credential.verification_reference,
        "verification_evidence_hash": credential.verification_evidence_hash,
        "registration_status": credential.registration_status,
        "decision_note": credential.decision_note,
        "status": credential.status,
        "revision": credential.revision,
        "verified_by": credential.verified_by,
        "verified_at": _iso(credential.verified_at),
        "valid_until": _iso(credential.valid_until),
    }


def _attestation_evidence(attestation: ScenarioExpertAttestation) -> dict[str, Any]:
    return {
        "id": attestation.id,
        "scenario_id": attestation.scenario_id,
        "credential_id": attestation.credential_id,
        "signed_by": attestation.signed_by,
        "snapshot_hash": attestation.snapshot_hash,
        "artifact_manifest_hash": attestation.artifact_manifest_hash,
        "signature_format": attestation.signature_format,
        "signature_artifact_hash": attestation.signature_artifact_hash,
        "signature_validation_url": attestation.signature_validation_url,
        "signature_validation_report_hash": attestation.signature_validation_report_hash,
        "signature_validation_status": attestation.signature_validation_status,
        "signature_verified_by": attestation.signature_verified_by,
        "signature_verified_at": _iso(attestation.signature_verified_at),
        "signature_verification_note": attestation.signature_verification_note,
        "certificate_subject": attestation.certificate_subject,
        "certificate_serial": attestation.certificate_serial,
        "certificate_valid_until": _iso(attestation.certificate_valid_until),
        "statement": attestation.statement,
        "limitations": attestation.limitations,
        "status": attestation.status,
        "signed_at": _iso(attestation.signed_at),
        "expires_at": _iso(attestation.expires_at),
    }


def _uat_evidence(acceptance: ScenarioUATAcceptance) -> dict[str, Any]:
    return {
        "id": acceptance.id,
        "scenario_id": acceptance.scenario_id,
        "expert_attestation_id": acceptance.expert_attestation_id,
        "accepted_by": acceptance.accepted_by,
        "customer_organization": acceptance.customer_organization,
        "snapshot_hash": acceptance.snapshot_hash,
        "test_plan_hash": acceptance.test_plan_hash,
        "test_evidence_hash": acceptance.test_evidence_hash,
        "evidence_reference": acceptance.evidence_reference,
        "environment": acceptance.environment,
        "target_environment_id": acceptance.target_environment_id,
        "acceptance_statement": acceptance.acceptance_statement,
        "status": acceptance.status,
        "accepted_at": _iso(acceptance.accepted_at),
        "expires_at": _iso(acceptance.expires_at),
    }


def _content_certification_evidence(
    certification: LegalContentCertification,
) -> dict[str, Any]:
    return {
        "id": certification.id,
        "manifest_hash": certification.certification_manifest_hash,
        "primary_credential_id": certification.primary_credential_id,
        "secondary_credential_id": certification.secondary_credential_id,
        "primary_signature_hash": certification.primary_signature_hash,
        "primary_certificate_subject": certification.primary_certificate_subject,
        "primary_certificate_serial": certification.primary_certificate_serial,
        "primary_validation_url": certification.primary_validation_url,
        "primary_validation_report_hash": certification.primary_validation_report_hash,
        "secondary_signature_hash": certification.secondary_signature_hash,
        "secondary_certificate_subject": certification.secondary_certificate_subject,
        "secondary_certificate_serial": certification.secondary_certificate_serial,
        "secondary_validation_url": certification.secondary_validation_url,
        "secondary_validation_report_hash": certification.secondary_validation_report_hash,
        "status": certification.status,
        "certified_by": certification.certified_by,
        "certified_at": _iso(certification.certified_at),
        "expires_at": _iso(certification.expires_at),
    }


def _deployment_evidence_manifest(deployment: DeploymentEvidence) -> dict[str, Any]:
    fields = (
        "id",
        "legal_content_certification_id",
        "environment",
        "target_environment_id",
        "commit_sha",
        "migration_head",
        "ci_run_url",
        "artifact_sha256",
        "artifact_receipt_hash",
        "sbom_sha256",
        "security_evidence_url",
        "security_evidence_sha256",
        "provenance_url",
        "provenance_sha256",
        "runtime_probe_url",
        "runtime_probe_sha256",
        "backend_image_digest",
        "frontend_image_digest",
        "database_image_digest",
        "config_schema_sha256",
        "capability_pack_hash",
        "rules_artifact_hash",
        "corpus_artifact_hash",
        "gold_dataset_sha256",
        "evaluation_policy_sha256",
        "evaluation_run_sha256",
        "regression_status",
        "verification_note",
        "status",
        "verified_by",
    )
    result = {field: getattr(deployment, field) for field in fields}
    result.update(
        {
            "verified_at": _iso(deployment.verified_at),
            "expires_at": _iso(deployment.expires_at),
        }
    )
    return result


def _delivery_evidence_manifest(
    evidence_objects: list[DeliveryEvidenceObject],
) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "scenario_id": item.scenario_id,
            "evidence_kind": item.evidence_kind,
            "filename": item.filename,
            "media_type": item.media_type,
            "content_sha256": item.content_sha256,
            "content_length": item.content_length,
            "source_url": item.source_url,
            "status": item.status,
            "uploaded_by": item.uploaded_by,
            "uploaded_at": _iso(item.uploaded_at),
            "expires_at": _iso(item.expires_at),
        }
        for item in sorted(evidence_objects, key=lambda value: value.id)
    ]


def _release_body(
    *,
    scenario_id: int,
    snapshot_hash: str,
    attestation: ScenarioExpertAttestation,
    acceptance: ScenarioUATAcceptance,
    deployment: DeploymentEvidence,
    content_certification: LegalContentCertification,
    scenario_credential: LegalExpertCredential,
    primary_credential: LegalExpertCredential,
    secondary_credential: LegalExpertCredential,
    evidence_objects: list[DeliveryEvidenceObject],
    release_note: str,
    released_by: int,
    released_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "scenario_id": scenario_id,
        "snapshot_hash": snapshot_hash,
        "expert_attestation_id": attestation.id,
        "expert_attestation_evidence_hash": stable_hash(
            _attestation_evidence(attestation)
        ),
        "artifact_manifest_hash": attestation.artifact_manifest_hash,
        "uat_acceptance_id": acceptance.id,
        "uat_evidence_hash": stable_hash(_uat_evidence(acceptance)),
        "deployment_evidence_id": deployment.id,
        "deployment_evidence_hash": stable_hash(
            _deployment_evidence_manifest(deployment)
        ),
        "legal_content_certification_id": content_certification.id,
        "legal_content_certification_evidence_hash": stable_hash(
            _content_certification_evidence(content_certification)
        ),
        "scenario_credential_evidence_hash": stable_hash(
            _credential_evidence(scenario_credential)
        ),
        "primary_content_credential_evidence_hash": stable_hash(
            _credential_evidence(primary_credential)
        ),
        "secondary_content_credential_evidence_hash": stable_hash(
            _credential_evidence(secondary_credential)
        ),
        "delivery_evidence_manifest_hash": stable_hash(
            _delivery_evidence_manifest(evidence_objects)
        ),
        "release_note_hash": stable_hash({"release_note": release_note.strip()}),
        "released_by": released_by,
        "released_at": _as_utc(released_at).isoformat(),
        "expires_at": _as_utc(expires_at).isoformat(),
    }


def build_legal_content_manifest(
    *,
    capability_pack_id: str,
    capability_pack_version: str,
    capability_pack_hash: str,
    rules_artifact_hash: str,
    corpus_artifact_hash: str,
    gold_dataset_sha256: str,
    evaluation_policy_sha256: str,
    evaluation_run_sha256: str,
    regression_status: str,
    primary_credential_id: str,
    secondary_credential_id: str,
    limitations: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "capability_pack_id": capability_pack_id.strip(),
        "capability_pack_version": capability_pack_version.strip(),
        "capability_pack_hash": capability_pack_hash,
        "rules_artifact_hash": rules_artifact_hash,
        "corpus_artifact_hash": corpus_artifact_hash,
        "gold_dataset_sha256": gold_dataset_sha256,
        "evaluation_policy_sha256": evaluation_policy_sha256,
        "evaluation_run_sha256": evaluation_run_sha256,
        "regression_status": regression_status,
        "primary_credential_id": primary_credential_id,
        "secondary_credential_id": secondary_credential_id,
        "limitations": limitations.strip(),
    }


def _active_legal_changes_after(
    db: Session, certified_at: datetime
) -> list[LegalChangeEvent]:
    """Conservative pilot policy: any later approved content change forces revalidation."""

    return (
        db.query(LegalChangeEvent)
        .join(
            LegalSourceVersion,
            LegalSourceVersion.id == LegalChangeEvent.source_version_id,
        )
        .filter(
            LegalSourceVersion.status == "active",
            LegalChangeEvent.change_type == "content_changed",
            LegalChangeEvent.detected_at > certified_at,
        )
        .order_by(LegalChangeEvent.detected_at.asc())
        .limit(20)
        .all()
    )


def _current_mechanism_snapshot(
    db: Session,
    scenario: InvestigationScenario,
) -> tuple[dict[str, Any], Any, list[ClaimRecord], CoverageProof]:
    try:
        gate = require_delivery_answerability(db, scenario=scenario)
    except AnswerabilityGateError as exc:
        raise DeliveryAssuranceError(
            f"Answerability Gate 未通过：{exc.message} ({', '.join(exc.reason_codes)})"
        ) from exc
    latest = mechanism_service.latest_compilation(db, scenario.id)
    if latest is None:
        raise DeliveryAssuranceError("缺少当前 ClaimCompilation")
    compilation, claims = latest

    claims_snapshot = [
        {
            "id": claim.id,
            "checklist_code": claim.checklist_code,
            "statement": claim.statement,
            "status": claim.status,
            "fact_refs": list(claim.fact_refs or []),
            "evidence_refs": list(claim.evidence_refs or []),
            "confirmed_by": claim.confirmed_by,
            "confirmed_at": _as_utc(claim.confirmed_at).isoformat()
            if claim.confirmed_at
            else None,
            "confirmation_note": claim.confirmation_note,
        }
        for claim in sorted(claims, key=lambda item: item.checklist_code)
    ]
    proof = (
        db.query(CoverageProof)
        .filter(
            CoverageProof.scenario_id == scenario.id,
            CoverageProof.compilation_id == compilation.id,
        )
        .order_by(CoverageProof.created_at.desc())
        .first()
    )
    if proof is None or proof.id != gate["coverage_proof_id"]:
        raise DeliveryAssuranceError(
            "Answerability Gate 与 CoverageProof 读取结果不一致"
        )

    mechanism = {
        "compilation_id": compilation.id,
        "compiler_version": compilation.compiler_version,
        "compiler_input_hash": compilation.input_hash,
        "compiler_output_hash": compilation.output_hash,
        "confirmed_claims_hash": stable_hash(claims_snapshot),
        "claim_count": len(claims),
        "coverage_proof_id": proof.id,
        "coverage_proof_hash": proof.proof_hash,
        "coverage_denominator_hash": proof.denominator_hash,
        "answerability_gate": gate,
    }
    return mechanism, compilation, claims, proof


def build_delivery_snapshot(
    db: Session,
    *,
    scenario: InvestigationScenario,
    generation_config: GenerationConfig,
) -> dict[str, Any]:
    if scenario.is_demo or scenario.checklist is None:
        raise DeliveryAssuranceError("演示场景或无清单场景不得进入客户交付")
    review = (scenario.checklist.payload or {}).get("review") or {}
    if review.get("status") != "approved" or not review.get("finalized_at"):
        raise DeliveryAssuranceError("只有法务复核结论为 approved 的定稿可进入客户交付")
    finalized_by_id = _scenario_counsel_id(scenario)
    finalizer = db.get(User, finalized_by_id)
    if finalizer is None or finalizer.role != ROLE_LEGAL:
        raise DeliveryAssuranceError("法务定稿主审必须保持独立 legal 角色")
    if any(
        bool(item.get("external_counsel_required"))
        for item in (review.get("items") or [])
    ):
        raise DeliveryAssuranceError(
            "仍存在 external_counsel_required 条目，禁止客户交付"
        )
    if generation_config.scenario_id != scenario.id:
        raise DeliveryAssuranceError("冻结生成配置与场景错绑")

    mechanism, _compilation, _claims, _proof = _current_mechanism_snapshot(db, scenario)
    payload = scenario.checklist.payload or {}
    snapshot = {
        "schema_version": "1.0",
        "scenario_id": scenario.id,
        "scope_snapshot_hash": scenario.scope_snapshot_hash,
        "checklist_id": scenario.checklist.id,
        "checklist_revision": scenario.checklist.revision,
        "checklist_payload_hash": stable_hash(payload),
        "review": {
            "status": review.get("status"),
            "revision": review.get("revision"),
            "finalized_at": review.get("finalized_at"),
            "finalized_by_id": review.get("finalized_by_id"),
        },
        "generation": {
            "attempt_id": generation_config.attempt_id,
            "snapshot_hash": generation_config.snapshot_hash,
            "config_hash": generation_config.config_hash,
            "generation_input_hash": generation_config.generation_input_hash,
            "capability_pack_id": generation_config.capability_pack_id,
            "capability_pack_version": generation_config.capability_pack_version,
            "capability_pack_hash": generation_config.capability_pack_hash,
            "rules_artifact_id": generation_config.rules_artifact_id,
            "rules_artifact_version": generation_config.rules_artifact_version,
            "rules_artifact_hash": generation_config.rules_artifact_hash,
            "corpus_artifact_id": generation_config.corpus_artifact_id,
            "corpus_artifact_version": generation_config.corpus_artifact_version,
            "corpus_artifact_hash": generation_config.corpus_artifact_hash,
        },
        "mechanism": mechanism,
    }
    if not snapshot["scope_snapshot_hash"]:
        raise DeliveryAssuranceError("缺少冻结 scope_snapshot_hash")
    return snapshot


def submit_credential(
    db: Session,
    *,
    user: User,
    holder_name: str,
    jurisdiction: str,
    authority: str,
    registration_number: str,
    official_register_url: str,
    submitted_evidence_hash: str,
) -> LegalExpertCredential:
    _require_legal(user)
    if _jurisdiction_matches("brazil", jurisdiction):
        _require_brazil_official_registry_url(official_register_url)
    require_delivery_evidence_object(
        db,
        evidence_kind="oab_submission",
        content_sha256=submitted_evidence_hash,
        uploaded_by=user.id,
    )
    if (
        db.query(LegalExpertCredential.id)
        .filter(
            LegalExpertCredential.submitted_evidence_hash == submitted_evidence_hash
        )
        .first()
        is not None
    ):
        raise DeliveryAssuranceError("同一 OAB 申报原件不得重新绑定其他执业凭证")
    credential = LegalExpertCredential(
        id=str(uuid4()),
        user_id=user.id,
        holder_name=holder_name.strip(),
        jurisdiction=jurisdiction.strip(),
        authority=authority.strip(),
        registration_number=registration_number.strip(),
        official_register_url=official_register_url,
        submitted_evidence_hash=submitted_evidence_hash,
        status="pending",
        created_by=user.id,
    )
    db.add(credential)
    db.flush()
    return credential


def decide_credential(
    db: Session,
    *,
    credential: LegalExpertCredential,
    decision: str,
    expected_revision: int,
    note: str,
    user: User,
    verification_reference: str | None = None,
    verification_evidence_hash: str | None = None,
    registration_status: str | None = None,
    valid_until: datetime | None = None,
) -> LegalExpertCredential:
    _require_admin(user)
    if user.id == credential.user_id:
        raise DeliveryAssurancePermissionError("凭证持有人不得核验自己的执业凭证")
    transitions = {"pending": {"verified", "rejected"}, "verified": {"revoked"}}
    if expected_revision != credential.revision:
        raise DeliveryAssuranceConflict("执业凭证已被其他会话更新，请刷新后重试")
    if decision not in transitions.get(credential.status, set()):
        raise DeliveryAssuranceError(
            f"执业凭证不得从 {credential.status} 变更为 {decision}"
        )
    now = _now()
    values: dict[str, Any] = {
        "status": decision,
        "decision_note": note.strip(),
        "revision": credential.revision + 1,
        "updated_at": now,
    }
    if decision == "verified":
        if (
            not verification_reference
            or not verification_evidence_hash
            or valid_until is None
        ):
            raise DeliveryAssuranceError(
                "核验通过必须提交官方核验引用、证据哈希和有效期"
            )
        if credential.jurisdiction.strip().lower() in {"br", "bra", "brasil", "brazil"}:
            _require_brazil_official_registry_url(verification_reference)
        if registration_status != "regular":
            raise DeliveryAssuranceError("只有 OAB 状态 regular 的凭证可核验通过")
        if _as_utc(valid_until) <= now:
            raise DeliveryAssuranceError("凭证有效期必须晚于当前时间")
        verification_evidence = require_delivery_evidence_object(
            db,
            evidence_kind="oab_verification_report",
            content_sha256=verification_evidence_hash,
            uploaded_by=user.id,
            now=now,
        )
        reused_evidence = (
            db.query(LegalExpertCredential.id)
            .filter(
                LegalExpertCredential.id != credential.id,
                LegalExpertCredential.verification_evidence_hash
                == verification_evidence_hash,
            )
            .first()
        )
        if reused_evidence is not None:
            raise DeliveryAssuranceError("同一 OAB 核验报告不得复用于其他执业凭证")
        _require_expiry_covered_by_evidence(valid_until, [verification_evidence])
        values.update(
            {
                "verification_reference": verification_reference,
                "verification_evidence_hash": verification_evidence_hash,
                "registration_status": registration_status,
                "verified_by": user.id,
                "verified_at": now,
                "valid_until": valid_until,
            }
        )
    elif decision == "revoked":
        values.update({"revoked_by": user.id, "revoked_at": now})
    result = db.execute(
        update(LegalExpertCredential)
        .where(
            LegalExpertCredential.id == credential.id,
            LegalExpertCredential.status == credential.status,
            LegalExpertCredential.revision == credential.revision,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("执业凭证已被其他会话更新，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(LegalExpertCredential, credential.id)


def create_delivery_artifacts(
    db: Session,
    *,
    scenario: InvestigationScenario,
    generation_config: GenerationConfig,
    user: User,
) -> list[ScenarioDeliveryArtifact]:
    """Freeze exact bytes. The endpoint returns metadata only until a release is active."""

    _require_scenario_counsel(scenario, user)
    snapshot = build_delivery_snapshot(
        db, scenario=scenario, generation_config=generation_config
    )
    snapshot_hash = stable_hash(snapshot)
    answerability = snapshot["mechanism"]["answerability_gate"]
    bundle = build_audit_bundle(scenario, generation_config=generation_config)
    bundle["bundle_version"] = "1.4"
    bundle["answerability_gate"] = answerability
    bundle["delivery_snapshot_hash"] = snapshot_hash
    audit_bytes = json.dumps(
        bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    docx_bytes, docx_name = build_sample_docx(
        scenario, generation_config=generation_config
    )
    pdf_bytes, pdf_name = build_sample_pdf(
        scenario, generation_config=generation_config
    )
    candidates = [
        (
            "docx",
            docx_bytes,
            docx_name,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("pdf", pdf_bytes, pdf_name, "application/pdf"),
        (
            "audit_bundle",
            audit_bytes,
            f"vela-{scenario.id}-audit-bundle.json",
            "application/json",
        ),
    ]
    db.execute(
        update(ScenarioDeliveryArtifact)
        .where(
            ScenarioDeliveryArtifact.scenario_id == scenario.id,
            ScenarioDeliveryArtifact.status == "candidate",
        )
        .values(status="superseded")
    )
    artifacts: list[ScenarioDeliveryArtifact] = []
    renderer_version = (
        f"vela-export-1:{generation_config.capability_pack_hash}:"
        f"{generation_config.output_profile.get('export_template', 'unknown')}"
    )
    for artifact_type, content, filename, media_type in candidates:
        artifact = ScenarioDeliveryArtifact(
            id=str(uuid4()),
            scenario_id=scenario.id,
            artifact_type=artifact_type,
            snapshot_hash=snapshot_hash,
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_length=len(content),
            media_type=media_type,
            filename=filename,
            renderer_version=renderer_version,
            content=content,
            status="candidate",
            created_by=user.id,
        )
        db.add(artifact)
        artifacts.append(artifact)
    db.flush()
    return artifacts


def _artifact_manifest(
    db: Session,
    *,
    scenario_id: int,
    snapshot_hash: str,
    artifact_ids: list[str],
) -> list[dict[str, Any]]:
    artifacts = (
        db.query(ScenarioDeliveryArtifact)
        .filter(ScenarioDeliveryArtifact.id.in_(artifact_ids))
        .all()
    )
    if len(artifacts) != 3 or {item.artifact_type for item in artifacts} != {
        "docx",
        "pdf",
        "audit_bundle",
    }:
        raise DeliveryAssuranceError(
            "专家签署必须覆盖同一冻结批次的 DOCX、PDF 和 audit bundle"
        )
    if any(
        item.scenario_id != scenario_id
        or item.snapshot_hash != snapshot_hash
        or item.status != "candidate"
        or hashlib.sha256(item.content).hexdigest() != item.content_sha256
        or len(item.content) != item.content_length
        for item in artifacts
    ):
        raise DeliveryAssuranceError("冻结制品错绑、已失效或 bytes 哈希校验失败")
    return [
        {
            "artifact_id": item.id,
            "artifact_type": item.artifact_type,
            "content_sha256": item.content_sha256,
            "content_length": item.content_length,
            "media_type": item.media_type,
            "filename": item.filename,
            "renderer_version": item.renderer_version,
        }
        for item in sorted(artifacts, key=lambda value: value.artifact_type)
    ]


def _validate_attestation_artifacts(
    db: Session,
    *,
    attestation: ScenarioExpertAttestation,
    expected_status: str,
) -> list[ScenarioDeliveryArtifact]:
    manifest = attestation.artifact_manifest
    if not isinstance(manifest, list) or len(manifest) != 3:
        raise DeliveryAssuranceError("签署制品 manifest 必须恰好包含三个制品")
    artifact_ids = [
        item.get("artifact_id") for item in manifest if isinstance(item, dict)
    ]
    artifact_types = [
        item.get("artifact_type") for item in manifest if isinstance(item, dict)
    ]
    if (
        len(artifact_ids) != 3
        or len(set(artifact_ids)) != 3
        or len(set(artifact_types)) != 3
        or set(artifact_types) != {"docx", "pdf", "audit_bundle"}
        or stable_hash(manifest) != attestation.artifact_manifest_hash
        or stable_hash(attestation.snapshot or {}) != attestation.snapshot_hash
    ):
        raise DeliveryAssuranceError("签署快照或制品 manifest 结构/哈希校验失败")
    artifacts = (
        db.query(ScenarioDeliveryArtifact)
        .filter(ScenarioDeliveryArtifact.id.in_(artifact_ids))
        .all()
    )
    if len(artifacts) != 3:
        raise DeliveryAssuranceError("签署引用的冻结制品不存在")
    by_id = {item.id: item for item in artifacts}
    metadata_fields = (
        "artifact_type",
        "content_sha256",
        "content_length",
        "media_type",
        "filename",
        "renderer_version",
    )
    for item in manifest:
        artifact = by_id.get(item["artifact_id"])
        if (
            artifact is None
            or artifact.scenario_id != attestation.scenario_id
            or artifact.snapshot_hash != attestation.snapshot_hash
            or artifact.status != expected_status
            or any(
                getattr(artifact, field) != item.get(field) for field in metadata_fields
            )
            or hashlib.sha256(artifact.content).hexdigest() != artifact.content_sha256
            or len(artifact.content) != artifact.content_length
        ):
            raise DeliveryAssuranceError("签署引用的冻结制品 bytes、元数据或状态已变化")
    return artifacts


def current_delivery_artifact_manifest(
    db: Session, *, scenario_id: int
) -> tuple[str, list[dict[str, Any]], str]:
    artifacts = (
        db.query(ScenarioDeliveryArtifact)
        .filter(
            ScenarioDeliveryArtifact.scenario_id == scenario_id,
            ScenarioDeliveryArtifact.status == "candidate",
        )
        .order_by(ScenarioDeliveryArtifact.artifact_type.asc())
        .all()
    )
    if len(artifacts) != 3:
        raise DeliveryAssuranceError("缺少完整的当前冻结制品批次")
    snapshot_hashes = {item.snapshot_hash for item in artifacts}
    if len(snapshot_hashes) != 1:
        raise DeliveryAssuranceError("当前冻结制品不属于同一场景快照")
    manifest = _artifact_manifest(
        db,
        scenario_id=scenario_id,
        snapshot_hash=next(iter(snapshot_hashes)),
        artifact_ids=[item.id for item in artifacts],
    )
    return next(iter(snapshot_hashes)), manifest, stable_hash(manifest)


def create_expert_attestation(
    db: Session,
    *,
    scenario: InvestigationScenario,
    generation_config: GenerationConfig,
    credential: LegalExpertCredential,
    artifact_ids: list[str],
    signed_artifact_manifest_hash: str,
    signature_format: str,
    signature_artifact_hash: str,
    signature_validation_url: str,
    signature_validation_report_hash: str,
    certificate_subject: str,
    certificate_serial: str,
    certificate_valid_until: datetime,
    statement: str,
    limitations: str,
    expires_at: datetime,
    user: User,
) -> ScenarioExpertAttestation:
    _require_scenario_counsel(scenario, user)
    now = _now()
    if credential.user_id != user.id:
        raise DeliveryAssurancePermissionError("只能使用本人的已核验执业凭证签署")
    if credential.status != "verified" or credential.valid_until is None:
        raise DeliveryAssuranceError("执业凭证尚未被独立核验")
    if not _is_live(credential.status, credential.valid_until, now=now):
        raise DeliveryAssuranceError("执业凭证已过期或失效")
    if not _jurisdiction_matches(scenario.country, credential.jurisdiction):
        raise DeliveryAssuranceError("执业凭证法域与场景国家不匹配")
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > _as_utc(
        credential.valid_until
    ):
        raise DeliveryAssuranceError("签署有效期必须晚于当前时间且不超过执业凭证有效期")
    if _as_utc(certificate_valid_until) <= now or _as_utc(expires_at) > _as_utc(
        certificate_valid_until
    ):
        raise DeliveryAssuranceError("签名证书必须当前有效且覆盖整个签署有效期")
    if (
        urlparse(signature_validation_url).hostname or ""
    ).lower() != "validar.iti.gov.br":
        raise DeliveryAssuranceError("数字签名验证必须来自 ITI VALIDAR 官方域名")
    if credential.holder_name.casefold() not in certificate_subject.casefold():
        raise DeliveryAssuranceError("签名证书主体与执业凭证持有人不匹配")
    signature_evidence = require_delivery_evidence_object(
        db,
        evidence_kind="iti_signature_artifact",
        content_sha256=signature_artifact_hash,
        scenario_id=scenario.id,
        uploaded_by=user.id,
        now=now,
    )
    validation_evidence = require_delivery_evidence_object(
        db,
        evidence_kind="iti_validation_report",
        content_sha256=signature_validation_report_hash,
        scenario_id=scenario.id,
        now=now,
    )
    _require_expiry_covered_by_evidence(
        expires_at, [signature_evidence, validation_evidence]
    )
    snapshot = build_delivery_snapshot(
        db, scenario=scenario, generation_config=generation_config
    )
    snapshot_hash = stable_hash(snapshot)
    manifest = _artifact_manifest(
        db,
        scenario_id=scenario.id,
        snapshot_hash=snapshot_hash,
        artifact_ids=artifact_ids,
    )
    manifest_hash = stable_hash(manifest)
    if signed_artifact_manifest_hash != manifest_hash:
        raise DeliveryAssuranceError(
            "外部签名覆盖的 artifact manifest hash 与当前冻结制品不一致"
        )
    rebound_attestation = (
        db.query(ScenarioExpertAttestation.id)
        .filter(
            (
                (
                    ScenarioExpertAttestation.signature_artifact_hash
                    == signature_artifact_hash
                )
                | (
                    ScenarioExpertAttestation.signature_validation_report_hash
                    == signature_validation_report_hash
                )
            ),
            ScenarioExpertAttestation.artifact_manifest_hash != manifest_hash,
        )
        .first()
    )
    if rebound_attestation is not None:
        raise DeliveryAssuranceError("签名或核验报告原件已绑定其他 artifact manifest")
    attestation = ScenarioExpertAttestation(
        id=str(uuid4()),
        scenario_id=scenario.id,
        credential_id=credential.id,
        signed_by=user.id,
        snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        artifact_manifest=manifest,
        artifact_manifest_hash=manifest_hash,
        signature_format=signature_format,
        signature_artifact_hash=signature_artifact_hash,
        signature_validation_url=signature_validation_url,
        signature_validation_report_hash=signature_validation_report_hash,
        signature_validation_status="submitted",
        certificate_subject=certificate_subject.strip(),
        certificate_serial=certificate_serial.strip(),
        certificate_valid_until=certificate_valid_until,
        statement=statement.strip(),
        limitations=limitations.strip(),
        status="pending_validation",
        signed_at=now,
        expires_at=expires_at,
    )
    db.add(attestation)
    db.flush()
    return attestation


def decide_attestation_signature(
    db: Session,
    *,
    attestation: ScenarioExpertAttestation,
    decision: str,
    note: str,
    user: User,
) -> ScenarioExpertAttestation:
    _require_admin(user)
    if attestation.signed_by == user.id:
        raise DeliveryAssurancePermissionError("签署人不得核验自己的数字签名")
    if (
        attestation.status != "pending_validation"
        or attestation.signature_validation_status != "submitted"
    ):
        raise DeliveryAssuranceError("只有待核验的数字签名可作决定")
    if decision not in {"approved", "rejected"}:
        raise DeliveryAssuranceError("无效的数字签名核验决定")
    now = _now()
    if decision == "approved":
        credential = db.get(LegalExpertCredential, attestation.credential_id)
        if (
            credential is None
            or credential.valid_until is None
            or not _is_live(credential.status, credential.valid_until, now=now)
            or _as_utc(attestation.expires_at) <= now
            or _as_utc(attestation.certificate_valid_until) <= now
        ):
            raise DeliveryAssuranceError("核验时签署、签名证书或执业凭证已失效")
        _validate_attestation_artifacts(
            db, attestation=attestation, expected_status="candidate"
        )
        require_delivery_evidence_object(
            db,
            evidence_kind="iti_signature_artifact",
            content_sha256=attestation.signature_artifact_hash,
            scenario_id=attestation.scenario_id,
            uploaded_by=attestation.signed_by,
            now=now,
        )
        require_delivery_evidence_object(
            db,
            evidence_kind="iti_validation_report",
            content_sha256=attestation.signature_validation_report_hash,
            scenario_id=attestation.scenario_id,
            now=now,
        )
    result = db.execute(
        update(ScenarioExpertAttestation)
        .where(
            ScenarioExpertAttestation.id == attestation.id,
            ScenarioExpertAttestation.status == "pending_validation",
            ScenarioExpertAttestation.signature_validation_status == "submitted",
        )
        .values(
            status="active" if decision == "approved" else "rejected",
            signature_validation_status=decision,
            signature_verified_by=user.id,
            signature_verified_at=now,
            signature_verification_note=note.strip(),
        )
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("数字签名核验状态已变化，请刷新后重试")
    if decision == "approved":
        db.execute(
            update(ScenarioExpertAttestation)
            .where(
                ScenarioExpertAttestation.scenario_id == attestation.scenario_id,
                ScenarioExpertAttestation.id != attestation.id,
                ScenarioExpertAttestation.status == "active",
            )
            .values(status="superseded")
        )
    db.flush()
    db.expire_all()
    return db.get(ScenarioExpertAttestation, attestation.id)


def revoke_attestation(
    db: Session,
    *,
    attestation: ScenarioExpertAttestation,
    reason: str,
    user: User,
) -> ScenarioExpertAttestation:
    if user.id != attestation.signed_by and user.role != ROLE_ADMIN:
        raise DeliveryAssurancePermissionError("只有原签署专家或管理员可撤回签署")
    if attestation.status != "active":
        raise DeliveryAssuranceError("只有 active 签署可被撤回")
    now = _now()
    result = db.execute(
        update(ScenarioExpertAttestation)
        .where(
            ScenarioExpertAttestation.id == attestation.id,
            ScenarioExpertAttestation.status == "active",
        )
        .values(
            status="revoked",
            revoked_by=user.id,
            revoked_at=now,
            revocation_reason=reason.strip(),
        )
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("专家签署状态已变化，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(ScenarioExpertAttestation, attestation.id)


def create_uat_acceptance(
    db: Session,
    *,
    scenario: InvestigationScenario,
    attestation: ScenarioExpertAttestation,
    customer_organization: str,
    test_plan_hash: str,
    test_evidence_hash: str,
    evidence_reference: str,
    environment: str,
    target_environment_id: str,
    acceptance_statement: str,
    expires_at: datetime,
    user: User,
) -> ScenarioUATAcceptance:
    now = _now()
    if scenario.user_id != user.id:
        raise DeliveryAssurancePermissionError("只有项目提交人可签署客户 UAT")
    if (
        not user.organization
        or user.organization.strip() != customer_organization.strip()
    ):
        raise DeliveryAssuranceError("UAT 客户组织必须与项目提交人所属组织一致")
    if attestation.scenario_id != scenario.id or not _is_live(
        attestation.status, attestation.expires_at, now=now
    ):
        raise DeliveryAssuranceError("专家签署不存在、已过期或已撤回")
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > _as_utc(
        attestation.expires_at
    ):
        raise DeliveryAssuranceError("UAT 有效期必须晚于当前时间且不超过专家签署有效期")
    test_plan_evidence = require_delivery_evidence_object(
        db,
        evidence_kind="uat_test_plan",
        content_sha256=test_plan_hash,
        scenario_id=scenario.id,
        uploaded_by=user.id,
        now=now,
    )
    test_result_evidence = require_delivery_evidence_object(
        db,
        evidence_kind="uat_test_evidence",
        content_sha256=test_evidence_hash,
        scenario_id=scenario.id,
        uploaded_by=user.id,
        now=now,
    )
    _require_expiry_covered_by_evidence(
        expires_at, [test_plan_evidence, test_result_evidence]
    )
    normalized_target_environment_id = target_environment_id.strip()
    rebound_uat = (
        db.query(ScenarioUATAcceptance.id)
        .filter(
            (
                (ScenarioUATAcceptance.test_plan_hash == test_plan_hash)
                | (ScenarioUATAcceptance.test_evidence_hash == test_evidence_hash)
            ),
            (
                (ScenarioUATAcceptance.snapshot_hash != attestation.snapshot_hash)
                | (
                    ScenarioUATAcceptance.target_environment_id
                    != normalized_target_environment_id
                )
            ),
        )
        .first()
    )
    if rebound_uat is not None:
        raise DeliveryAssuranceError("测试计划或 UAT 结果原件已绑定其他快照/环境")
    db.execute(
        update(ScenarioUATAcceptance)
        .where(
            ScenarioUATAcceptance.scenario_id == scenario.id,
            ScenarioUATAcceptance.status == "accepted",
        )
        .values(status="superseded")
    )
    acceptance = ScenarioUATAcceptance(
        id=str(uuid4()),
        scenario_id=scenario.id,
        expert_attestation_id=attestation.id,
        accepted_by=user.id,
        customer_organization=customer_organization.strip(),
        snapshot_hash=attestation.snapshot_hash,
        test_plan_hash=test_plan_hash,
        test_evidence_hash=test_evidence_hash,
        evidence_reference=evidence_reference,
        environment=environment.strip(),
        target_environment_id=normalized_target_environment_id,
        acceptance_statement=acceptance_statement.strip(),
        status="accepted",
        accepted_at=now,
        expires_at=expires_at,
    )
    db.add(acceptance)
    db.flush()
    return acceptance


def withdraw_uat(
    db: Session,
    *,
    acceptance: ScenarioUATAcceptance,
    reason: str,
    user: User,
) -> ScenarioUATAcceptance:
    if user.id != acceptance.accepted_by:
        raise DeliveryAssurancePermissionError("只有原 UAT 签署人可撤回验收")
    if acceptance.status != "accepted":
        raise DeliveryAssuranceError("只有 accepted UAT 可被撤回")
    now = _now()
    result = db.execute(
        update(ScenarioUATAcceptance)
        .where(
            ScenarioUATAcceptance.id == acceptance.id,
            ScenarioUATAcceptance.status == "accepted",
        )
        .values(status="withdrawn", withdrawn_at=now, withdrawal_reason=reason.strip())
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("UAT 状态已变化，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(ScenarioUATAcceptance, acceptance.id)


def create_legal_content_certification(
    db: Session,
    *,
    capability_pack_id: str,
    capability_pack_version: str,
    capability_pack_hash: str,
    rules_artifact_hash: str,
    corpus_artifact_hash: str,
    gold_dataset_sha256: str,
    evaluation_policy_sha256: str,
    evaluation_run_sha256: str,
    regression_status: str,
    primary_credential: LegalExpertCredential,
    secondary_credential: LegalExpertCredential,
    primary_signature_hash: str,
    primary_certificate_subject: str,
    primary_certificate_serial: str,
    primary_validation_url: str,
    primary_validation_report_hash: str,
    secondary_signature_hash: str,
    secondary_certificate_subject: str,
    secondary_certificate_serial: str,
    secondary_validation_url: str,
    secondary_validation_report_hash: str,
    signed_content_manifest_hash: str,
    limitations: str,
    expires_at: datetime,
    user: User,
) -> LegalContentCertification:
    _require_admin(user)
    now = _now()
    require_current_legal_content_signers(
        db,
        primary_credential=primary_credential,
        secondary_credential=secondary_credential,
        now=now,
    )
    content_evidence = [
        require_delivery_evidence_object(
            db,
            evidence_kind="content_primary_signature",
            content_sha256=primary_signature_hash,
            uploaded_by=primary_credential.user_id,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="content_primary_validation_report",
            content_sha256=primary_validation_report_hash,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="content_secondary_signature",
            content_sha256=secondary_signature_hash,
            uploaded_by=secondary_credential.user_id,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="content_secondary_validation_report",
            content_sha256=secondary_validation_report_hash,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="gold_dataset",
            content_sha256=gold_dataset_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="evaluation_policy",
            content_sha256=evaluation_policy_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="evaluation_run",
            content_sha256=evaluation_run_sha256,
            now=now,
        ),
    ]
    if (
        urlparse(primary_validation_url).hostname or ""
    ).lower() != "validar.iti.gov.br" or (
        urlparse(secondary_validation_url).hostname or ""
    ).lower() != "validar.iti.gov.br":
        raise DeliveryAssuranceError("双专家数字签名必须引用 ITI VALIDAR 官方域名")
    if (
        primary_credential.holder_name.casefold()
        not in primary_certificate_subject.casefold()
    ):
        raise DeliveryAssuranceError("第一签名证书主体与第一执业凭证持有人不匹配")
    if (
        secondary_credential.holder_name.casefold()
        not in secondary_certificate_subject.casefold()
    ):
        raise DeliveryAssuranceError("第二签名证书主体与第二执业凭证持有人不匹配")
    max_expiry = min(
        _as_utc(primary_credential.valid_until),
        _as_utc(secondary_credential.valid_until),
    )
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > max_expiry:
        raise DeliveryAssuranceError("内容认证有效期不得超过任一专家凭证有效期")
    _require_expiry_covered_by_evidence(expires_at, content_evidence)
    if regression_status != "passed":
        raise DeliveryAssuranceError("冻结 gold regression 未通过")
    manifest = build_legal_content_manifest(
        capability_pack_id=capability_pack_id,
        capability_pack_version=capability_pack_version,
        capability_pack_hash=capability_pack_hash,
        rules_artifact_hash=rules_artifact_hash,
        corpus_artifact_hash=corpus_artifact_hash,
        gold_dataset_sha256=gold_dataset_sha256,
        evaluation_policy_sha256=evaluation_policy_sha256,
        evaluation_run_sha256=evaluation_run_sha256,
        regression_status=regression_status,
        primary_credential_id=primary_credential.id,
        secondary_credential_id=secondary_credential.id,
        limitations=limitations,
    )
    manifest_hash = stable_hash(manifest)
    if signed_content_manifest_hash != manifest_hash:
        raise DeliveryAssuranceError(
            "双专家签名未覆盖当前 rules/corpus/gold manifest hash"
        )
    for content_evidence_hash in (
        primary_signature_hash,
        primary_validation_report_hash,
        secondary_signature_hash,
        secondary_validation_report_hash,
    ):
        reused_content_evidence = (
            db.query(LegalContentCertification.id)
            .filter(
                (
                    (
                        LegalContentCertification.primary_signature_hash
                        == content_evidence_hash
                    )
                    | (
                        LegalContentCertification.primary_validation_report_hash
                        == content_evidence_hash
                    )
                    | (
                        LegalContentCertification.secondary_signature_hash
                        == content_evidence_hash
                    )
                    | (
                        LegalContentCertification.secondary_validation_report_hash
                        == content_evidence_hash
                    )
                ),
                LegalContentCertification.certification_manifest_hash != manifest_hash,
            )
            .first()
        )
        if reused_content_evidence is not None:
            raise DeliveryAssuranceError(
                "内容签名或核验报告原件已绑定其他内容 manifest"
            )
    certification = LegalContentCertification(
        id=str(uuid4()),
        capability_pack_id=capability_pack_id.strip(),
        capability_pack_version=capability_pack_version.strip(),
        capability_pack_hash=capability_pack_hash,
        rules_artifact_hash=rules_artifact_hash,
        corpus_artifact_hash=corpus_artifact_hash,
        gold_dataset_sha256=gold_dataset_sha256,
        evaluation_policy_sha256=evaluation_policy_sha256,
        evaluation_run_sha256=evaluation_run_sha256,
        regression_status=regression_status,
        primary_credential_id=primary_credential.id,
        secondary_credential_id=secondary_credential.id,
        primary_signature_hash=primary_signature_hash,
        primary_certificate_subject=primary_certificate_subject.strip(),
        primary_certificate_serial=primary_certificate_serial.strip(),
        primary_validation_report_hash=primary_validation_report_hash,
        secondary_signature_hash=secondary_signature_hash,
        secondary_certificate_subject=secondary_certificate_subject.strip(),
        secondary_certificate_serial=secondary_certificate_serial.strip(),
        secondary_validation_report_hash=secondary_validation_report_hash,
        primary_validation_url=primary_validation_url,
        secondary_validation_url=secondary_validation_url,
        certification_manifest_hash=manifest_hash,
        limitations=limitations.strip(),
        status="certified",
        certified_by=user.id,
        certified_at=now,
        expires_at=expires_at,
    )
    db.add(certification)
    db.flush()
    return certification


def revoke_legal_content_certification(
    db: Session,
    *,
    certification: LegalContentCertification,
    reason: str,
    user: User,
) -> LegalContentCertification:
    _require_admin(user)
    if certification.status != "certified":
        raise DeliveryAssuranceError("只有 certified 法律内容认证可被撤回")
    now = _now()
    result = db.execute(
        update(LegalContentCertification)
        .where(
            LegalContentCertification.id == certification.id,
            LegalContentCertification.status == "certified",
        )
        .values(
            status="revoked",
            revoked_by=user.id,
            revoked_at=now,
            revocation_reason=reason.strip(),
        )
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("法律内容认证状态已变化，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(LegalContentCertification, certification.id)


def create_deployment_evidence(
    db: Session,
    *,
    legal_content_certification_id: str,
    environment: str,
    target_environment_id: str,
    commit_sha: str,
    migration_head: str,
    ci_run_url: str,
    artifact_sha256: str,
    artifact_receipt_hash: str,
    sbom_sha256: str,
    security_evidence_url: str,
    security_evidence_sha256: str,
    provenance_url: str,
    provenance_sha256: str,
    runtime_probe_url: str,
    runtime_probe_sha256: str,
    backend_image_digest: str,
    frontend_image_digest: str,
    database_image_digest: str,
    config_schema_sha256: str,
    capability_pack_hash: str,
    rules_artifact_hash: str,
    corpus_artifact_hash: str,
    gold_dataset_sha256: str,
    evaluation_policy_sha256: str,
    evaluation_run_sha256: str,
    regression_status: str,
    verification_note: str,
    expires_at: datetime,
    user: User,
) -> DeploymentEvidence:
    _require_admin(user)
    now = _now()
    if _as_utc(expires_at) <= now:
        raise DeliveryAssuranceError("部署证据有效期必须晚于当前时间")
    certification = db.get(LegalContentCertification, legal_content_certification_id)
    if certification is None or not _is_live(
        certification.status, certification.expires_at, now=now
    ):
        raise DeliveryAssuranceError("法律内容双专家认证不存在、已过期或已撤回")
    if _as_utc(expires_at) > _as_utc(certification.expires_at):
        raise DeliveryAssuranceError("部署证据有效期不得超过法律内容认证有效期")
    if (
        certification.capability_pack_hash != capability_pack_hash
        or certification.rules_artifact_hash != rules_artifact_hash
        or certification.corpus_artifact_hash != corpus_artifact_hash
        or certification.gold_dataset_sha256 != gold_dataset_sha256
        or certification.evaluation_policy_sha256 != evaluation_policy_sha256
        or certification.evaluation_run_sha256 != evaluation_run_sha256
    ):
        raise DeliveryAssuranceError("部署证据与法律内容双专家认证的哈希不一致")
    deployment_evidence_objects = [
        require_delivery_evidence_object(
            db,
            evidence_kind="build_artifact_descriptor",
            content_sha256=artifact_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="build_artifact_receipt",
            content_sha256=artifact_receipt_hash,
            now=now,
        ),
        require_delivery_evidence_object(
            db, evidence_kind="sbom", content_sha256=sbom_sha256, now=now
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="security_report",
            content_sha256=security_evidence_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="provenance",
            content_sha256=provenance_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="runtime_probe",
            content_sha256=runtime_probe_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="config_schema",
            content_sha256=config_schema_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="gold_dataset",
            content_sha256=gold_dataset_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="evaluation_policy",
            content_sha256=evaluation_policy_sha256,
            now=now,
        ),
        require_delivery_evidence_object(
            db,
            evidence_kind="evaluation_run",
            content_sha256=evaluation_run_sha256,
            now=now,
        ),
    ]
    try:
        descriptor = json.loads(
            deployment_evidence_objects[0].content.decode("utf-8")
        )
        receipt = json.loads(deployment_evidence_objects[1].content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryAssuranceError(
            "构建 descriptor 与 receipt 必须是有效 UTF-8 JSON"
        ) from exc
    expected_descriptor = {
        "schema_version": "1.0",
        "target_environment_id": target_environment_id.strip(),
        "commit_sha": commit_sha,
        "migration_head": migration_head.strip(),
        "backend_image_digest": backend_image_digest,
        "frontend_image_digest": frontend_image_digest,
        "database_image_digest": database_image_digest,
    }
    if not isinstance(descriptor, dict) or any(
        descriptor.get(key) != value for key, value in expected_descriptor.items()
    ):
        raise DeliveryAssuranceError(
            "构建 descriptor 未绑定当前 commit、镜像、迁移或目标环境"
        )
    expected_receipt = {
        "schema_version": "1.0",
        "target_environment_id": target_environment_id.strip(),
        "commit_sha": commit_sha,
        "migration_head": migration_head.strip(),
        "artifact_sha256": artifact_sha256,
        "backend_image_digest": backend_image_digest,
        "frontend_image_digest": frontend_image_digest,
        "database_image_digest": database_image_digest,
    }
    if not isinstance(receipt, dict) or any(
        receipt.get(key) != value for key, value in expected_receipt.items()
    ):
        raise DeliveryAssuranceError("构建 receipt 未绑定当前 commit、镜像、迁移或目标环境")
    _require_expiry_covered_by_evidence(expires_at, deployment_evidence_objects)
    evidence = DeploymentEvidence(
        id=str(uuid4()),
        legal_content_certification_id=certification.id,
        environment=environment,
        target_environment_id=target_environment_id.strip(),
        commit_sha=commit_sha,
        migration_head=migration_head.strip(),
        ci_run_url=ci_run_url,
        artifact_sha256=artifact_sha256,
        artifact_receipt_hash=artifact_receipt_hash,
        sbom_sha256=sbom_sha256,
        security_evidence_url=security_evidence_url,
        security_evidence_sha256=security_evidence_sha256,
        provenance_url=provenance_url,
        provenance_sha256=provenance_sha256,
        runtime_probe_url=runtime_probe_url,
        runtime_probe_sha256=runtime_probe_sha256,
        backend_image_digest=backend_image_digest,
        frontend_image_digest=frontend_image_digest,
        database_image_digest=database_image_digest,
        config_schema_sha256=config_schema_sha256,
        capability_pack_hash=capability_pack_hash,
        rules_artifact_hash=rules_artifact_hash,
        corpus_artifact_hash=corpus_artifact_hash,
        gold_dataset_sha256=gold_dataset_sha256,
        evaluation_policy_sha256=evaluation_policy_sha256,
        evaluation_run_sha256=evaluation_run_sha256,
        regression_status=regression_status,
        verification_note=verification_note.strip(),
        status="verified",
        verified_by=user.id,
        verified_at=now,
        expires_at=expires_at,
    )
    db.add(evidence)
    db.flush()
    return evidence


def revoke_deployment_evidence(
    db: Session,
    *,
    evidence: DeploymentEvidence,
    reason: str,
    user: User,
) -> DeploymentEvidence:
    _require_admin(user)
    if evidence.status != "verified":
        raise DeliveryAssuranceError("只有 verified 部署证据可被撤回")
    now = _now()
    result = db.execute(
        update(DeploymentEvidence)
        .where(
            DeploymentEvidence.id == evidence.id,
            DeploymentEvidence.status == "verified",
        )
        .values(
            status="revoked",
            revoked_by=user.id,
            revoked_at=now,
            revocation_reason=reason.strip(),
        )
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("部署证据状态已变化，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(DeploymentEvidence, evidence.id)


def create_delivery_release(
    db: Session,
    *,
    scenario: InvestigationScenario,
    generation_config: GenerationConfig,
    attestation: ScenarioExpertAttestation,
    acceptance: ScenarioUATAcceptance,
    deployment: DeploymentEvidence,
    release_note: str,
    expires_at: datetime,
    user: User,
) -> ScenarioDeliveryRelease:
    _require_admin(user)
    now = _now()
    if attestation.signed_by == user.id:
        raise DeliveryAssurancePermissionError("发布管理员不得放行本人签署的法律结论")
    if attestation.scenario_id != scenario.id or acceptance.scenario_id != scenario.id:
        raise DeliveryAssuranceError("签署、UAT 与场景错绑")
    if acceptance.expert_attestation_id != attestation.id:
        raise DeliveryAssuranceError("UAT 未绑定所选专家签署")
    customer = db.get(User, scenario.user_id)
    if (
        acceptance.accepted_by != scenario.user_id
        or customer is None
        or not customer.organization
        or customer.organization.strip() != acceptance.customer_organization.strip()
        or acceptance.environment != "customer_acceptance"
    ):
        raise DeliveryAssuranceError("客户 UAT 的签署人、组织或验收环境无效")
    if user.id == acceptance.accepted_by:
        raise DeliveryAssurancePermissionError("最终发布管理员不得同时作为客户 UAT 签署人")
    if not _is_live(attestation.status, attestation.expires_at, now=now):
        raise DeliveryAssuranceError("专家签署已过期、撤回或被替代")
    if not _is_live(acceptance.status, acceptance.expires_at, now=now):
        raise DeliveryAssuranceError("客户 UAT 已过期、撤回或被替代")
    if not _is_live(deployment.status, deployment.expires_at, now=now):
        raise DeliveryAssuranceError("生产部署证据已过期或撤回")
    if deployment.environment != "production":
        raise DeliveryAssuranceError("只有 production 部署证据可用于客户交付")
    if acceptance.target_environment_id != deployment.target_environment_id:
        raise DeliveryAssuranceError("客户 UAT 与生产部署证据的环境 ID 不一致")
    if deployment.regression_status != "passed":
        raise DeliveryAssuranceError("冻结 gold regression 未通过")
    content_certification = db.get(
        LegalContentCertification, deployment.legal_content_certification_id
    )
    if content_certification is None or not _is_live(
        content_certification.status, content_certification.expires_at, now=now
    ):
        raise DeliveryAssuranceError("法律内容双专家认证已过期或撤回")
    if not _content_certification_signers_are_current(
        db, content_certification, now=now
    ):
        raise DeliveryAssuranceError("法律内容认证签署人凭证已过期、撤回或身份不匹配")
    primary_credential = db.get(
        LegalExpertCredential, content_certification.primary_credential_id
    )
    secondary_credential = db.get(
        LegalExpertCredential, content_certification.secondary_credential_id
    )
    if primary_credential is None or secondary_credential is None:
        raise DeliveryAssuranceError("法律内容认证签署人凭证不存在")
    if stable_hash(_content_certification_manifest(content_certification)) != (
        content_certification.certification_manifest_hash
    ):
        raise DeliveryAssuranceError("法律内容双专家认证 manifest 哈希校验失败")
    if _active_legal_changes_after(db, content_certification.certified_at):
        raise DeliveryAssuranceError("内容认证后出现已审批法源实质变化，必须重新认证")
    if (
        deployment.capability_pack_hash != generation_config.capability_pack_hash
        or deployment.rules_artifact_hash != generation_config.rules_artifact_hash
        or deployment.corpus_artifact_hash != generation_config.corpus_artifact_hash
    ):
        raise DeliveryAssuranceError(
            "部署证据的 Capability Pack/规则/语料哈希与场景不一致"
        )
    if (
        content_certification.capability_pack_hash
        != generation_config.capability_pack_hash
        or content_certification.rules_artifact_hash
        != generation_config.rules_artifact_hash
        or content_certification.corpus_artifact_hash
        != generation_config.corpus_artifact_hash
        or content_certification.gold_dataset_sha256 != deployment.gold_dataset_sha256
        or content_certification.evaluation_policy_sha256
        != deployment.evaluation_policy_sha256
        or content_certification.evaluation_run_sha256
        != deployment.evaluation_run_sha256
    ):
        raise DeliveryAssuranceError(
            "法律内容双专家认证未覆盖当前规则、语料或 gold run"
        )
    credential = db.get(LegalExpertCredential, attestation.credential_id)
    if (
        credential is None
        or credential.valid_until is None
        or not _is_live(credential.status, credential.valid_until, now=now)
    ):
        raise DeliveryAssuranceError("专家执业凭证已失效")
    if (
        attestation.signature_validation_status != "approved"
        or attestation.signature_verified_by is None
        or attestation.signature_verified_at is None
    ):
        raise DeliveryAssuranceError("专家数字签名尚未经独立核验")
    if attestation.signed_by != _scenario_counsel_id(scenario):
        raise DeliveryAssuranceError("专家签署人不是当前场景法务定稿主审")
    verification_actors = {
        attestation.signature_verified_by,
        deployment.verified_by,
        content_certification.certified_by,
        credential.verified_by,
        primary_credential.verified_by,
        secondary_credential.verified_by,
    }
    verification_actors.discard(None)
    if user.id in verification_actors:
        raise DeliveryAssurancePermissionError(
            "最终发布管理员必须独立于凭证、签名、内容认证和部署证据核验人"
        )
    for actor_id in verification_actors:
        actor = db.get(User, actor_id)
        if actor is None or actor.role != ROLE_ADMIN:
            raise DeliveryAssuranceError("证据核验人必须保持 admin 角色")
    _validate_attestation_artifacts(
        db, attestation=attestation, expected_status="candidate"
    )
    release_evidence_objects = _require_release_evidence_objects(
        db,
        scenario=scenario,
        attestation=attestation,
        acceptance=acceptance,
        deployment=deployment,
        content_certification=content_certification,
        scenario_credential=credential,
        primary_credential=primary_credential,
        secondary_credential=secondary_credential,
        now=now,
    )
    snapshot = build_delivery_snapshot(
        db, scenario=scenario, generation_config=generation_config
    )
    snapshot_hash = stable_hash(snapshot)
    if (
        attestation.snapshot_hash != snapshot_hash
        or acceptance.snapshot_hash != snapshot_hash
    ):
        raise DeliveryAssuranceError("签署或 UAT 已因项目快照变化而失效")
    max_expiry = min(
        _as_utc(attestation.expires_at),
        _as_utc(attestation.certificate_valid_until),
        _as_utc(acceptance.expires_at),
        _as_utc(deployment.expires_at),
        _as_utc(content_certification.expires_at),
        _as_utc(credential.valid_until),
        _as_utc(primary_credential.valid_until),
        _as_utc(secondary_credential.valid_until),
    )
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > max_expiry:
        raise DeliveryAssuranceError(
            "发布有效期不得超过证据链任一凭证、签名或验收的最早有效期"
        )
    _require_expiry_covered_by_evidence(expires_at, release_evidence_objects)
    normalized_release_note = release_note.strip()
    release_body = _release_body(
        scenario_id=scenario.id,
        snapshot_hash=snapshot_hash,
        attestation=attestation,
        acceptance=acceptance,
        deployment=deployment,
        content_certification=content_certification,
        scenario_credential=credential,
        primary_credential=primary_credential,
        secondary_credential=secondary_credential,
        evidence_objects=release_evidence_objects,
        release_note=normalized_release_note,
        released_by=user.id,
        released_at=now,
        expires_at=expires_at,
    )
    db.execute(
        update(ScenarioDeliveryRelease)
        .where(
            ScenarioDeliveryRelease.scenario_id == scenario.id,
            ScenarioDeliveryRelease.status == "active",
        )
        .values(status="superseded")
    )
    release = ScenarioDeliveryRelease(
        id=str(uuid4()),
        scenario_id=scenario.id,
        expert_attestation_id=attestation.id,
        uat_acceptance_id=acceptance.id,
        deployment_evidence_id=deployment.id,
        snapshot_hash=snapshot_hash,
        release_hash=stable_hash(release_body),
        release_note=normalized_release_note,
        status="active",
        released_by=user.id,
        released_at=now,
        expires_at=expires_at,
    )
    db.add(release)
    artifact_ids = [
        item.get("artifact_id") for item in attestation.artifact_manifest or []
    ]
    artifact_update = db.execute(
        update(ScenarioDeliveryArtifact)
        .where(
            ScenarioDeliveryArtifact.id.in_(artifact_ids),
            ScenarioDeliveryArtifact.status == "candidate",
        )
        .values(status="released")
    )
    if artifact_update.rowcount != 3:
        raise DeliveryAssuranceConflict("冻结制品状态已变化，发布授权未创建")
    db.flush()
    return release


def revoke_delivery_release(
    db: Session,
    *,
    release: ScenarioDeliveryRelease,
    reason: str,
    user: User,
) -> ScenarioDeliveryRelease:
    _require_admin(user)
    if release.status != "active":
        raise DeliveryAssuranceError("只有 active 发布授权可被撤回")
    now = _now()
    result = db.execute(
        update(ScenarioDeliveryRelease)
        .where(
            ScenarioDeliveryRelease.id == release.id,
            ScenarioDeliveryRelease.status == "active",
        )
        .values(
            status="revoked",
            revoked_by=user.id,
            revoked_at=now,
            revocation_reason=reason.strip(),
        )
    )
    if result.rowcount != 1:
        raise DeliveryAssuranceConflict("发布授权状态已变化，请刷新后重试")
    db.flush()
    db.expire_all()
    return db.get(ScenarioDeliveryRelease, release.id)


def evaluate_delivery_release(
    db: Session,
    *,
    scenario: InvestigationScenario,
    generation_config: GenerationConfig,
) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        snapshot = build_delivery_snapshot(
            db, scenario=scenario, generation_config=generation_config
        )
        snapshot_hash = stable_hash(snapshot)
    except DeliveryAssuranceError as exc:
        snapshot = None
        snapshot_hash = None
        reasons.append(f"answerability_snapshot_invalid:{exc}")

    release = (
        db.query(ScenarioDeliveryRelease)
        .filter(
            ScenarioDeliveryRelease.scenario_id == scenario.id,
            ScenarioDeliveryRelease.status == "active",
        )
        .order_by(ScenarioDeliveryRelease.released_at.desc())
        .first()
    )
    now = _now()
    attestation = acceptance = deployment = content_certification = None
    credential = primary_credential = secondary_credential = None
    if release is None:
        reasons.append("active_delivery_release_missing")
    else:
        if _as_utc(release.expires_at) <= now:
            reasons.append("delivery_release_expired")
        if snapshot_hash is None or release.snapshot_hash != snapshot_hash:
            reasons.append("delivery_release_snapshot_stale")
        attestation = db.get(ScenarioExpertAttestation, release.expert_attestation_id)
        acceptance = db.get(ScenarioUATAcceptance, release.uat_acceptance_id)
        deployment = db.get(DeploymentEvidence, release.deployment_evidence_id)
        if deployment is not None:
            content_certification = db.get(
                LegalContentCertification, deployment.legal_content_certification_id
            )
        if attestation is not None:
            credential = db.get(LegalExpertCredential, attestation.credential_id)
        if content_certification is not None:
            primary_credential = db.get(
                LegalExpertCredential, content_certification.primary_credential_id
            )
            secondary_credential = db.get(
                LegalExpertCredential, content_certification.secondary_credential_id
            )

        if attestation is None or not _is_live(
            attestation.status, attestation.expires_at, now=now
        ):
            reasons.append("expert_attestation_inactive")
        elif (
            attestation.signature_validation_status != "approved"
            or not attestation.signature_verified_by
            or not attestation.signature_verified_at
            or _as_utc(attestation.certificate_valid_until) <= now
            or stable_hash(attestation.snapshot or {}) != attestation.snapshot_hash
            or stable_hash(attestation.artifact_manifest or {})
            != attestation.artifact_manifest_hash
            or attestation.scenario_id != scenario.id
            or attestation.snapshot_hash != release.snapshot_hash
        ):
            reasons.append("expert_signature_or_manifest_invalid")
        else:
            manifest = attestation.artifact_manifest
            if not isinstance(manifest, list) or not all(
                isinstance(item, dict) for item in manifest
            ):
                reasons.append("delivery_artifact_set_invalid")
                manifest = []
            manifest_ids = [item.get("artifact_id") for item in manifest]
            if (
                len(manifest) != 3
                or len(set(manifest_ids)) != 3
                or {item.get("artifact_type") for item in manifest}
                != {"docx", "pdf", "audit_bundle"}
            ):
                reasons.append("delivery_artifact_set_invalid")
            for manifest_item in manifest:
                artifact = db.get(
                    ScenarioDeliveryArtifact, manifest_item.get("artifact_id")
                )
                if (
                    artifact is None
                    or artifact.scenario_id != scenario.id
                    or artifact.snapshot_hash != release.snapshot_hash
                    or artifact.status != "released"
                    or artifact.content_sha256 != manifest_item.get("content_sha256")
                    or artifact.content_length != manifest_item.get("content_length")
                    or artifact.media_type != manifest_item.get("media_type")
                    or artifact.filename != manifest_item.get("filename")
                    or artifact.renderer_version
                    != manifest_item.get("renderer_version")
                    or hashlib.sha256(artifact.content).hexdigest()
                    != artifact.content_sha256
                    or len(artifact.content) != artifact.content_length
                ):
                    reasons.append(
                        f"delivery_artifact_invalid:{manifest_item.get('artifact_type')}"
                    )
        if acceptance is None or not _is_live(
            acceptance.status, acceptance.expires_at, now=now
        ):
            reasons.append("customer_uat_inactive")
        elif (
            acceptance.scenario_id != scenario.id
            or attestation is None
            or acceptance.expert_attestation_id != attestation.id
            or acceptance.snapshot_hash != release.snapshot_hash
        ):
            reasons.append("customer_uat_binding_invalid")
        elif (
            acceptance.accepted_by != scenario.user_id
            or acceptance.environment != "customer_acceptance"
        ):
            reasons.append("customer_uat_identity_invalid")
        else:
            customer = db.get(User, acceptance.accepted_by)
            if (
                customer is None
                or not customer.organization
                or customer.organization.strip()
                != acceptance.customer_organization.strip()
            ):
                reasons.append("customer_uat_identity_invalid")

        if deployment is None or not _is_live(
            deployment.status, deployment.expires_at, now=now
        ):
            reasons.append("deployment_evidence_inactive")
        elif deployment.environment != "production":
            reasons.append("deployment_not_production")
        elif (
            acceptance is not None
            and acceptance.target_environment_id != deployment.target_environment_id
        ):
            reasons.append("uat_deployment_environment_mismatch")
        elif deployment.regression_status != "passed":
            reasons.append("gold_regression_not_passed")
        elif (
            deployment.capability_pack_hash != generation_config.capability_pack_hash
            or deployment.rules_artifact_hash != generation_config.rules_artifact_hash
            or deployment.corpus_artifact_hash != generation_config.corpus_artifact_hash
        ):
            reasons.append("deployment_legal_artifact_binding_stale")
        else:
            if content_certification is None or not _is_live(
                content_certification.status,
                content_certification.expires_at,
                now=now,
            ):
                reasons.append("legal_content_certification_inactive")
            elif not _content_certification_signers_are_current(
                db, content_certification, now=now
            ):
                reasons.append("legal_content_signer_credentials_invalid")
            elif stable_hash(
                _content_certification_manifest(content_certification)
            ) != (content_certification.certification_manifest_hash):
                reasons.append("legal_content_certification_hash_invalid")
            elif _active_legal_changes_after(db, content_certification.certified_at):
                reasons.append("legal_change_revalidation_required")
            elif (
                content_certification.capability_pack_hash
                != generation_config.capability_pack_hash
                or content_certification.rules_artifact_hash
                != generation_config.rules_artifact_hash
                or content_certification.corpus_artifact_hash
                != generation_config.corpus_artifact_hash
                or content_certification.gold_dataset_sha256
                != deployment.gold_dataset_sha256
                or content_certification.evaluation_policy_sha256
                != deployment.evaluation_policy_sha256
                or content_certification.evaluation_run_sha256
                != deployment.evaluation_run_sha256
            ):
                reasons.append("legal_content_certification_binding_stale")

        if attestation is not None:
            if (
                credential is None
                or credential.valid_until is None
                or not _is_live(credential.status, credential.valid_until, now=now)
            ):
                reasons.append("expert_credential_inactive")
            elif credential.user_id != attestation.signed_by:
                reasons.append("expert_credential_signer_mismatch")
            elif (
                credential.registration_status != "regular"
                or not _jurisdiction_matches(scenario.country, credential.jurisdiction)
                or credential.holder_name.casefold()
                not in attestation.certificate_subject.casefold()
            ):
                reasons.append("expert_credential_identity_invalid")
            else:
                signer = db.get(User, attestation.signed_by)
                if signer is None or signer.role != ROLE_LEGAL:
                    reasons.append("expert_signer_role_invalid")
                else:
                    try:
                        if signer.id != _scenario_counsel_id(scenario):
                            reasons.append("expert_signer_not_scenario_counsel")
                    except DeliveryAssuranceError:
                        reasons.append("expert_signer_not_scenario_counsel")

        release_admin = db.get(User, release.released_by)
        if release_admin is None or release_admin.role != ROLE_ADMIN:
            reasons.append("release_approver_role_invalid")
        verification_actors = {
            attestation.signature_verified_by if attestation else None,
            deployment.verified_by if deployment else None,
            content_certification.certified_by if content_certification else None,
            credential.verified_by if credential else None,
            primary_credential.verified_by if primary_credential else None,
            secondary_credential.verified_by if secondary_credential else None,
        }
        verification_actors.discard(None)
        if release.released_by in verification_actors:
            reasons.append("release_approver_separation_invalid")
        if acceptance is not None and release.released_by == acceptance.accepted_by:
            reasons.append("release_approver_separation_invalid")
        for actor_id in verification_actors:
            actor = db.get(User, actor_id)
            if actor is None or actor.role != ROLE_ADMIN:
                reasons.append("evidence_verifier_role_invalid")

        evidence_records = (
            attestation,
            acceptance,
            deployment,
            content_certification,
            credential,
            primary_credential,
            secondary_credential,
        )
        if all(item is not None for item in evidence_records):
            try:
                release_evidence_objects = _require_release_evidence_objects(
                    db,
                    scenario=scenario,
                    attestation=attestation,
                    acceptance=acceptance,
                    deployment=deployment,
                    content_certification=content_certification,
                    scenario_credential=credential,
                    primary_credential=primary_credential,
                    secondary_credential=secondary_credential,
                    now=now,
                )
            except DeliveryAssuranceError:
                release_evidence_objects = []
                reasons.append("delivery_evidence_objects_invalid")
            release_body = _release_body(
                scenario_id=release.scenario_id,
                snapshot_hash=release.snapshot_hash,
                attestation=attestation,
                acceptance=acceptance,
                deployment=deployment,
                content_certification=content_certification,
                scenario_credential=credential,
                primary_credential=primary_credential,
                secondary_credential=secondary_credential,
                evidence_objects=release_evidence_objects,
                release_note=release.release_note,
                released_by=release.released_by,
                released_at=release.released_at,
                expires_at=release.expires_at,
            )
            if stable_hash(release_body) != release.release_hash:
                reasons.append("delivery_release_hash_invalid")
            evidence_expiries = (
                attestation.expires_at,
                attestation.certificate_valid_until,
                acceptance.expires_at,
                deployment.expires_at,
                content_certification.expires_at,
                credential.valid_until,
                primary_credential.valid_until,
                secondary_credential.valid_until,
            )
            if any(
                expiry is None or _as_utc(release.expires_at) > _as_utc(expiry)
                for expiry in evidence_expiries
            ):
                reasons.append("delivery_release_expiry_exceeds_evidence")

    unique_reasons = sorted(set(reasons))
    return {
        "schema_version": "1.1",
        "scenario_id": scenario.id,
        "evaluated_at": now.isoformat(),
        "delivery_allowed": not unique_reasons,
        "blocking_reasons": unique_reasons,
        "snapshot_hash": snapshot_hash,
        "release_id": release.id if release else None,
        "release_hash": release.release_hash if release else None,
        "expert_attestation_id": attestation.id if attestation else None,
        "uat_acceptance_id": acceptance.id if acceptance else None,
        "deployment_evidence_id": deployment.id if deployment else None,
        "boundary": (
            "系统仅验证证据链的身份、状态、期限与哈希绑定；"
            "不自行认定律师执业资格真实有效，也不替代律师法律判断或客户验收。"
        ),
    }


def require_active_delivery_release(
    db: Session,
    *,
    scenario: InvestigationScenario,
    generation_config: GenerationConfig,
) -> dict[str, Any]:
    report = evaluate_delivery_release(
        db, scenario=scenario, generation_config=generation_config
    )
    if not report["delivery_allowed"]:
        raise DeliveryGateBlocked(report)
    return report


def require_released_delivery_artifact(
    db: Session,
    *,
    scenario: InvestigationScenario,
    generation_config: GenerationConfig,
    artifact_type: str,
) -> tuple[dict[str, Any], ScenarioDeliveryArtifact]:
    report = require_active_delivery_release(
        db, scenario=scenario, generation_config=generation_config
    )
    release = db.get(ScenarioDeliveryRelease, report["release_id"])
    attestation = db.get(ScenarioExpertAttestation, release.expert_attestation_id)
    manifest_item = next(
        (
            item
            for item in list(attestation.artifact_manifest or [])
            if item.get("artifact_type") == artifact_type
        ),
        None,
    )
    if manifest_item is None:
        raise DeliveryGateBlocked(
            {
                **report,
                "delivery_allowed": False,
                "blocking_reasons": ["artifact_not_released"],
            }
        )
    artifact = db.get(ScenarioDeliveryArtifact, manifest_item.get("artifact_id"))
    if artifact is None or artifact.status != "released":
        raise DeliveryGateBlocked(
            {
                **report,
                "delivery_allowed": False,
                "blocking_reasons": ["artifact_not_released"],
            }
        )
    return report, artifact
