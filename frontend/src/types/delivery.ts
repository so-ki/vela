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
  status: 'certified' | 'revoked'
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
  status: 'verified' | 'revoked'
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
  released_at: string
  expires_at: string
}
