import axios from 'axios'
import type { Disclaimer, ExportConfig, LoginResponse, SsoConfig, SystemStatus, User } from '@/types'

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
  const token = localStorage.getItem('vela_token')
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
  role: 'legal' | 'business'
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

export async function fetchRulesPacks(includePlanned = false) {
  const { data } = await api.get('/rules/packs', { params: { include_planned: includePlanned } })
  return data
}

export async function fetchRulesCatalog(packId?: string) {
  const { data } = await api.get('/rules/catalog', {
    params: packId ? { pack_id: packId } : undefined,
  })
  return data
}

export async function fetchDemoTemplate() {
  const { data } = await api.get('/rules/demo-template')
  return data
}

export async function createScenario(payload: Record<string, unknown>) {
  const { data } = await api.post('/scenarios', payload)
  return data
}

export async function createDemoScenario() {
  const { data } = await api.post('/scenarios/demo/byd-campinas')
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

export async function submitMaterialsDemo() {
  const { data } = await api.post('/scenarios/demo/submit-materials')
  return data
}

export async function generateAndSubmitScenario(payload: Record<string, unknown>, polish = false) {
  const { data } = await api.post(`/scenarios/generate-and-submit?polish=${polish}`, payload)
  return data
}

export async function generateAndSubmitDemo(polish = false) {
  const { data } = await api.post(`/scenarios/demo/generate-and-submit?polish=${polish}`)
  return data
}

export async function generateInvestigationPack(
  scenarioId: number,
  complianceDimensions: string[],
  polish = false,
  matchThreshold = 70,
  retrievalTopK = 3,
) {
  const { data } = await api.post(`/scenarios/${scenarioId}/generate-investigation`, {
    compliance_dimensions: complianceDimensions,
    polish,
    match_threshold: matchThreshold,
    retrieval_top_k: retrievalTopK,
  })
  return data
}

/** @deprecated 使用 generateInvestigationPack */
export async function confirmScenarioScope(
  scenarioId: number,
  complianceDimensions: string[],
  polish = false,
) {
  return generateInvestigationPack(scenarioId, complianceDimensions, polish)
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
  facts: Array<{ field: string; value: string; source_snippet?: string | null; source_filename?: string | null }>
  disclaimer: string
  llm_skipped?: string | null
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

export async function extractDocumentFromFile(file: File): Promise<DocumentExtractResult> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<DocumentExtractResult>('/scenarios/extract-document', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function extractDocumentsFromFiles(files: File[]): Promise<DocumentExtractBatchResult> {
  const form = new FormData()
  for (const file of files) {
    form.append('files', file)
  }
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

export async function returnScenarioToBusiness(scenarioId: number, note?: string) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/return-to-business`, { note: note || null })
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

export async function fetchScenario(id: number) {
  const { data } = await api.get(`/scenarios/${id}`)
  return data
}

export async function retrieveLegalSources(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/retrieve`)
  return data
}

export async function generateBrief(scenarioId: number, polish = true) {
  const { data } = await api.post(`/scenarios/${scenarioId}/brief`, null, {
    params: { polish },
  })
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
  payload: { decision: string; comment?: string; external_counsel_required?: boolean },
) {
  const { data } = await api.patch(`/scenarios/${scenarioId}/review/items/${itemCode}`, payload)
  return data
}

export async function finalizeReview(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/finalize`)
  return data
}

export async function approveAllReview(scenarioId: number) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/approve-all`)
  return data
}

export async function createFullSample() {
  const { data } = await api.post('/scenarios/demo/sample')
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

export async function runCorpusMaintenanceAgent(syncLexml = true, autoReindex = true) {
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
export async function fetchOnboardingStatus() {
  const { data } = await api.get('/onboarding/status')
  return data as { completed: boolean }
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
