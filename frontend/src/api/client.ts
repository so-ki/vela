import axios from 'axios'
import type {
  Disclaimer,
  ExportConfig,
  LoginResponse,
  OnboardingStatus,
  SsoConfig,
  SystemStatus,
  User,
} from '@/types'
import type { CapabilityPackIdentity, RulesCatalog, Scenario } from '@/types/scenario'
import type {
  ClaimCompilation,
  ClaimDraft,
  ClaimRecord,
  CoverageProof,
  CoverageTask,
  DeliveryGateStatus,
  FactRecord,
  FactRecordCreatePayload,
  MaterialLedgerEntry,
  MaterialLedgerUpsertPayload,
} from '@/types/mechanism'
import type {
  ArtifactManifest,
  DeliveryArtifact,
  DeliveryEvidenceKind,
  DeliveryEvidenceObject,
  DeliveryRelease,
  DeploymentEvidence,
  ExpertAttestation,
  LegalContentCertification,
  LegalCredential,
  UATAcceptance,
} from '@/types/delivery'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

function parseContentDisposition(header?: string): string | null {
  if (!header) return null
  const utfMatch = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utfMatch) return decodeURIComponent(utfMatch[1])
  const match = header.match(/filename="([^"]+)"/i)
  return match ? match[1] : null
}

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('vela_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export async function fetchDisclaimer(): Promise<Disclaimer> {
  const { data } = await api.get<Disclaimer>('/auth/disclaimer')
  return data
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login', { email, password })
  return data
}

export async function fetchSsoConfig(): Promise<SsoConfig> {
  const { data } = await api.get<SsoConfig>('/auth/sso/config')
  return data
}

export async function fetchExportConfig(): Promise<ExportConfig> {
  const { data } = await api.get<ExportConfig>('/export/config')
  return data
}

export async function register(payload: {
  email: string
  password: string
  full_name: string
  organization?: string
  accept_disclaimer: boolean
}): Promise<User> {
  const { data } = await api.post<User>('/auth/register', payload)
  return data
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>('/auth/me')
  return data
}

export async function acceptDisclaimer(): Promise<User> {
  const { data } = await api.post<User>('/auth/accept-disclaimer', { accept: true })
  return data
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get<SystemStatus>('/status')
  return data
}

export async function fetchRulesClassification() {
  const { data } = await api.get('/rules/classification')
  return data
}

export async function fetchRulesPacks(): Promise<CapabilityPackIdentity[]> {
  const { data } = await api.get<CapabilityPackIdentity[]>('/capability-packs')
  return data
}

export async function fetchRulesCatalog(): Promise<RulesCatalog> {
  const { data } = await api.get<RulesCatalog>('/capability-packs/catalog')
  return data
}

