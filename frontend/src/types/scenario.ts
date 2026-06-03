export interface DimensionInfo {
  id: string
  name: string
  name_pt: string
  description: string
  order: number
}

export interface RulesCatalog {
  pack?: { id: string; name: string; version?: string; focus?: string }
  jurisdiction: { id: string; name: string; name_pt: string }
  industries: { id: string; name: string; sub_sectors?: { id: string; name: string }[] }[]
  action_types: { id: string; name: string }[]
  dimensions: DimensionInfo[]
  supported_locations: {
    country: string
    state: string
    state_name: string
    city: string
    city_name: string
  }[]
}

export interface ScenarioFormData {
  project_name: string
  country: string
  state: string
  city: string
  industry: string
  action_type: string
  investment_structure?: string
  description: string
  employee_count?: number
  capacity_notes?: string
  facility_notes?: string
  compliance_dimensions: string[]
  board_date?: string
  start_date?: string
  production_date?: string
  remarks?: string
}

export interface LegalHit {
  id: string
  source: string
  source_label: string
  urn: string
  url: string
  title_pt: string
  title_zh: string
  excerpt_pt: string
  excerpt_zh: string
  validity: string
  level: string
  published_at: string
  match_score: number
  vector_similarity: number
  keyword_overlap: number
  requires_review: boolean
}

export interface ChecklistItem {
  code: string
  title: string
  description: string
  priority: string
  relevance_score: number
  rationale: string
  matched_triggers: string[]
  sub_sector_tags?: string[]
  status: string
  legal_hits?: LegalHit[]
  retrieval_status?: string
}

export interface ChecklistSection {
  dimension_id: string
  dimension_name: string
  dimension_name_pt: string
  description: string
  items: ChecklistItem[]
}

export interface Checklist {
  id: number
  title: string
  version: string
  total_items: number
  jurisdiction: string
  industry_pack_name?: string
  detected_industry: string
  detected_industry_name: string
  detected_sub_sectors?: { id: string; name: string; matched_keywords?: string[] }[]
  detected_action_type: string
  detected_action_type_name: string
  selected_dimensions: string[]
  sections: ChecklistSection[]
  disclaimer: string
  created_at: string
}

export interface Scenario {
  id: number
  project_name: string
  country: string
  state: string
  city: string
  industry: string
  action_type: string
  investment_structure: string | null
  description: string
  employee_count: number | null
  capacity_notes: string | null
  facility_notes: string | null
  compliance_dimensions: string[]
  board_date: string | null
  start_date: string | null
  production_date: string | null
  remarks: string | null
  status: string
  created_at: string
  checklist: Checklist | null
  business_feedback?: BusinessFeedback | null
  can_revise?: boolean
  revision_round?: number
}

export interface BusinessFeedbackItem {
  code: string
  title: string
  dimension_name: string
  decision: string
  comment: string | null
  external_counsel_required: boolean
  reviewed_at: string | null
}

export interface BusinessFeedback {
  review_status: string
  is_finalized: boolean
  is_returned?: boolean
  approved_count: number
  rejected_count: number
  pending_count: number
  action_required: boolean
  summary: string
  return_note?: string | null
  items: BusinessFeedbackItem[]
}

export interface LegalRetrievalResult {
  scenario_id: number
  total_hits: number
  zero_hit_items: string[]
  sections: ChecklistSection[]
  disclaimer: string
  index_status: { installed?: boolean; document_count: number }
}

export interface ScenarioSummary {
  id: number
  project_name: string
  city: string
  industry: string
  status: string
  total_items: number | null
  created_at: string
  submitter_name?: string | null
  submitter_organization?: string | null
  progress_status?: string | null
  review_priority?: string | null
  blocked_count?: number | null
  passed_count?: number | null
  legal_rejected_count?: number | null
  feedback_action_required?: boolean | null
  needs_revision?: boolean | null
}

export interface BriefCitation {
  id: string
  source_label: string
  title_zh: string
  title_pt: string
  url: string
  match_score: number
  requires_review: boolean
}

export interface BriefItem {
  code: string
  title: string
  priority: string
  gate_status: string
  match_score: number
  requires_review: boolean
  block_reason?: string | null
  risk_zh: string
  risk_pt: string
  citations: BriefCitation[]
}

export interface BriefSection {
  dimension_id: string
  dimension_name: string
  dimension_name_pt: string
  risk_level: string
  summary_zh: string
  summary_pt: string
  items: BriefItem[]
}

export interface RiskBrief {
  scenario_id: number
  status: string
  threshold: number
  title_zh: string
  title_pt: string
  summary_zh: string
  summary_pt: string
  sections: BriefSection[]
  blocked_items: BriefItem[]
  passed_count: number
  blocked_count: number
  disclaimer: string
  generated_at: string
  mode: string
  llm_provider?: string | null
  llm_model?: string | null
  llm_error?: string | null
  llm_polish_skipped?: string | null
}

export interface ReviewItem {
  code: string
  title: string
  dimension_name: string
  gate_status: string
  match_score: number
  decision: string
  comment?: string | null
  external_counsel_required?: boolean
  legal_hits?: LegalHit[]
  reviewed_at?: string | null
}

export interface ReviewState {
  scenario_id: number
  status: string
  reviewer_name: string
  started_at: string
  finalized_at?: string | null
  items: ReviewItem[]
  approved_count: number
  rejected_count: number
  pending_count: number
  can_finalize: boolean
  can_export: boolean
  can_return_to_business?: boolean
}
