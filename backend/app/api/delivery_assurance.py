from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.roles import ROLE_ADMIN, is_legal_role
from app.models.delivery_assurance import (
    DeploymentEvidence,
    LegalContentCertification,
    LegalExpertCredential,
    ScenarioDeliveryRelease,
    ScenarioDeliveryArtifact,
    ScenarioExpertAttestation,
    ScenarioUATAcceptance,
)
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.delivery_assurance import (
    CredentialCreateRequest,
    CredentialDecisionRequest,
    CredentialResponse,
    DeliveryArtifactCreateRequest,
    DeliveryArtifactManifestResponse,
    DeliveryArtifactResponse,
    DeliveryGateStatusResponse,
    DeliveryReleaseCreateRequest,
    DeliveryReleaseResponse,
    DeploymentEvidenceCreateRequest,
    DeploymentEvidenceResponse,
    ExpertAttestationCreateRequest,
    ExpertAttestationResponse,
    LegalContentCertificationCreateRequest,
    LegalContentManifestRequest,
    LegalContentManifestResponse,
    LegalContentCertificationResponse,
    RevokeRequest,
    SignatureDecisionRequest,
    UATAcceptanceCreateRequest,
    UATAcceptanceResponse,
)
from app.services.audit import write_audit_log
from app.services.delivery_assurance_service import (
    DeliveryAssuranceConflict,
    DeliveryAssuranceError,
    DeliveryAssurancePermissionError,
    create_delivery_release,
    create_delivery_artifacts,
    create_deployment_evidence,
    create_expert_attestation,
    create_legal_content_certification,
    create_uat_acceptance,
    build_legal_content_manifest,
    decide_credential,
    decide_attestation_signature,
    evaluate_delivery_release,
    current_delivery_artifact_manifest,
    revoke_attestation,
    revoke_delivery_release,
    revoke_deployment_evidence,
    revoke_legal_content_certification,
    submit_credential,
    withdraw_uat,
)
from app.services.generation_guard import (
    GenerationGuardError,
    require_generated_result,
    stable_hash,
)


router = APIRouter(tags=["客户交付保证"])


def _require_admin_route(user: User) -> None:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="只有发布管理员可执行该操作")


def _load_scenario(db: Session, scenario_id: int, user: User) -> InvestigationScenario:
    scenario = (
        db.query(InvestigationScenario)
        .options(joinedload(InvestigationScenario.checklist))
        .filter(
            InvestigationScenario.id == scenario_id,
            InvestigationScenario.is_demo.is_(False),
            InvestigationScenario.legal_deleted_at.is_(None),
        )
        .first()
    )
    if scenario is None or scenario.checklist is None:
        raise HTTPException(status_code=404, detail="正式协查场景不存在")
    if scenario.user_id != user.id and not is_legal_role(user):
        raise HTTPException(status_code=403, detail="无权访问该协查场景")
    return scenario


def _entity(db: Session, model, entity_id: str, label: str):
    value = db.get(model, entity_id)
    if value is None:
        raise HTTPException(status_code=404, detail=f"{label}不存在")
    return value


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, DeliveryAssurancePermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, DeliveryAssuranceConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _config(db: Session, scenario: InvestigationScenario):
    try:
        return require_generated_result(db, scenario)
    except GenerationGuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _audit_detail(**values) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)


