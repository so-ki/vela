import axios from 'axios'
import type { Disclaimer, LoginResponse, SystemStatus, User } from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

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

export async function fetchRulesCatalog() {
  const { data } = await api.get('/rules/catalog')
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

export async function generateAndSubmitScenario(payload: Record<string, unknown>, polish = false) {
  const { data } = await api.post(`/scenarios/generate-and-submit?polish=${polish}`, payload)
  return data
}

export async function generateAndSubmitDemo(polish = false) {
  const { data } = await api.post(`/scenarios/demo/generate-and-submit?polish=${polish}`)
  return data
}

export interface DocumentExtractResult {
  filename: string
  mode: string
  project_name?: string | null
  investment_structure?: string | null
  description?: string | null
  employee_count?: number | null
  capacity_notes?: string | null
  facility_notes?: string | null
  remarks?: string | null
  compliance_dimensions: string[]
  facts: Array<{ field: string; value: string; source_snippet?: string | null }>
  disclaimer: string
  llm_skipped?: string | null
}

export async function extractDocumentFromFile(file: File): Promise<DocumentExtractResult> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<DocumentExtractResult>('/scenarios/extract-document', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function reviseAndResubmitScenario(
  scenarioId: number,
  payload: Record<string, unknown>,
  polish = false,
) {
  const { data } = await api.post(`/scenarios/${scenarioId}/revise-and-resubmit?polish=${polish}`, payload)
  return data
}

export async function returnScenarioToBusiness(scenarioId: number, note?: string) {
  const { data } = await api.post(`/scenarios/${scenarioId}/review/return-to-business`, { note: note || null })
  return data
}

export async function fetchScenarios() {
  const { data } = await api.get('/scenarios')
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
  const { data } = await api.get(`/scenarios/${scenarioId}/export/docx`, {
    responseType: 'blob',
  })
  return data as Blob
}

export async function downloadPdfExport(scenarioId: number) {
  const { data } = await api.get(`/scenarios/${scenarioId}/export/pdf`, {
    responseType: 'blob',
  })
  return data as Blob
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

export async function fetchMiningDemoTemplate() {
  const { data } = await api.get('/rules/demo-template/mining')
  return data
}

export async function fetchLegalStatus() {
  const { data } = await api.get('/legal/status')
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

export default api
