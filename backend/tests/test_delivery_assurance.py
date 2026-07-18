from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.delivery_assurance import (
    ScenarioDeliveryArtifact,
    ScenarioDeliveryRelease,
    ScenarioExpertAttestation,
)
from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.models.user import User
from app.services.delivery_assurance_service import (
    DeliveryAssuranceError,
    DeliveryAssurancePermissionError,
    DeliveryGateBlocked,
    build_legal_content_manifest,
    create_delivery_release,
    create_deployment_evidence,
    create_expert_attestation,
    create_legal_content_certification,
    create_uat_acceptance,
    decide_attestation_signature,
    decide_credential,
    current_delivery_artifact_manifest,
    evaluate_delivery_release,
    require_released_delivery_artifact,
    submit_credential,
)
from app.services.generation_guard import stable_hash
import app.services.delivery_assurance_service as delivery_service


@pytest.fixture()
def delivery_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'delivery.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(
                    id=1,
                    email="customer@example.com",
                    full_name="Customer Owner",
                    organization="Acme",
                    role="business",
                    disclaimer_accepted=True,
                ),
                User(
                    id=2,
                    email="expert@example.com",
                    full_name="Brazil Expert",
                    organization="Law Firm",
                    role="legal",
                    disclaimer_accepted=True,
                ),
                User(
                    id=3,
                    email="release-admin@example.com",
                    full_name="Release Admin",
                    organization="Acme",
                    role="admin",
                    disclaimer_accepted=True,
                ),
                User(
                    id=4,
                    email="second-expert@example.com",
                    full_name="Second Brazil Expert",
                    organization="Independent Law Firm",
                    role="legal",
                    disclaimer_accepted=True,
                ),
                User(
                    id=5,
                    email="independent-release-admin@example.com",
                    full_name="Independent Release Admin",
                    organization="Acme",
                    role="admin",
                    disclaimer_accepted=True,
                ),
            ]
        )
        scenario = InvestigationScenario(
            id=1,
            user_id=1,
            project_name="Controlled delivery",
            country="brazil",
            state="SP",
            city="Campinas",
            industry="new_energy",
            action_type="greenfield_plant",
            description="Controlled delivery test",
            compliance_dimensions=["environment"],
            status="review_approved",
            scope_snapshot_hash="a" * 64,
            is_demo=False,
        )
        scenario.checklist = ComplianceChecklist(
            title="Frozen checklist",
            version="v1",
            payload={
                "review": {
                    "status": "approved",
                    "finalized_at": "2026-07-18T00:00:00Z",
                    "finalized_by_id": 2,
                }
            },
            total_items=1,
        )
        db.add(scenario)
        db.commit()
    return factory


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        scenario_id=1,
        capability_pack_hash="1" * 64,
        rules_artifact_hash="2" * 64,
        corpus_artifact_hash="3" * 64,
    )


