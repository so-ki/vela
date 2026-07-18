from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.roles import ROLE_ADMIN, ROLE_LEGAL
from app.models.delivery_assurance import (
    DeploymentEvidence,
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


def _require_admin(user: User) -> None:
    if user.role != ROLE_ADMIN:
        raise DeliveryAssurancePermissionError("只有发布管理员可执行该操作")


def _require_legal(user: User) -> None:
    if user.role != ROLE_LEGAL:
        raise DeliveryAssurancePermissionError("只有独立 legal 角色可作为法律专家，管理员不得代签")


def _jurisdiction_matches(scenario_country: str, jurisdiction: str) -> bool:
    aliases = {
        "br": "brazil",
        "bra": "brazil",
        "brasil": "brazil",
        "brazil": "brazil",
    }
    country = aliases.get(scenario_country.strip().lower(), scenario_country.strip().lower())
    expert = aliases.get(jurisdiction.strip().lower(), jurisdiction.strip().lower())
    return country == expert


def _require_brazil_official_registry_url(value: str) -> None:
    host = (urlparse(value).hostname or "").lower().rstrip(".")
    if host not in {"consulta.oab.org.br", "confirmadv.oab.org.br"}:
        raise DeliveryAssuranceError("巴西律师凭证必须引用 OAB CNA 或 ConfirmADV 官方域名")


def _content_certification_manifest(certification: LegalContentCertification) -> dict[str, Any]:
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
            "confirmed_at": _as_utc(claim.confirmed_at).isoformat() if claim.confirmed_at else None,
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
        raise DeliveryAssuranceError("Answerability Gate 与 CoverageProof 读取结果不一致")

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
    if any(
        bool(item.get("external_counsel_required"))
        for item in (review.get("items") or [])
    ):
        raise DeliveryAssuranceError("仍存在 external_counsel_required 条目，禁止客户交付")
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
        raise DeliveryAssuranceError(f"执业凭证不得从 {credential.status} 变更为 {decision}")
    now = _now()
    values: dict[str, Any] = {
        "status": decision,
        "decision_note": note.strip(),
        "revision": credential.revision + 1,
        "updated_at": now,
    }
    if decision == "verified":
        if not verification_reference or not verification_evidence_hash or valid_until is None:
            raise DeliveryAssuranceError("核验通过必须提交官方核验引用、证据哈希和有效期")
        if credential.jurisdiction.strip().lower() in {"br", "bra", "brasil", "brazil"}:
            _require_brazil_official_registry_url(verification_reference)
        if registration_status != "regular":
            raise DeliveryAssuranceError("只有 OAB 状态 regular 的凭证可核验通过")
        if _as_utc(valid_until) <= now:
            raise DeliveryAssuranceError("凭证有效期必须晚于当前时间")
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

    _require_legal(user)
    snapshot = build_delivery_snapshot(db, scenario=scenario, generation_config=generation_config)
    snapshot_hash = stable_hash(snapshot)
    answerability = snapshot["mechanism"]["answerability_gate"]
    bundle = build_audit_bundle(scenario, generation_config=generation_config)
    bundle["bundle_version"] = "1.4"
    bundle["answerability_gate"] = answerability
    bundle["delivery_snapshot_hash"] = snapshot_hash
    audit_bytes = json.dumps(
        bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    docx_bytes, docx_name = build_sample_docx(scenario, generation_config=generation_config)
    pdf_bytes, pdf_name = build_sample_pdf(scenario, generation_config=generation_config)
    candidates = [
        (
            "docx",
            docx_bytes,
            docx_name,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("pdf", pdf_bytes, pdf_name, "application/pdf"),
        ("audit_bundle", audit_bytes, f"vela-{scenario.id}-audit-bundle.json", "application/json"),
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
        raise DeliveryAssuranceError("专家签署必须覆盖同一冻结批次的 DOCX、PDF 和 audit bundle")
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
    _require_legal(user)
    now = _now()
    if credential.user_id != user.id:
        raise DeliveryAssurancePermissionError("只能使用本人的已核验执业凭证签署")
    if credential.status != "verified" or credential.valid_until is None:
        raise DeliveryAssuranceError("执业凭证尚未被独立核验")
    if not _is_live(credential.status, credential.valid_until, now=now):
        raise DeliveryAssuranceError("执业凭证已过期或失效")
    if not _jurisdiction_matches(scenario.country, credential.jurisdiction):
        raise DeliveryAssuranceError("执业凭证法域与场景国家不匹配")
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > _as_utc(credential.valid_until):
        raise DeliveryAssuranceError("签署有效期必须晚于当前时间且不超过执业凭证有效期")
    if _as_utc(certificate_valid_until) <= now or _as_utc(expires_at) > _as_utc(
        certificate_valid_until
    ):
        raise DeliveryAssuranceError("签名证书必须当前有效且覆盖整个签署有效期")
    if (urlparse(signature_validation_url).hostname or "").lower() != "validar.iti.gov.br":
        raise DeliveryAssuranceError("数字签名验证必须来自 ITI VALIDAR 官方域名")
    if credential.holder_name.casefold() not in certificate_subject.casefold():
        raise DeliveryAssuranceError("签名证书主体与执业凭证持有人不匹配")
    snapshot = build_delivery_snapshot(db, scenario=scenario, generation_config=generation_config)
    snapshot_hash = stable_hash(snapshot)
    manifest = _artifact_manifest(
        db,
        scenario_id=scenario.id,
        snapshot_hash=snapshot_hash,
        artifact_ids=artifact_ids,
    )
    manifest_hash = stable_hash(manifest)
    if signed_artifact_manifest_hash != manifest_hash:
        raise DeliveryAssuranceError("外部签名覆盖的 artifact manifest hash 与当前冻结制品不一致")
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
    if attestation.status != "pending_validation" or attestation.signature_validation_status != "submitted":
        raise DeliveryAssuranceError("只有待核验的数字签名可作决定")
    if decision not in {"approved", "rejected"}:
        raise DeliveryAssuranceError("无效的数字签名核验决定")
    now = _now()
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
    if not user.organization or user.organization.strip() != customer_organization.strip():
        raise DeliveryAssuranceError("UAT 客户组织必须与项目提交人所属组织一致")
    if attestation.scenario_id != scenario.id or not _is_live(
        attestation.status, attestation.expires_at, now=now
    ):
        raise DeliveryAssuranceError("专家签署不存在、已过期或已撤回")
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > _as_utc(attestation.expires_at):
        raise DeliveryAssuranceError("UAT 有效期必须晚于当前时间且不超过专家签署有效期")
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
        target_environment_id=target_environment_id.strip(),
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
    if primary_credential.id == secondary_credential.id or primary_credential.user_id == secondary_credential.user_id:
        raise DeliveryAssuranceError("生产法律内容必须由两名不同律师独立认证")
    for credential in (primary_credential, secondary_credential):
        if (
            credential.status != "verified"
            or credential.registration_status != "regular"
            or credential.valid_until is None
            or not _is_live(credential.status, credential.valid_until, now=now)
        ):
            raise DeliveryAssuranceError("双专家认证引用了无效、过期或非 regular 的执业凭证")
        if not _jurisdiction_matches("brazil", credential.jurisdiction):
            raise DeliveryAssuranceError("巴西法律内容认证必须由巴西法域律师完成")
        holder = db.get(User, credential.user_id)
        if holder is None or holder.role != ROLE_LEGAL:
            raise DeliveryAssuranceError("内容认证签署人必须保持独立 legal 角色")
    if (urlparse(primary_validation_url).hostname or "").lower() != "validar.iti.gov.br" or (
        urlparse(secondary_validation_url).hostname or ""
    ).lower() != "validar.iti.gov.br":
        raise DeliveryAssuranceError("双专家数字签名必须引用 ITI VALIDAR 官方域名")
    if primary_credential.holder_name.casefold() not in primary_certificate_subject.casefold():
        raise DeliveryAssuranceError("第一签名证书主体与第一执业凭证持有人不匹配")
    if secondary_credential.holder_name.casefold() not in secondary_certificate_subject.casefold():
        raise DeliveryAssuranceError("第二签名证书主体与第二执业凭证持有人不匹配")
    max_expiry = min(
        _as_utc(primary_credential.valid_until),
        _as_utc(secondary_credential.valid_until),
    )
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > max_expiry:
        raise DeliveryAssuranceError("内容认证有效期不得超过任一专家凭证有效期")
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
        raise DeliveryAssuranceError("双专家签名未覆盖当前 rules/corpus/gold manifest hash")
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
    sbom_sha256: str,
    security_evidence_url: str,
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
    if (
        certification.capability_pack_hash != capability_pack_hash
        or certification.rules_artifact_hash != rules_artifact_hash
        or certification.corpus_artifact_hash != corpus_artifact_hash
        or certification.gold_dataset_sha256 != gold_dataset_sha256
        or certification.evaluation_policy_sha256 != evaluation_policy_sha256
        or certification.evaluation_run_sha256 != evaluation_run_sha256
    ):
        raise DeliveryAssuranceError("部署证据与法律内容双专家认证的哈希不一致")
    evidence = DeploymentEvidence(
        id=str(uuid4()),
        legal_content_certification_id=certification.id,
        environment=environment,
        target_environment_id=target_environment_id.strip(),
        commit_sha=commit_sha,
        migration_head=migration_head.strip(),
        ci_run_url=ci_run_url,
        artifact_sha256=artifact_sha256,
        sbom_sha256=sbom_sha256,
        security_evidence_url=security_evidence_url,
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
        .where(DeploymentEvidence.id == evidence.id, DeploymentEvidence.status == "verified")
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
        raise DeliveryAssuranceError("部署证据的 Capability Pack/规则/语料哈希与场景不一致")
    if (
        content_certification.capability_pack_hash != generation_config.capability_pack_hash
        or content_certification.rules_artifact_hash != generation_config.rules_artifact_hash
        or content_certification.corpus_artifact_hash != generation_config.corpus_artifact_hash
        or content_certification.gold_dataset_sha256 != deployment.gold_dataset_sha256
        or content_certification.evaluation_policy_sha256 != deployment.evaluation_policy_sha256
        or content_certification.evaluation_run_sha256 != deployment.evaluation_run_sha256
    ):
        raise DeliveryAssuranceError("法律内容双专家认证未覆盖当前规则、语料或 gold run")
    credential = db.get(LegalExpertCredential, attestation.credential_id)
    if credential is None or credential.valid_until is None or not _is_live(
        credential.status, credential.valid_until, now=now
    ):
        raise DeliveryAssuranceError("专家执业凭证已失效")
    if (
        attestation.signature_validation_status != "approved"
        or attestation.signature_verified_by is None
        or attestation.signature_verified_at is None
    ):
        raise DeliveryAssuranceError("专家数字签名尚未经独立核验")
    snapshot = build_delivery_snapshot(db, scenario=scenario, generation_config=generation_config)
    snapshot_hash = stable_hash(snapshot)
    if attestation.snapshot_hash != snapshot_hash or acceptance.snapshot_hash != snapshot_hash:
        raise DeliveryAssuranceError("签署或 UAT 已因项目快照变化而失效")
    max_expiry = min(
        _as_utc(attestation.expires_at),
        _as_utc(acceptance.expires_at),
        _as_utc(deployment.expires_at),
    )
    if _as_utc(expires_at) <= now or _as_utc(expires_at) > max_expiry:
        raise DeliveryAssuranceError("发布有效期不得超过签署、UAT 或部署证据的最早有效期")
    release_body = {
        "schema_version": "1.0",
        "scenario_id": scenario.id,
        "snapshot_hash": snapshot_hash,
        "expert_attestation_id": attestation.id,
        "uat_acceptance_id": acceptance.id,
        "deployment_evidence_id": deployment.id,
        "released_by": user.id,
        "released_at": now.isoformat(),
        "expires_at": _as_utc(expires_at).isoformat(),
    }
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
        release_note=release_note.strip(),
        status="active",
        released_by=user.id,
        released_at=now,
        expires_at=expires_at,
    )
    db.add(release)
    artifact_ids = [item.get("artifact_id") for item in attestation.artifact_manifest or []]
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
        snapshot = build_delivery_snapshot(db, scenario=scenario, generation_config=generation_config)
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
    attestation = acceptance = deployment = None
    if release is None:
        reasons.append("active_delivery_release_missing")
    else:
        if _as_utc(release.expires_at) <= now:
            reasons.append("delivery_release_expired")
        if snapshot_hash is None or release.snapshot_hash != snapshot_hash:
            reasons.append("delivery_release_snapshot_stale")
        release_body = {
            "schema_version": "1.0",
            "scenario_id": release.scenario_id,
            "snapshot_hash": release.snapshot_hash,
            "expert_attestation_id": release.expert_attestation_id,
            "uat_acceptance_id": release.uat_acceptance_id,
            "deployment_evidence_id": release.deployment_evidence_id,
            "released_by": release.released_by,
            "released_at": _as_utc(release.released_at).isoformat(),
            "expires_at": _as_utc(release.expires_at).isoformat(),
        }
        if stable_hash(release_body) != release.release_hash:
            reasons.append("delivery_release_hash_invalid")
        attestation = db.get(ScenarioExpertAttestation, release.expert_attestation_id)
        acceptance = db.get(ScenarioUATAcceptance, release.uat_acceptance_id)
        deployment = db.get(DeploymentEvidence, release.deployment_evidence_id)
        if attestation is None or not _is_live(attestation.status, attestation.expires_at, now=now):
            reasons.append("expert_attestation_inactive")
        elif (
            attestation.signature_validation_status != "approved"
            or not attestation.signature_verified_by
            or not attestation.signature_verified_at
            or stable_hash(attestation.snapshot or {}) != attestation.snapshot_hash
            or stable_hash(attestation.artifact_manifest or {}) != attestation.artifact_manifest_hash
            or attestation.scenario_id != scenario.id
            or attestation.snapshot_hash != release.snapshot_hash
        ):
            reasons.append("expert_signature_or_manifest_invalid")
        else:
            manifest = list(attestation.artifact_manifest or [])
            if {item.get("artifact_type") for item in manifest} != {
                "docx",
                "pdf",
                "audit_bundle",
            }:
                reasons.append("delivery_artifact_set_invalid")
            for item in manifest:
                artifact = db.get(ScenarioDeliveryArtifact, item.get("artifact_id"))
                if (
                    artifact is None
                    or artifact.scenario_id != scenario.id
                    or artifact.snapshot_hash != release.snapshot_hash
                    or artifact.status != "released"
                    or artifact.content_sha256 != item.get("content_sha256")
                    or artifact.content_length != item.get("content_length")
                    or hashlib.sha256(artifact.content).hexdigest() != artifact.content_sha256
                    or len(artifact.content) != artifact.content_length
                ):
                    reasons.append(f"delivery_artifact_invalid:{item.get('artifact_type')}")
        if acceptance is None or not _is_live(acceptance.status, acceptance.expires_at, now=now):
            reasons.append("customer_uat_inactive")
        elif (
            acceptance.scenario_id != scenario.id
            or attestation is None
            or acceptance.expert_attestation_id != attestation.id
            or acceptance.snapshot_hash != release.snapshot_hash
        ):
            reasons.append("customer_uat_binding_invalid")
        if deployment is None or not _is_live(deployment.status, deployment.expires_at, now=now):
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
            content_certification = db.get(
                LegalContentCertification, deployment.legal_content_certification_id
            )
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
            elif stable_hash(_content_certification_manifest(content_certification)) != (
                content_certification.certification_manifest_hash
            ):
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
            credential = db.get(LegalExpertCredential, attestation.credential_id)
            if credential is None or credential.valid_until is None or not _is_live(
                credential.status, credential.valid_until, now=now
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

    unique_reasons = sorted(set(reasons))
    return {
        "schema_version": "1.0",
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
            {**report, "delivery_allowed": False, "blocking_reasons": ["artifact_not_released"]}
        )
    artifact = db.get(ScenarioDeliveryArtifact, manifest_item.get("artifact_id"))
    if artifact is None or artifact.status != "released":
        raise DeliveryGateBlocked(
            {**report, "delivery_allowed": False, "blocking_reasons": ["artifact_not_released"]}
        )
    return report, artifact
