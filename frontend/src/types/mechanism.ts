export type MaterialState =
  | 'missing'
  | 'received'
  | 'unreadable'
  | 'ambiguous'
  | 'verified'
  | 'not_applicable'

export interface MaterialLedgerEntry {
  id: string
  scenario_id: number
  block_id: string
  source_document: string
  state: MaterialState
  state_at: string
  extraction_task_id: string | null
  note: string | null
  confirmation_note: string | null
  confirmed_by: number | null
  confirmed_at: string | null
  state_history: Array<Record<string, unknown>>
  revision: number
  created_by: number
  created_at: string
  updated_at: string
}

export interface MaterialLedgerUpsertPayload {
  source_document: string
  state: MaterialState
  extraction_task_id?: string | null
  note?: string | null
  confirmation_note?: string | null
  expected_revision?: number | null
}

export interface CoverageTask {
  id: string
  scenario_id: number
  source: string
  state: MaterialState
  denominator_ref: string
  denominator_snapshot_hash: string
  denominator_items: string[]
  covered_items: string[]
  denominator_count: number
  covered_count: number
  missing_count: number
  note: string | null
  created_by: number
  created_at: string
  updated_at: string
}

export interface FactRecord {
  id: string
  scenario_id: number
  subject: string
  attribute: string
  value: string
  fact_time: string
  block_id: string
  fact_pack_version: string
  source_document: string | null
  status: 'submitted' | 'business_confirmed'
  confirmation_note: string | null
  business_confirmed_by: number | null
  business_confirmed_at: string | null
  created_by: number
  created_at: string
}

export interface FactRecordCreatePayload {
  subject: string
  attribute: string
  value: string
  fact_time: string
  block_id: string
  fact_pack_version: string
  source_document?: string | null
}

export interface ClaimDraft {
  checklist_code: string
  statement: string
  fact_refs: string[]
  evidence_refs: string[]
}

export interface ClaimRecord {
  id: string
  compilation_id: string
  scenario_id: number
  checklist_code: string
  statement: string
  status: 'refused' | 'awaiting_human_confirmation' | 'supported'
  fact_refs: string[]
  evidence_refs: string[]
  reason_codes: string[]
  confirmed_by: number | null
  confirmed_at: string | null
  confirmation_note: string | null
  created_at: string
  updated_at: string
}

export interface ClaimCompilation {
  id: string
  scenario_id: number
  compiler_version: string
  input_hash: string
  output_hash: string
  denominator_count: number
  ready_count: number
  refused_count: number
  input_snapshot: Record<string, unknown>
  created_by: number
  created_at: string
  claims: ClaimRecord[]
}

export interface CoverageProof {
  id: string
  scenario_id: number
  compilation_id: string
  denominator_ref: string
  denominator_hash: string
  denominator_count: number
  covered_count: number
  uncovered_count: number
  unanswerable_count: number
  proof: {
    schema_version?: string
    covered_checklist_codes?: string[]
    uncovered?: Array<{
      checklist_code: string
      status: string
      unanswerable_reasons: string[]
    }>
    answerability_rule?: string
    [key: string]: unknown
  }
  proof_hash: string
  created_by: number
  created_at: string
}

export interface DeliveryGateStatus {
  schema_version: '1.0'
  scenario_id: number
  evaluated_at: string
  delivery_allowed: boolean
  blocking_reasons: string[]
  snapshot_hash: string | null
  release_id: string | null
  release_hash: string | null
  expert_attestation_id: string | null
  uat_acceptance_id: string | null
  deployment_evidence_id: string | null
  boundary: string
}
