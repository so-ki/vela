export type DeliveryEvidenceKind =
  | 'oab_submission'
  | 'oab_verification_report'
  | 'iti_signature_artifact'
  | 'iti_validation_report'
  | 'uat_test_plan'
  | 'uat_test_evidence'
  | 'content_primary_signature'
  | 'content_primary_validation_report'
  | 'content_secondary_signature'
  | 'content_secondary_validation_report'
  | 'gold_dataset'
  | 'evaluation_policy'
  | 'evaluation_run'
  | 'build_artifact_descriptor'
  | 'build_artifact_receipt'
  | 'sbom'
  | 'security_report'
  | 'provenance'
  | 'runtime_probe'
  | 'config_schema'

export interface DeliveryEvidenceObject {
  id: string
  scenario_id: number | null
  evidence_kind: DeliveryEvidenceKind
  filename: string
  media_type: string
  content_sha256: string
  content_length: number
  source_url: string | null
  status: 'available' | 'revoked'
  uploaded_by: number
  uploaded_at: string
  expires_at: string | null
  revoked_by: number | null
  revoked_at: string | null
  revocation_reason: string | null
  created_at: string
}

export interface DeliveryArtifact {
  id: string
  scenario_id: number
  artifact_type: 'docx' | 'pdf' | 'audit_bundle'
  snapshot_hash: string
  content_sha256: string
  content_length: number
  media_type: string
  filename: string
  renderer_version: string
  status: 'candidate' | 'superseded' | 'released' | 'revoked'
  created_by: number
  created_at: string
}

export interface ArtifactManifest {
  scenario_id: number
  snapshot_hash: string
  artifact_manifest: Array<Record<string, unknown>>
  artifact_manifest_hash: string
}

export interface LegalCredential {
  id: string
  user_id: number
  holder_name: string
  jurisdiction: string
  authority: string
  registration_number: string
  official_register_url: string
  status: 'pending' | 'verified' | 'rejected' | 'revoked'
  registration_status: string | null
  verified_by: number | null
  valid_until: string | null
  revision: number
  created_at: string
}

export interface ExpertAttestation {
  id: string
  scenario_id: number
  credential_id: string
  signed_by: number
  snapshot_hash: string
  artifact_manifest_hash: string
  signature_format: string
  signature_validation_status: 'submitted' | 'approved' | 'rejected'
  signature_verified_by: number | null
  status: 'pending_validation' | 'active' | 'superseded' | 'rejected' | 'revoked'
  signed_at: string
  expires_at: string
}

export interface UATAcceptance {
  id: string
  scenario_id: number
  expert_attestation_id: string
  accepted_by: number
  customer_organization: string
  snapshot_hash: string
  target_environment_id: string
  status: 'accepted' | 'superseded' | 'withdrawn'
  accepted_at: string
  expires_at: string
}

export interface LegalContentCertification {
  id: string
  capability_pack_id: string
  capability_pack_version: string
  capability_pack_hash: string
  rules_artifact_hash: string
  corpus_artifact_hash: string
  certification_manifest_hash: string
  primary_credential_id: string
  secondary_credential_id: string
  status: 'certified' | 'revoked'
  certified_by: number
  certified_at: string
  expires_at: string
}

export interface DeploymentEvidence {
  id: string
  legal_content_certification_id: string
  environment: 'staging' | 'production'
  target_environment_id: string
  commit_sha: string
  migration_head: string
  artifact_receipt_hash: string | null
  security_evidence_sha256: string | null
  status: 'verified' | 'revoked'
  verified_by: number
  verified_at: string
  expires_at: string
}

export interface DeliveryRelease {
  id: string
  scenario_id: number
  expert_attestation_id: string
  uat_acceptance_id: string
  deployment_evidence_id: string
  snapshot_hash: string
  release_hash: string
  status: 'active' | 'superseded' | 'revoked'
  released_by: number
  released_at: string
  expires_at: string
}