def test_real_delivery_chain_is_separated_hash_bound_and_fail_closed(
    delivery_db, monkeypatch
):
    now = datetime.now(timezone.utc)
    fixed_snapshot = {
        "schema_version": "1.0",
        "scenario_id": 1,
        "scope_snapshot_hash": "a" * 64,
        "mechanism": {"answerability_gate": {"decision": "passed"}},
    }
    monkeypatch.setattr(
        "app.services.delivery_assurance_service.build_delivery_snapshot",
        lambda db, *, scenario, generation_config: fixed_snapshot,
    )

    with delivery_db() as db:
        customer = db.get(User, 1)
        expert = db.get(User, 2)
        admin = db.get(User, 3)
        second_expert = db.get(User, 4)
        release_admin = db.get(User, 5)
        scenario = db.get(InvestigationScenario, 1)

        with pytest.raises(DeliveryAssurancePermissionError, match="管理员不得代签"):
            submit_credential(
                db,
                user=admin,
                holder_name="Release Admin",
                jurisdiction="BR",
                authority="OAB/SP",
                registration_number="000001",
                official_register_url="https://consulta.oab.org.br/",
                submitted_evidence_hash="4" * 64,
            )

        credential = submit_credential(
            db,
            user=expert,
            holder_name="Brazil Expert",
            jurisdiction="BR",
            authority="OAB/SP",
            registration_number="123456",
            official_register_url="https://consulta.oab.org.br/",
            submitted_evidence_hash="4" * 64,
        )
        with pytest.raises(DeliveryAssurancePermissionError):
            decide_credential(
                db,
                credential=credential,
                decision="verified",
                expected_revision=0,
                note="Self verification must be rejected.",
                user=expert,
                verification_reference="https://consulta.oab.org.br/",
                verification_evidence_hash="5" * 64,
                registration_status="regular",
                valid_until=now + timedelta(days=60),
            )
        credential = decide_credential(
            db,
            credential=credential,
            decision="verified",
            expected_revision=0,
            note="Independent OAB CNA and ConfirmADV evidence reviewed.",
            user=admin,
            verification_reference="https://confirmadv.oab.org.br/",
            verification_evidence_hash="5" * 64,
            registration_status="regular",
            valid_until=now + timedelta(days=60),
        )
        second_credential = submit_credential(
            db,
            user=second_expert,
            holder_name="Second Brazil Expert",
            jurisdiction="BR",
            authority="OAB/RJ",
            registration_number="654321",
            official_register_url="https://consulta.oab.org.br/",
            submitted_evidence_hash="a" * 64,
        )
        second_credential = decide_credential(
            db,
            credential=second_credential,
            decision="verified",
            expected_revision=0,
            note="Independent second OAB CNA and ConfirmADV evidence reviewed.",
            user=admin,
            verification_reference="https://confirmadv.oab.org.br/",
            verification_evidence_hash="b" * 64,
            registration_status="regular",
            valid_until=now + timedelta(days=60),
        )

        snapshot_hash = stable_hash(fixed_snapshot)
        artifacts = []
        for index, artifact_type in enumerate(("audit_bundle", "docx", "pdf"), start=1):
            content = f"frozen-{artifact_type}".encode()
            artifact = ScenarioDeliveryArtifact(
                id=f"00000000-0000-0000-0000-00000000000{index}",
                scenario_id=1,
                artifact_type=artifact_type,
                snapshot_hash=snapshot_hash,
                content_sha256=__import__("hashlib").sha256(content).hexdigest(),
                content_length=len(content),
                media_type="application/octet-stream",
                filename=f"artifact.{artifact_type}",
                renderer_version="test-renderer@commit",
                content=content,
                status="candidate",
                created_by=2,
            )
            db.add(artifact)
            artifacts.append(artifact)
        db.flush()
        manifest = [
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
        current_snapshot_hash, current_manifest, current_manifest_hash = (
            current_delivery_artifact_manifest(db, scenario_id=scenario.id)
        )
        assert current_snapshot_hash == snapshot_hash
        assert current_manifest == manifest
        assert current_manifest_hash == stable_hash(manifest)
        attestation_kwargs = {
            "scenario": scenario,
            "generation_config": _config(),
            "credential": credential,
            "artifact_ids": [item.id for item in artifacts],
            "signed_artifact_manifest_hash": stable_hash(manifest),
            "signature_format": "PAdES",
            "signature_artifact_hash": "6" * 64,
            "signature_validation_url": "https://validar.iti.gov.br/",
            "signature_validation_report_hash": "7" * 64,
            "certificate_serial": "ICP-BRASIL-123",
            "certificate_valid_until": now + timedelta(days=45),
            "statement": "I reviewed the frozen facts, legal sources, claims and exact artifact hashes.",
            "limitations": "This approval is limited to the frozen scope and stated legal date.",
            "expires_at": now + timedelta(days=30),
            "user": expert,
        }
        with pytest.raises(DeliveryAssuranceError, match="证书主体"):
            create_expert_attestation(
                db,
                certificate_subject="CN=Unrelated Signer",
                **attestation_kwargs,
            )
        with pytest.raises(DeliveryAssurancePermissionError, match="主审律师"):
            create_expert_attestation(
                db,
                scenario=scenario,
                generation_config=_config(),
                credential=second_credential,
                artifact_ids=[item.id for item in artifacts],
                signed_artifact_manifest_hash=stable_hash(manifest),
                signature_format="PAdES",
                signature_artifact_hash="c" * 64,
                signature_validation_url="https://validar.iti.gov.br/",
                signature_validation_report_hash="d" * 64,
                certificate_subject="CN=Second Brazil Expert",
                certificate_serial="ICP-BRASIL-OTHER",
                certificate_valid_until=now + timedelta(days=45),
                statement="A non-finalizing lawyer must not be allowed to sign this scenario.",
                limitations="Not applicable.",
                expires_at=now + timedelta(days=30),
                user=second_expert,
            )
        attestation = create_expert_attestation(
            db,
            certificate_subject="CN=Brazil Expert",
            **attestation_kwargs,
        )
        assert attestation.status == "pending_validation"
        tamper_target = artifacts[0]
        original_content = tamper_target.content
        db.execute(
            update(ScenarioDeliveryArtifact)
            .where(ScenarioDeliveryArtifact.id == tamper_target.id)
            .values(content=b"tampered-before-signature-approval")
        )
        db.flush()
        with pytest.raises(DeliveryAssuranceError, match="bytes、元数据或状态"):
            decide_attestation_signature(
                db,
                attestation=attestation,
                decision="approved",
                note="This must fail because the frozen bytes changed.",
                user=admin,
            )
        db.execute(
            update(ScenarioDeliveryArtifact)
            .where(ScenarioDeliveryArtifact.id == tamper_target.id)
            .values(content=original_content)
        )
        db.flush()
        attestation = decide_attestation_signature(
            db,
            attestation=attestation,
            decision="approved",
            note="ITI VALIDAR report independently checked against the frozen manifest.",
            user=admin,
        )
        assert attestation.status == "active"

        acceptance = create_uat_acceptance(
            db,
            scenario=scenario,
            attestation=attestation,
            customer_organization="Acme",
            test_plan_hash="8" * 64,
            test_evidence_hash="9" * 64,
            evidence_reference="https://evidence.example.com/uat/1",
            environment="customer_acceptance",
            target_environment_id="acme-prod-br-01",
            acceptance_statement="Customer owner accepts the frozen delivery set for the stated controlled scope.",
            expires_at=now + timedelta(days=20),
            user=customer,
        )
        content_limitations = (
            "Certification is limited to the frozen release and declared legal date."
        )
        content_manifest = build_legal_content_manifest(
            capability_pack_id="brazil_new_energy_greenfield",
            capability_pack_version="1.0",
            capability_pack_hash="1" * 64,
            rules_artifact_hash="2" * 64,
            corpus_artifact_hash="3" * 64,
            gold_dataset_sha256="4" * 64,
            evaluation_policy_sha256="5" * 64,
            evaluation_run_sha256="6" * 64,
            regression_status="passed",
            primary_credential_id=credential.id,
            secondary_credential_id=second_credential.id,
            limitations=content_limitations,
        )
        content_certification = create_legal_content_certification(
            db,
            capability_pack_id="brazil_new_energy_greenfield",
            capability_pack_version="1.0",
            capability_pack_hash="1" * 64,
            rules_artifact_hash="2" * 64,
            corpus_artifact_hash="3" * 64,
            gold_dataset_sha256="4" * 64,
            evaluation_policy_sha256="5" * 64,
            evaluation_run_sha256="6" * 64,
            regression_status="passed",
            primary_credential=credential,
            secondary_credential=second_credential,
            primary_signature_hash="7" * 64,
            primary_certificate_subject="CN=Brazil Expert",
            primary_certificate_serial="ICP-BRASIL-CONTENT-1",
            primary_validation_url="https://validar.iti.gov.br/",
            primary_validation_report_hash="8" * 64,
            secondary_signature_hash="9" * 64,
            secondary_certificate_subject="CN=Second Brazil Expert",
            secondary_certificate_serial="ICP-BRASIL-CONTENT-2",
            secondary_validation_url="https://validar.iti.gov.br/",
            secondary_validation_report_hash="a" * 64,
            signed_content_manifest_hash=stable_hash(content_manifest),
            limitations=content_limitations,
            expires_at=now + timedelta(days=20),
            user=admin,
        )
        deployment = create_deployment_evidence(
            db,
            legal_content_certification_id=content_certification.id,
            environment="production",
            target_environment_id="acme-prod-br-01",
            commit_sha="a" * 40,
            migration_head="20260718_0005",
            ci_run_url="https://github.com/acme/vela/actions/runs/1",
            artifact_sha256="a" * 64,
            sbom_sha256="b" * 64,
            security_evidence_url="https://evidence.example.com/security/1",
            provenance_url="https://evidence.example.com/provenance/1",
            provenance_sha256="c" * 64,
            runtime_probe_url="https://evidence.example.com/runtime/1",
            runtime_probe_sha256="d" * 64,
            backend_image_digest="sha256:" + "e" * 64,
            frontend_image_digest="sha256:" + "f" * 64,
            database_image_digest="sha256:" + "0" * 64,
            config_schema_sha256="1" * 64,
            capability_pack_hash="1" * 64,
            rules_artifact_hash="2" * 64,
            corpus_artifact_hash="3" * 64,
            gold_dataset_sha256="4" * 64,
            evaluation_policy_sha256="5" * 64,
            evaluation_run_sha256="6" * 64,
            regression_status="passed",
            verification_note="Production probes, provenance, SBOM, CVE policy and gold run reviewed.",
            expires_at=now + timedelta(days=15),
            user=admin,
        )
        with pytest.raises(
            DeliveryAssurancePermissionError, match="最终发布管理员必须独立"
        ):
            create_delivery_release(
                db,
                scenario=scenario,
                generation_config=_config(),
                attestation=attestation,
                acceptance=acceptance,
                deployment=deployment,
                release_note="The evidence verifier must not approve the final release.",
                expires_at=now + timedelta(days=10),
                user=admin,
            )
        release_note = "All independently supplied release prerequisites are present and hash-bound."
        release = create_delivery_release(
            db,
            scenario=scenario,
            generation_config=_config(),
            attestation=attestation,
            acceptance=acceptance,
            deployment=deployment,
            release_note=release_note,
            expires_at=now + timedelta(days=10),
            user=release_admin,
        )
        db.commit()
        report = evaluate_delivery_release(
            db, scenario=scenario, generation_config=_config()
        )
        assert report["delivery_allowed"] is True
        assert report["release_hash"] == release.release_hash
        _report, frozen_docx = require_released_delivery_artifact(
            db,
            scenario=scenario,
            generation_config=_config(),
            artifact_type="docx",
        )
        assert frozen_docx.content == b"frozen-docx"

        db.execute(
            update(ScenarioDeliveryRelease)
            .where(ScenarioDeliveryRelease.id == release.id)
            .values(release_note="tampered release decision")
        )
        db.commit()
        release_tamper_report = evaluate_delivery_release(
            db, scenario=scenario, generation_config=_config()
        )
        assert release_tamper_report["delivery_allowed"] is False
        assert (
            "delivery_release_hash_invalid" in release_tamper_report["blocking_reasons"]
        )
        db.execute(
            update(ScenarioDeliveryRelease)
            .where(ScenarioDeliveryRelease.id == release.id)
            .values(release_note=release_note)
        )
        db.commit()

        original_manifest = attestation.artifact_manifest
        original_manifest_hash = attestation.artifact_manifest_hash
        malformed_manifest = {"unexpected": "object-instead-of-list"}
        db.execute(
            update(ScenarioExpertAttestation)
            .where(ScenarioExpertAttestation.id == attestation.id)
            .values(
                artifact_manifest=malformed_manifest,
                artifact_manifest_hash=stable_hash(malformed_manifest),
            )
        )
        db.commit()
        malformed_manifest_report = evaluate_delivery_release(
            db, scenario=scenario, generation_config=_config()
        )
        assert malformed_manifest_report["delivery_allowed"] is False
        assert (
            "delivery_artifact_set_invalid"
            in malformed_manifest_report["blocking_reasons"]
        )
        db.execute(
            update(ScenarioExpertAttestation)
            .where(ScenarioExpertAttestation.id == attestation.id)
            .values(
                artifact_manifest=original_manifest,
                artifact_manifest_hash=original_manifest_hash,
            )
        )
        db.commit()

        original_change_lookup = delivery_service._active_legal_changes_after
        monkeypatch.setattr(
            delivery_service,
            "_active_legal_changes_after",
            lambda db, certified_at: [object()],
        )
        revalidation = evaluate_delivery_release(
            db, scenario=scenario, generation_config=_config()
        )
        assert revalidation["delivery_allowed"] is False
        assert "legal_change_revalidation_required" in revalidation["blocking_reasons"]
        monkeypatch.setattr(
            delivery_service,
            "_active_legal_changes_after",
            original_change_lookup,
        )

        second_credential = decide_credential(
            db,
            credential=second_credential,
            decision="revoked",
            expected_revision=1,
            note="Independent verifier revoked the second signer credential.",
            user=admin,
        )
        db.commit()
        revoked_signer_report = evaluate_delivery_release(
            db, scenario=scenario, generation_config=_config()
        )
        assert revoked_signer_report["delivery_allowed"] is False
        assert (
            "legal_content_signer_credentials_invalid"
            in revoked_signer_report["blocking_reasons"]
        )

        db.execute(
            update(ScenarioDeliveryArtifact)
            .where(ScenarioDeliveryArtifact.id == frozen_docx.id)
            .values(content=b"tampered-after-signature")
        )
        db.commit()
        with pytest.raises(DeliveryGateBlocked) as blocked:
            require_released_delivery_artifact(
                db,
                scenario=scenario,
                generation_config=_config(),
                artifact_type="docx",
            )
        assert any(
            reason.startswith("delivery_artifact_invalid:docx")
            for reason in blocked.value.report["blocking_reasons"]
        )