@router.post(
    "/delivery-assurance/credentials",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_credential(
    body: CredentialCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        credential = submit_credential(db, user=current_user, **body.model_dump())
        write_audit_log(
            db,
            user=current_user,
            action="delivery.credential_submit",
            resource_type="legal_expert_credential",
            resource_id=credential.id,
            detail=_audit_detail(
                jurisdiction=credential.jurisdiction,
                authority=credential.authority,
                registration_suffix=credential.registration_number[-4:],
                status=credential.status,
                automatic_verification=False,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(credential)
        return credential
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该执业登记已提交") from exc


@router.get(
    "/scenarios/{scenario_id}/delivery-assurance/artifacts",
    response_model=list[DeliveryArtifactResponse],
)
def get_delivery_artifacts(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    return (
        db.query(ScenarioDeliveryArtifact)
        .filter(ScenarioDeliveryArtifact.scenario_id == scenario_id)
        .order_by(ScenarioDeliveryArtifact.created_at.desc())
        .limit(100)
        .all()
    )


@router.get(
    "/scenarios/{scenario_id}/delivery-assurance/artifact-manifest",
    response_model=DeliveryArtifactManifestResponse,
)
def get_delivery_artifact_manifest(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    try:
        snapshot_hash, manifest, manifest_hash = current_delivery_artifact_manifest(
            db, scenario_id=scenario_id
        )
        return {
            "scenario_id": scenario_id,
            "snapshot_hash": snapshot_hash,
            "artifact_manifest": manifest,
            "artifact_manifest_hash": manifest_hash,
        }
    except DeliveryAssuranceError as exc:
        _raise_service_error(exc)


@router.get(
    "/scenarios/{scenario_id}/delivery-assurance/artifacts/{artifact_id}/candidate",
)
def download_candidate_artifact(
    scenario_id: int,
    artifact_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # The scenario owner must inspect the exact same bytes during UAT; legal and
    # admin users are admitted by _load_scenario for signature/release review.
    _load_scenario(db, scenario_id, current_user)
    artifact = _entity(db, ScenarioDeliveryArtifact, artifact_id, "冻结制品")
    if artifact.scenario_id != scenario_id or artifact.status != "candidate":
        raise HTTPException(status_code=404, detail="当前候选制品不存在")
    encoded_name = quote(artifact.filename)
    candidate_extension = "json" if artifact.artifact_type == "audit_bundle" else artifact.artifact_type
    write_audit_log(
        db,
        user=current_user,
        action="delivery.candidate_artifact_download",
        resource_type="scenario_delivery_artifact",
        resource_id=artifact.id,
        detail=_audit_detail(
            scenario_id=scenario_id,
            content_sha256=artifact.content_sha256,
            customer_delivery_authorized=False,
        ),
    )
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="UNSIGNED_CANDIDATE.{candidate_extension}"; '
                f"filename*=UTF-8''{encoded_name}"
            ),
            "Cache-Control": "no-store",
            "X-Content-SHA256": artifact.content_sha256,
            "X-Customer-Delivery-Authorized": "false",
        },
    )


@router.get("/delivery-assurance/credentials", response_model=list[CredentialResponse])
def get_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"legal", ROLE_ADMIN}:
        raise HTTPException(status_code=403, detail="只有法务或发布管理员可读取执业凭证")
    query = db.query(LegalExpertCredential)
    if current_user.role != ROLE_ADMIN:
        query = query.filter(LegalExpertCredential.user_id == current_user.id)
    return query.order_by(LegalExpertCredential.created_at.desc()).limit(200).all()


@router.post(
    "/delivery-assurance/credentials/{credential_id}/decisions",
    response_model=CredentialResponse,
)
def post_credential_decision(
    credential_id: str,
    body: CredentialDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    credential = _entity(db, LegalExpertCredential, credential_id, "执业凭证")
    before = credential.status
    try:
        credential = decide_credential(
            db,
            credential=credential,
            user=current_user,
            **body.model_dump(),
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.credential_decision",
            resource_type="legal_expert_credential",
            resource_id=credential.id,
            detail=_audit_detail(
                before=before,
                after=credential.status,
                holder_user_id=credential.user_id,
                independent_verifier=current_user.id != credential.user_id,
                valid_until=credential.valid_until,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(credential)
        return credential
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/artifacts",
    response_model=list[DeliveryArtifactResponse],
    status_code=status.HTTP_201_CREATED,
)
def post_delivery_artifacts(
    scenario_id: int,
    _body: DeliveryArtifactCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, scenario_id, current_user)
    try:
        artifacts = create_delivery_artifacts(
            db,
            scenario=scenario,
            generation_config=_config(db, scenario),
            user=current_user,
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.artifacts_freeze",
            resource_type="scenario",
            resource_id=str(scenario.id),
            detail=_audit_detail(
                snapshot_hash=artifacts[0].snapshot_hash,
                artifacts=[
                    {
                        "id": item.id,
                        "type": item.artifact_type,
                        "sha256": item.content_sha256,
                        "length": item.content_length,
                    }
                    for item in artifacts
                ],
                bytes_downloadable=False,
            ),
            commit=False,
        )
        db.commit()
        for artifact in artifacts:
            db.refresh(artifact)
        return artifacts
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/expert-attestations",
    response_model=ExpertAttestationResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_expert_attestation(
    scenario_id: int,
    body: ExpertAttestationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, scenario_id, current_user)
    credential = _entity(db, LegalExpertCredential, body.credential_id, "执业凭证")
    try:
        attestation = create_expert_attestation(
            db,
            scenario=scenario,
            generation_config=_config(db, scenario),
            credential=credential,
            user=current_user,
            **body.model_dump(exclude={"credential_id"}),
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.expert_attest",
            resource_type="scenario_expert_attestation",
            resource_id=attestation.id,
            detail=_audit_detail(
                scenario_id=scenario.id,
                credential_id=credential.id,
                snapshot_hash=attestation.snapshot_hash,
                expires_at=attestation.expires_at,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(attestation)
        return attestation
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get(
    "/scenarios/{scenario_id}/delivery-assurance/expert-attestations",
    response_model=list[ExpertAttestationResponse],
)
def get_expert_attestations(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    return (
        db.query(ScenarioExpertAttestation)
        .filter(ScenarioExpertAttestation.scenario_id == scenario_id)
        .order_by(ScenarioExpertAttestation.created_at.desc())
        .limit(200)
        .all()
    )


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/expert-attestations/{attestation_id}/signature-decision",
    response_model=ExpertAttestationResponse,
)
def post_attestation_signature_decision(
    scenario_id: int,
    attestation_id: str,
    body: SignatureDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    _load_scenario(db, scenario_id, current_user)
    attestation = _entity(db, ScenarioExpertAttestation, attestation_id, "专家签署")
    if attestation.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="专家签署不存在")
    try:
        attestation = decide_attestation_signature(
            db,
            attestation=attestation,
            decision=body.decision,
            note=body.note,
            user=current_user,
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.expert_signature_decision",
            resource_type="scenario_expert_attestation",
            resource_id=attestation.id,
            detail=_audit_detail(
                scenario_id=scenario_id,
                decision=body.decision,
                manifest_hash=attestation.artifact_manifest_hash,
                validation_report_hash=attestation.signature_validation_report_hash,
                signature_proves_content_correctness=False,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(attestation)
        return attestation
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/expert-attestations/{attestation_id}/revoke",
    response_model=ExpertAttestationResponse,
)
def post_revoke_attestation(
    scenario_id: int,
    attestation_id: str,
    body: RevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    attestation = _entity(db, ScenarioExpertAttestation, attestation_id, "专家签署")
    if attestation.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="专家签署不存在")
    try:
        attestation = revoke_attestation(
            db, attestation=attestation, reason=body.reason, user=current_user
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.expert_attestation_revoke",
            resource_type="scenario_expert_attestation",
            resource_id=attestation.id,
            detail=_audit_detail(scenario_id=scenario_id, reason=body.reason),
            commit=False,
        )
        db.commit()
        db.refresh(attestation)
        return attestation
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/uat-acceptances",
    response_model=UATAcceptanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_uat_acceptance(
    scenario_id: int,
    body: UATAcceptanceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, scenario_id, current_user)
    attestation = _entity(
        db, ScenarioExpertAttestation, body.expert_attestation_id, "专家签署"
    )
    try:
        acceptance = create_uat_acceptance(
            db,
            scenario=scenario,
            attestation=attestation,
            user=current_user,
            **body.model_dump(exclude={"expert_attestation_id"}),
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.uat_accept",
            resource_type="scenario_uat_acceptance",
            resource_id=acceptance.id,
            detail=_audit_detail(
                scenario_id=scenario.id,
                expert_attestation_id=attestation.id,
                snapshot_hash=acceptance.snapshot_hash,
                test_plan_hash=acceptance.test_plan_hash,
                test_evidence_hash=acceptance.test_evidence_hash,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(acceptance)
        return acceptance
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get(
    "/scenarios/{scenario_id}/delivery-assurance/uat-acceptances",
    response_model=list[UATAcceptanceResponse],
)
def get_uat_acceptances(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    return (
        db.query(ScenarioUATAcceptance)
        .filter(ScenarioUATAcceptance.scenario_id == scenario_id)
        .order_by(ScenarioUATAcceptance.created_at.desc())
        .limit(200)
        .all()
    )


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/uat-acceptances/{acceptance_id}/withdraw",
    response_model=UATAcceptanceResponse,
)
def post_withdraw_uat(
    scenario_id: int,
    acceptance_id: str,
    body: RevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    acceptance = _entity(db, ScenarioUATAcceptance, acceptance_id, "客户 UAT")
    if acceptance.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="客户 UAT 不存在")
    try:
        acceptance = withdraw_uat(
            db, acceptance=acceptance, reason=body.reason, user=current_user
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.uat_withdraw",
            resource_type="scenario_uat_acceptance",
            resource_id=acceptance.id,
            detail=_audit_detail(scenario_id=scenario_id, reason=body.reason),
            commit=False,
        )
        db.commit()
        db.refresh(acceptance)
        return acceptance
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/delivery-assurance/legal-content-certifications/manifest",
    response_model=LegalContentManifestResponse,
)
def post_legal_content_manifest(
    body: LegalContentManifestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"legal", ROLE_ADMIN}:
        raise HTTPException(status_code=403, detail="只有法务或发布管理员可生成签名清单")
    primary = _entity(
        db, LegalExpertCredential, body.primary_credential_id, "第一专家执业凭证"
    )
    secondary = _entity(
        db, LegalExpertCredential, body.secondary_credential_id, "第二专家执业凭证"
    )
    if primary.user_id == secondary.user_id:
        raise HTTPException(status_code=422, detail="签名清单必须绑定两名不同专家")
    manifest = build_legal_content_manifest(**body.model_dump())
    return {"manifest": manifest, "manifest_hash": stable_hash(manifest)}


@router.get(
    "/delivery-assurance/legal-content-certifications",
    response_model=list[LegalContentCertificationResponse],
)
def get_legal_content_certifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"legal", ROLE_ADMIN}:
        raise HTTPException(status_code=403, detail="只有法务或发布管理员可读取内容认证")
    return (
        db.query(LegalContentCertification)
        .order_by(LegalContentCertification.certified_at.desc())
        .limit(200)
        .all()
    )


@router.post(
    "/delivery-assurance/legal-content-certifications",
    response_model=LegalContentCertificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_legal_content_certification(
    body: LegalContentCertificationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    primary = _entity(
        db, LegalExpertCredential, body.primary_credential_id, "第一专家执业凭证"
    )
    secondary = _entity(
        db, LegalExpertCredential, body.secondary_credential_id, "第二专家执业凭证"
    )
    try:
        certification = create_legal_content_certification(
            db,
            primary_credential=primary,
            secondary_credential=secondary,
            user=current_user,
            **body.model_dump(
                exclude={"primary_credential_id", "secondary_credential_id"}
            ),
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.legal_content_certify",
            resource_type="legal_content_certification",
            resource_id=certification.id,
            detail=_audit_detail(
                capability_pack_hash=certification.capability_pack_hash,
                rules_artifact_hash=certification.rules_artifact_hash,
                corpus_artifact_hash=certification.corpus_artifact_hash,
                evaluation_run_sha256=certification.evaluation_run_sha256,
                primary_credential_id=certification.primary_credential_id,
                secondary_credential_id=certification.secondary_credential_id,
                two_distinct_experts=True,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(certification)
        return certification
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/delivery-assurance/legal-content-certifications/{certification_id}/revoke",
    response_model=LegalContentCertificationResponse,
)
def post_revoke_legal_content_certification(
    certification_id: str,
    body: RevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    certification = _entity(
        db, LegalContentCertification, certification_id, "法律内容认证"
    )
    try:
        certification = revoke_legal_content_certification(
            db, certification=certification, reason=body.reason, user=current_user
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.legal_content_certification_revoke",
            resource_type="legal_content_certification",
            resource_id=certification.id,
            detail=_audit_detail(reason=body.reason),
            commit=False,
        )
        db.commit()
        db.refresh(certification)
        return certification
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get(
    "/delivery-assurance/deployments",
    response_model=list[DeploymentEvidenceResponse],
)
def get_deployment_evidence(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    return (
        db.query(DeploymentEvidence)
        .order_by(DeploymentEvidence.verified_at.desc())
        .limit(200)
        .all()
    )


@router.post(
    "/delivery-assurance/deployments",
    response_model=DeploymentEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_deployment_evidence(
    body: DeploymentEvidenceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    try:
        evidence = create_deployment_evidence(
            db, user=current_user, **body.model_dump()
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.deployment_verify",
            resource_type="deployment_evidence",
            resource_id=evidence.id,
            detail=_audit_detail(
                environment=evidence.environment,
                commit_sha=evidence.commit_sha,
                artifact_sha256=evidence.artifact_sha256,
                sbom_sha256=evidence.sbom_sha256,
                expires_at=evidence.expires_at,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(evidence)
        return evidence
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/delivery-assurance/deployments/{evidence_id}/revoke",
    response_model=DeploymentEvidenceResponse,
)
def post_revoke_deployment_evidence(
    evidence_id: str,
    body: RevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    evidence = _entity(db, DeploymentEvidence, evidence_id, "部署证据")
    try:
        evidence = revoke_deployment_evidence(
            db, evidence=evidence, reason=body.reason, user=current_user
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.deployment_revoke",
            resource_type="deployment_evidence",
            resource_id=evidence.id,
            detail=_audit_detail(reason=body.reason),
            commit=False,
        )
        db.commit()
        db.refresh(evidence)
        return evidence
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/releases",
    response_model=DeliveryReleaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_delivery_release(
    scenario_id: int,
    body: DeliveryReleaseCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    scenario = _load_scenario(db, scenario_id, current_user)
    attestation = _entity(
        db, ScenarioExpertAttestation, body.expert_attestation_id, "专家签署"
    )
    acceptance = _entity(
        db, ScenarioUATAcceptance, body.uat_acceptance_id, "客户 UAT"
    )
    deployment = _entity(
        db, DeploymentEvidence, body.deployment_evidence_id, "部署证据"
    )
    try:
        release = create_delivery_release(
            db,
            scenario=scenario,
            generation_config=_config(db, scenario),
            attestation=attestation,
            acceptance=acceptance,
            deployment=deployment,
            release_note=body.release_note,
            expires_at=body.expires_at,
            user=current_user,
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.release_activate",
            resource_type="scenario_delivery_release",
            resource_id=release.id,
            detail=_audit_detail(
                scenario_id=scenario.id,
                snapshot_hash=release.snapshot_hash,
                release_hash=release.release_hash,
                expert_attestation_id=release.expert_attestation_id,
                uat_acceptance_id=release.uat_acceptance_id,
                deployment_evidence_id=release.deployment_evidence_id,
                separation_of_duties=current_user.id != attestation.signed_by,
            ),
            commit=False,
        )
        db.commit()
        db.refresh(release)
        return release
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get(
    "/scenarios/{scenario_id}/delivery-assurance/releases",
    response_model=list[DeliveryReleaseResponse],
)
def get_delivery_releases(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_scenario(db, scenario_id, current_user)
    return (
        db.query(ScenarioDeliveryRelease)
        .filter(ScenarioDeliveryRelease.scenario_id == scenario_id)
        .order_by(ScenarioDeliveryRelease.created_at.desc())
        .limit(200)
        .all()
    )


@router.post(
    "/scenarios/{scenario_id}/delivery-assurance/releases/{release_id}/revoke",
    response_model=DeliveryReleaseResponse,
)
def post_revoke_delivery_release(
    scenario_id: int,
    release_id: str,
    body: RevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_route(current_user)
    _load_scenario(db, scenario_id, current_user)
    release = _entity(db, ScenarioDeliveryRelease, release_id, "发布授权")
    if release.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="发布授权不存在")
    try:
        release = revoke_delivery_release(
            db, release=release, reason=body.reason, user=current_user
        )
        write_audit_log(
            db,
            user=current_user,
            action="delivery.release_revoke",
            resource_type="scenario_delivery_release",
            resource_id=release.id,
            detail=_audit_detail(scenario_id=scenario_id, reason=body.reason),
            commit=False,
        )
        db.commit()
        db.refresh(release)
        return release
    except (DeliveryAssuranceError, DeliveryAssurancePermissionError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get(
    "/scenarios/{scenario_id}/delivery-assurance/status",
    response_model=DeliveryGateStatusResponse,
)
def get_delivery_assurance_status(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_scenario(db, scenario_id, current_user)
    return evaluate_delivery_release(
        db,
        scenario=scenario,
        generation_config=_config(db, scenario),
    )