export async function submitMaterialsScenario(payload: Record<string, unknown>, files?: File[]) {
  if (files?.length) {
    const formData = new FormData()
    formData.append('payload', JSON.stringify(payload))
    for (const file of files) {
      formData.append('files', file)
    }
    const { data } = await api.post('/scenarios/submit-materials', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  }
  const { data } = await api.post('/scenarios/submit-materials', payload)
  return data
}

export async function generateInvestigationPack(
  scenarioId: number,
  complianceDimensions: string[],
  polish = false,
  matchThreshold = 70,
  retrievalTopK = 3,
  selectedIssueCodes: string[] = [],
  expectedProposalHash = '',
  fitDecision: 'fit' | 'accept_warning' = 'fit',
): Promise<Scenario> {
  const { data } = await api.post<Scenario>(`/scenarios/${scenarioId}/confirm-scope`, {
    compliance_dimensions: complianceDimensions,
    expected_proposal_hash: expectedProposalHash,
    fit_decision: fitDecision,
    polish,
    match_threshold: matchThreshold,
    retrieval_top_k: retrievalTopK,
    selected_issue_codes: selectedIssueCodes,
  })
  return data
}

export async function retryInvestigationPack(scenarioId: number): Promise<Scenario> {
  const { data } = await api.post<Scenario>(`/scenarios/${scenarioId}/retry-generation`)
  return data
}

export interface LlmSettings {
  available: boolean
  disabled_reason?: string | null
  enabled: boolean | null
  provider: string
  base_url: string
  api_key_masked: string
  has_api_key: boolean
  api_key_storage?: 'process_memory_ttl'
  default_model: string
  task_models: {
    extract: string
    issue_id: string
    gap: string
    red_team: string
    polish: string
  }
  provider_defaults: Record<string, { base_url?: string; default_model?: string }>
}

export async function fetchLlmSettings(): Promise<LlmSettings> {
  const { data } = await api.get('/llm/settings')
  return data
}

export async function patchLlmSettings(payload: Record<string, unknown>): Promise<LlmSettings> {
  const { data } = await api.patch('/llm/settings', payload)
  return data
}

export async function clearLlmApiKey(): Promise<LlmSettings> {
  const { data } = await api.delete('/llm/settings/api-key')
  return data
}

export async function testLlmConnection(payload: {
  provider: string
  base_url?: string
  api_key?: string
  model?: string
}) {
  const { data } = await api.post('/llm/test', payload)
  return data as { ok: boolean; latency_ms?: number; model?: string; error?: string }
}

export async function previewMaterialReview(scenarioId: number, complianceDimensions: string[]) {
  const { data } = await api.post(`/scenarios/${scenarioId}/material-review/preview`, {
    compliance_dimensions: complianceDimensions,
  })
  return data
}

export async function returnScenarioMaterials(
  scenarioId: number,
  payload: {
    compliance_dimensions: string[]
    missing_fields?: string[]
    missing_elements?: string[]
    note?: string | null
  },
) {
  const { data } = await api.post(`/scenarios/${scenarioId}/return-materials`, payload)
  return data
}

export interface DocumentExtractResult {
  filename: string
  mode: string
  project_name?: string | null
  investment_destination?: string | null
  investment_structure?: string | null
  funding_source?: string | null
  project_content_scale?: string | null
  description?: string | null
  known_risks?: string | null
  employee_count?: number | null
  capacity_notes?: string | null
  facility_notes?: string | null
  board_date?: string | null
  start_date?: string | null
  production_date?: string | null
  remarks?: string | null
  compliance_dimensions: string[]
  facts: Array<{
    field: string
    value: string
    source_snippet?: string | null
    source_filename?: string | null
    verification_status?: 'verified' | 'unverified' | 'weak_grounding'
    grounding_score?: number
  }>
  disclaimer: string
  llm_skipped?: string | null
  scan_or_empty?: boolean
  extraction_warning?: string | null
}

export interface ExtractFieldConflict {
  field: string
  label: string
  sources: Array<{ filename: string; value: string }>
  merge_note: string
}

export interface DocumentExtractBatchResult {
  files: DocumentExtractResult[]
  merged: DocumentExtractResult
  failed: string[]
  conflicts?: ExtractFieldConflict[]
}

export async function extractDocumentFromFile(file: File, llmConsent = false): Promise<DocumentExtractResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('llm_consent', String(llmConsent))
  const { data } = await api.post<DocumentExtractResult>('/scenarios/extract-document', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function extractDocumentsFromFiles(
  files: File[],
  llmConsent = false,
): Promise<DocumentExtractBatchResult> {
  const form = new FormData()
  for (const file of files) {
    form.append('files', file)
  }
  form.append('llm_consent', String(llmConsent))
  const { data } = await api.post<DocumentExtractBatchResult>('/scenarios/extract-documents', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function reviseAndResubmitScenario(
  scenarioId: number,
  payload: Record<string, unknown>,
  files?: File[],
) {
  if (files?.length) {
    const formData = new FormData()
    formData.append('payload', JSON.stringify(payload))
    for (const file of files) {
      formData.append('files', file)
    }
    const { data } = await api.post(`/scenarios/${scenarioId}/revise-and-resubmit`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  }
  const { data } = await api.post(`/scenarios/${scenarioId}/revise-and-resubmit`, payload)
  return data
}

export async function downloadScenarioMaterialFile(
  scenarioId: number,
  storedName: string,
  filename: string,
): Promise<void> {
  const { data } = await api.get(`/scenarios/${scenarioId}/material-files/${encodeURIComponent(storedName)}`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function returnScenarioToBusiness(
  scenarioId: number,
  expectedRevision: number,
  note?: string,
) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/return-to-business`, {
    note: note || null,
    expected_revision: expectedRevision,
  })
  return data
}

export async function fetchScenarios(includeArchived = false, includeDeleted = false) {
  const { data } = await api.get('/scenarios', {
    params: { include_archived: includeArchived, include_deleted: includeDeleted },
  })
  return data
}

export async function archiveScenario(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/archive`)
  return data
}

export async function unarchiveScenario(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/unarchive`)
  return data
}

export async function deleteScenario(scenarioId: number) {
  const { data } = await api.delete(`/scenarios/${scenarioId}`)
  return data
}

export async function restoreDeletedScenario(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/restore`)
  return data
}

export async function fetchScenario(id: number): Promise<Scenario> {
  const { data } = await api.get<Scenario>(`/scenarios/${id}`)
  return data
}

export async function fetchMaterialLedger(scenarioId: number): Promise<MaterialLedgerEntry[]> {
  const { data } = await api.get<MaterialLedgerEntry[]>(
    `/scenarios/${scenarioId}/mechanism/material-ledger`,
  )
  return data
}

export async function upsertMaterialLedgerEntry(
  scenarioId: number,
  blockId: string,
  payload: MaterialLedgerUpsertPayload,
): Promise<MaterialLedgerEntry> {
  const { data } = await api.put<MaterialLedgerEntry>(
    `/scenarios/${scenarioId}/mechanism/material-ledger/${encodeURIComponent(blockId)}`,
    payload,
  )
  return data
}

export async function fetchMechanismCoverageTasks(scenarioId: number): Promise<CoverageTask[]> {
  const { data } = await api.get<CoverageTask[]>(
    `/scenarios/${scenarioId}/mechanism/coverage-tasks`,
  )
  return data
}

export async function fetchFactRecords(scenarioId: number): Promise<FactRecord[]> {
  const { data } = await api.get<FactRecord[]>(`/scenarios/${scenarioId}/mechanism/facts`)
  return data
}

export async function createFactRecord(
  scenarioId: number,
  payload: FactRecordCreatePayload,
): Promise<FactRecord> {
  const { data } = await api.post<FactRecord>(
    `/scenarios/${scenarioId}/mechanism/facts`,
    payload,
  )
  return data
}

export async function confirmFactRecord(
  scenarioId: number,
  factId: string,
  confirmationNote: string,
): Promise<FactRecord> {
  const { data } = await api.post<FactRecord>(
    `/scenarios/${scenarioId}/mechanism/facts/${factId}/confirm`,
    { confirmation_note: confirmationNote },
  )
  return data
}

export async function fetchLatestClaimCompilation(
  scenarioId: number,
): Promise<ClaimCompilation | null> {
  try {
    const { data } = await api.get<ClaimCompilation>(
      `/scenarios/${scenarioId}/mechanism/claims/latest`,
    )
    return data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export async function compileMechanismClaims(
  scenarioId: number,
  drafts: ClaimDraft[],
): Promise<ClaimCompilation> {
  const { data } = await api.post<ClaimCompilation>(
    `/scenarios/${scenarioId}/mechanism/claims/compile`,
    { drafts },
  )
  return data
}

export async function confirmMechanismClaim(
  scenarioId: number,
  claimId: string,
  decision: 'confirmed' | 'rejected',
  confirmationNote: string,
): Promise<ClaimRecord> {
  const { data } = await api.post<ClaimRecord>(
    `/scenarios/${scenarioId}/mechanism/claims/${claimId}/confirm`,
    { decision, confirmation_note: confirmationNote },
  )
  return data
}

export async function fetchLatestCoverageProof(scenarioId: number): Promise<CoverageProof | null> {
  try {
    const { data } = await api.get<CoverageProof>(
      `/scenarios/${scenarioId}/mechanism/coverage-proofs/latest`,
    )
    return data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export async function createCoverageProof(
  scenarioId: number,
  compilationId?: string,
  denominatorRef = 'scenario-checklist',
): Promise<CoverageProof> {
  const { data } = await api.post<CoverageProof>(
    `/scenarios/${scenarioId}/mechanism/coverage-proofs`,
    {
      compilation_id: compilationId || null,
      denominator_ref: denominatorRef,
    },
  )
  return data
}

export async function fetchDeliveryGateStatus(
  scenarioId: number,
): Promise<DeliveryGateStatus> {
  const { data } = await api.get<DeliveryGateStatus>(
    `/scenarios/${scenarioId}/delivery-assurance/status`,
  )
  return data
}

export async function fetchDeliveryEvidenceObjects(
  scenarioId?: number,
): Promise<DeliveryEvidenceObject[]> {
  const { data } = await api.get<DeliveryEvidenceObject[]>(
    '/delivery-assurance/evidence-objects',
    { params: { scenario_id: scenarioId } },
  )
  return data
}

export async function uploadDeliveryEvidenceObject(payload: {
  evidenceKind: DeliveryEvidenceKind
  file: File
  scenarioId?: number
  sourceUrl?: string
  expiresAt?: string
}): Promise<DeliveryEvidenceObject> {
  const form = new FormData()
  form.append('evidence_kind', payload.evidenceKind)
  form.append('file', payload.file)
  if (payload.scenarioId !== undefined) form.append('scenario_id', String(payload.scenarioId))
  if (payload.sourceUrl) form.append('source_url', payload.sourceUrl)
  if (payload.expiresAt) form.append('expires_at', payload.expiresAt)
  const { data } = await api.post<DeliveryEvidenceObject>(
    '/delivery-assurance/evidence-objects',
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    },
  )
  return data
}

export async function downloadDeliveryEvidenceObject(evidenceId: string) {
  const response = await api.get(
    `/delivery-assurance/evidence-objects/${evidenceId}/download`,
    { responseType: 'blob' },
  )
  return {
    blob: response.data as Blob,
    filename:
      parseContentDisposition(response.headers['content-disposition']) || 'delivery-evidence.bin',
  }
}

export async function revokeDeliveryEvidenceObject(
  evidenceId: string,
  reason: string,
): Promise<DeliveryEvidenceObject> {
  const { data } = await api.post<DeliveryEvidenceObject>(
    `/delivery-assurance/evidence-objects/${evidenceId}/revoke`,
    { reason },
  )
  return data
}

export async function fetchDeliveryArtifacts(scenarioId: number): Promise<DeliveryArtifact[]> {
  const { data } = await api.get<DeliveryArtifact[]>(
    `/scenarios/${scenarioId}/delivery-assurance/artifacts`,
  )
  return data
}

export async function freezeDeliveryArtifacts(scenarioId: number): Promise<DeliveryArtifact[]> {
  const { data } = await api.post<DeliveryArtifact[]>(
    `/scenarios/${scenarioId}/delivery-assurance/artifacts`,
    { artifact_types: ['docx', 'pdf', 'audit_bundle'] },
  )
  return data
}

export async function fetchDeliveryArtifactManifest(
  scenarioId: number,
): Promise<ArtifactManifest> {
  const { data } = await api.get<ArtifactManifest>(
    `/scenarios/${scenarioId}/delivery-assurance/artifact-manifest`,
  )
  return data
}

export async function downloadCandidateArtifact(scenarioId: number, artifactId: string) {
  const response = await api.get(
    `/scenarios/${scenarioId}/delivery-assurance/artifacts/${artifactId}/candidate`,
    { responseType: 'blob' },
  )
  return {
    blob: response.data as Blob,
    filename:
      parseContentDisposition(response.headers['content-disposition']) ||
      'UNSIGNED_CANDIDATE.bin',
  }
}

export async function fetchLegalCredentials(): Promise<LegalCredential[]> {
  const { data } = await api.get<LegalCredential[]>('/delivery-assurance/credentials')
  return data
}

export async function submitLegalCredential(
  payload: Record<string, unknown>,
): Promise<LegalCredential> {
  const { data } = await api.post<LegalCredential>('/delivery-assurance/credentials', payload)
  return data
}

export async function decideLegalCredential(
  credentialId: string,
  payload: Record<string, unknown>,
): Promise<LegalCredential> {
  const { data } = await api.post<LegalCredential>(
    `/delivery-assurance/credentials/${credentialId}/decisions`,
    payload,
  )
  return data
}

export async function fetchExpertAttestations(
  scenarioId: number,
): Promise<ExpertAttestation[]> {
  const { data } = await api.get<ExpertAttestation[]>(
    `/scenarios/${scenarioId}/delivery-assurance/expert-attestations`,
  )
  return data
}

export async function submitExpertAttestation(
  scenarioId: number,
  payload: Record<string, unknown>,
): Promise<ExpertAttestation> {
  const { data } = await api.post<ExpertAttestation>(
    `/scenarios/${scenarioId}/delivery-assurance/expert-attestations`,
    payload,
  )
  return data
}

export async function decideExpertSignature(
  scenarioId: number,
  attestationId: string,
  payload: { decision: 'approved' | 'rejected'; note: string },
): Promise<ExpertAttestation> {
  const { data } = await api.post<ExpertAttestation>(
    `/scenarios/${scenarioId}/delivery-assurance/expert-attestations/${attestationId}/signature-decision`,
    payload,
  )
  return data
}

export async function revokeExpertAttestation(
  scenarioId: number,
  attestationId: string,
  reason: string,
): Promise<ExpertAttestation> {
  const { data } = await api.post<ExpertAttestation>(
    `/scenarios/${scenarioId}/delivery-assurance/expert-attestations/${attestationId}/revoke`,
    { reason },
  )
  return data
}

export async function fetchUATAcceptances(scenarioId: number): Promise<UATAcceptance[]> {
  const { data } = await api.get<UATAcceptance[]>(
    `/scenarios/${scenarioId}/delivery-assurance/uat-acceptances`,
  )
  return data
}

export async function submitUATAcceptance(
  scenarioId: number,
  payload: Record<string, unknown>,
): Promise<UATAcceptance> {
  const { data } = await api.post<UATAcceptance>(
    `/scenarios/${scenarioId}/delivery-assurance/uat-acceptances`,
    payload,
  )
  return data
}

export async function withdrawUATAcceptance(
  scenarioId: number,
  acceptanceId: string,
  reason: string,
): Promise<UATAcceptance> {
  const { data } = await api.post<UATAcceptance>(
    `/scenarios/${scenarioId}/delivery-assurance/uat-acceptances/${acceptanceId}/withdraw`,
    { reason },
  )
  return data
}

export async function fetchLegalContentCertifications(): Promise<LegalContentCertification[]> {
  const { data } = await api.get<LegalContentCertification[]>(
    '/delivery-assurance/legal-content-certifications',
  )
  return data
}

export async function previewLegalContentManifest(payload: Record<string, unknown>) {
  const { data } = await api.post<{ manifest: Record<string, unknown>; manifest_hash: string }>(
    '/delivery-assurance/legal-content-certifications/manifest',
    payload,
  )
  return data
}

export async function submitLegalContentCertification(
  payload: Record<string, unknown>,
): Promise<LegalContentCertification> {
  const { data } = await api.post<LegalContentCertification>(
    '/delivery-assurance/legal-content-certifications',
    payload,
  )
  return data
}

export async function revokeLegalContentCertification(
  certificationId: string,
  reason: string,
): Promise<LegalContentCertification> {
  const { data } = await api.post<LegalContentCertification>(
    `/delivery-assurance/legal-content-certifications/${certificationId}/revoke`,
    { reason },
  )
  return data
}

export async function fetchDeploymentEvidence(): Promise<DeploymentEvidence[]> {
  const { data } = await api.get<DeploymentEvidence[]>('/delivery-assurance/deployments')
  return data
}

export async function submitDeploymentEvidence(
  payload: Record<string, unknown>,
): Promise<DeploymentEvidence> {
  const { data } = await api.post<DeploymentEvidence>(
    '/delivery-assurance/deployments',
    payload,
  )
  return data
}

export async function revokeDeploymentEvidence(
  evidenceId: string,
  reason: string,
): Promise<DeploymentEvidence> {
  const { data } = await api.post<DeploymentEvidence>(
    `/delivery-assurance/deployments/${evidenceId}/revoke`,
    { reason },
  )
  return data
}

export async function fetchDeliveryReleases(scenarioId: number): Promise<DeliveryRelease[]> {
  const { data } = await api.get<DeliveryRelease[]>(
    `/scenarios/${scenarioId}/delivery-assurance/releases`,
  )
  return data
}

export async function submitDeliveryRelease(
  scenarioId: number,
  payload: Record<string, unknown>,
): Promise<DeliveryRelease> {
  const { data } = await api.post<DeliveryRelease>(
    `/scenarios/${scenarioId}/delivery-assurance/releases`,
    payload,
  )
  return data
}

export async function revokeDeliveryRelease(
  scenarioId: number,
  releaseId: string,
  reason: string,
): Promise<DeliveryRelease> {
  const { data } = await api.post<DeliveryRelease>(
    `/scenarios/${scenarioId}/delivery-assurance/releases/${releaseId}/revoke`,
    { reason },
  )
  return data
}

export async function fetchBrief(scenarioId: number) {
  const { data } = await api.get(`/scenarios/${scenarioId}/brief`)
  return data
}

export async function initReview(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/init`)
  return data
}

export async function fetchReview(scenarioId: number) {
  const { data } = await api.get(`/scenarios/${scenarioId}/review`)
  return data
}

export async function updateReviewItem(
  scenarioId: number,
  itemCode: string,
  payload: {
    decision: string
    comment?: string
    external_counsel_required?: boolean
    expected_revision: number
  },
) {
  const { data } = await api.patch(`/scenarios/${scenarioId}/review/items/${itemCode}`, payload)
  return data
}

export async function finalizeReview(scenarioId: number, expectedRevision: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/finalize`, undefined, {
    params: { expected_revision: expectedRevision },
  })
  return data
}

export async function approveAllReview(scenarioId: number, expectedRevision: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/approve-all`, undefined, {
    params: { expected_revision: expectedRevision },
  })
  return data
}

export async function submitScenarioForReview(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/submit`)
  return data
}

export async function downloadDocxExport(scenarioId: number) {
  const resp = await api.get(`/scenarios/${scenarioId}/export/docx`, {
    responseType: 'blob',
  })
  const filename =
    parseContentDisposition(resp.headers['content-disposition']) || 'vela_export.docx'
  return { blob: resp.data as Blob, filename }
}

export async function downloadPdfExport(scenarioId: number) {
  const resp = await api.get(`/scenarios/${scenarioId}/export/pdf`, {
    responseType: 'blob',
  })
  const filename =
    parseContentDisposition(resp.headers['content-disposition']) || 'vela_export.pdf'
  return { blob: resp.data as Blob, filename }
}

export async function fetchAuditBundle(scenarioId: number) {
  const { data } = await api.get(`/scenarios/${scenarioId}/export/audit-bundle`)
  return data
}

export async function downloadAuditBundle(scenarioId: number) {
  const bundle = await fetchAuditBundle(scenarioId)
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
  const filename = `vela_audit_bundle_${scenarioId}.json`
  return { blob, filename }
}

export async function fetchPlaybookDeviations(packId?: string) {
  const { data } = await api.get('/legal/playbook/deviations', {
    params: packId ? { pack_id: packId } : undefined,
  })
  return data
}

export async function fetchRulesPackSuggestions(packId?: string, minRejectCount = 2) {
  const { data } = await api.get('/legal/playbook/rules-pack-suggestions', {
    params: { pack_id: packId, min_reject_count: minRejectCount },
  })
  return data
}

export async function fetchRegFeedStatus() {
  const { data } = await api.get('/legal/reg-feed')
  return data
}

export async function scanRegFeed() {
  const { data } = await api.post('/legal/reg-feed/scan')
  return data
}

export async function fetchLegalMonitor() {
  const { data } = await api.get('/legal/monitor')
  return data
}

export async function scanLegalMonitor(forceReindex = false) {
  const { data } = await api.post('/legal/monitor/scan', null, {
    params: { force_reindex: forceReindex },
  })
  return data
}

export async function fetchLegalMonitorDiff() {
  const { data } = await api.get('/legal/monitor/diff')
  return data
}

export async function fetchLegalMonitorSubscriptions() {
  const { data } = await api.get('/legal/monitor/subscriptions')
  return data
}

export async function fetchMiningDemoTemplate() {
  const { data } = await api.get('/rules/demo-template/mining')
  return data
}

export async function fetchLegalStatus() {
  const { data } = await api.get('/legal/status')
  return data
}

export async function fetchUserPreferences() {
  const { data } = await api.get('/auth/preferences')
  return data
}

export async function updateRetrievalPreferences(payload: {
  match_threshold?: number
  retrieval_top_k?: number
}) {
  const { data } = await api.put('/auth/preferences/retrieval', payload)
  return data
}

export async function fetchCorpusAgentStatus() {
  const { data } = await api.get('/legal/corpus-agent/status')
  return data
}

export async function runCorpusMaintenanceAgent(syncLexml = true, autoReindex = false) {
  const { data } = await api.post('/legal/corpus-agent/run', null, {
    params: { sync_lexml: syncLexml, auto_reindex: autoReindex },
  })
  return data
}

export async function ackCorpusAgentNotification(notificationId: string) {
  const { data } = await api.post(`/legal/corpus-agent/notifications/${notificationId}/ack`)
  return data
}

export interface CorpusEntryPayload {
  id?: string
  source: string
  urn: string
  url: string
  title_pt: string
  title_zh: string
  dimension: string
  level: string
  validity: string
  published_at: string
  tags?: string[]
  checklist_codes?: string[]
  text_pt: string
  text_zh: string
}

export async function fetchCorpusMeta() {
  const { data } = await api.get('/legal/corpus/meta')
  return data
}

export async function fetchCorpusEntries(params?: {
  q?: string
  dimension?: string
  source?: string
}) {
  const { data } = await api.get('/legal/corpus', { params })
  return data
}

export async function fetchCorpusEntry(id: string) {
  const { data } = await api.get(`/legal/corpus/${id}`)
  return data
}

export async function createCorpusEntry(payload: CorpusEntryPayload) {
  const { data } = await api.post('/legal/corpus', payload)
  return data
}

export async function updateCorpusEntry(id: string, payload: Partial<CorpusEntryPayload>) {
  const { data } = await api.put(`/legal/corpus/${id}`, payload)
  return data
}

export async function deleteCorpusEntry(id: string) {
  const { data } = await api.delete(`/legal/corpus/${id}`)
  return data
}

export async function rebuildCorpusIndex(force = true) {
  const { data } = await api.post('/legal/corpus/reindex', null, { params: { force } })
  return data
}

export async function fetchLlmStatus() {
  const { data } = await api.get('/llm/status')
  return data
}

// —— 冷启动 / Playbook ——
export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  const { data } = await api.get<OnboardingStatus>('/onboarding/status')
  return data
}

export async function fetchInterviewScript() {
  const { data } = await api.get('/onboarding/interview/script')
  return data
}

export async function startInterview() {
  const { data } = await api.post('/onboarding/interview/start')
  return data
}

export async function submitInterviewAnswer(sessionId: string, questionId: string, answer: unknown) {
  const { data } = await api.post(
    `/onboarding/interview/${sessionId}/answer`,
    { question_id: questionId, answer },
    { timeout: 15000 },
  )
  return data
}

export async function syncInterviewAnswers(sessionId: string, answers: Record<string, unknown>) {
  const { data } = await api.post(
    `/onboarding/interview/${sessionId}/sync`,
    { answers },
    { timeout: 15000 },
  )
  return data
}

export async function uploadInterviewAttachment(
  sessionId: string,
  file: File,
  options: {
    purpose: string
    parse?: boolean
    parseInto?: string | null
    mergeMode?: 'append' | 'replace'
  },
) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`/onboarding/interview/${sessionId}/upload`, form, {
    params: {
      purpose: options.purpose,
      parse: options.parse !== false,
      parse_into: options.parseInto || undefined,
      merge_mode: options.mergeMode || 'append',
    },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
  return data as {
    meta: { id: string; original_name: string; purpose?: string }
    text?: string
    preview?: string
    parse_error?: string | null
    merged_field?: string | null
    merged_value?: string | null
  }
}

export async function completeInterview(sessionId: string) {
  const { data } = await api.post('/onboarding/interview/complete', { session_id: sessionId }, { timeout: 30000 })
  return data
}

export async function uploadPlaybookTemplate(file: File, sessionId?: string) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/onboarding/templates', form, {
    params: sessionId ? { session_id: sessionId } : undefined,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function fetchPlaybookProfile() {
  const { data } = await api.get('/onboarding/profile')
  return data
}

// —— 项目中心 ——
export async function fetchProjectHub(projectId: number) {
  const { data } = await api.get(`/projects/${projectId}/hub`)
  return data
}

export async function fetchProjectContext(projectId: number) {
  const { data } = await api.get(`/projects/${projectId}/context`)
  return data
}

export async function uploadProjectContract(projectId: number, file: File, contractType = 'general') {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`/projects/${projectId}/contracts/upload`, form, {
    params: { contract_type: contractType },
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function analyzeProjectContract(projectId: number, docId: string) {
  const { data } = await api.post(`/projects/${projectId}/contracts/analyze`, null, {
    params: { doc_id: docId },
  })
  return data
}

export async function fetchProjectContractAnalysis(projectId: number, docId: string) {
  const { data } = await api.get(`/projects/${projectId}/contracts/${docId}`)
  return data
}

export async function reviewContractFinding(
  projectId: number,
  docId: string,
  payload: { clause_index: number; decision: 'confirmed' | 'false_positive'; comment?: string },
) {
  const { data } = await api.post(`/projects/${projectId}/contracts/${docId}/findings/review`, payload)
  return data
}

export async function uploadDiligenceDocument(projectId: number, file: File, docCategory?: string) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`/projects/${projectId}/diligence/upload`, form, {
    params: docCategory ? { doc_category: docCategory } : undefined,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function analyzeProjectDiligence(projectId: number) {
  const { data } = await api.post(`/projects/${projectId}/diligence/analyze`)
  return data
}

export async function fetchDiligenceReport(projectId: number) {
  const { data } = await api.get(`/projects/${projectId}/diligence/report`)
  return data
}

export async function runProjectIntelligence(projectId: number) {
  const { data } = await api.post(`/projects/${projectId}/intelligence/run`)
  return data
}

export async function fetchIntelligenceReport(projectId: number) {
  const { data } = await api.get(`/projects/${projectId}/intelligence/report`)
  return data
}

export default api
