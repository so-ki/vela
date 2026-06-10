export interface DimensionInfo {
  id: string
  name: string
  name_pt: string
  description: string
  order: number
}

export interface SceneDefaults {
  rules_pack_id: string
  country: string
  state: string
  city: string
  industry: string
  action_type: string
}

export interface RulesPackSummary {
  id: string
  name?: string
  version?: string
  region?: string
  primary_country?: string
  industry_focus?: string
  focus?: string
  status?: string
}

export interface RulesClassification {
  schema_version: string
  default_pack_id: string
  regions: Array<{
    id: string
    name: string
    name_en?: string
    countries: Array<{
      id: string
      name: string
      name_pt?: string
      status?: string
      default_pack_id?: string
      default_pack?: RulesPackSummary | null
    }>
  }>
  packs: RulesPackSummary[]
}

export interface RulesCatalog {
  rules_pack_id?: string
  pack?: {
    id: string
    name: string
    version?: string
    focus?: string
    region?: string
    primary_country?: string
    industry_focus?: string
  }
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
  scene_defaults?: SceneDefaults
  material_fields?: Array<{
    key: string
    label: string
    type: 'text' | 'number' | 'textarea' | 'date'
    section: 'core' | 'timeline'
    ui_group?: string
    always_required?: boolean
    min_length?: number
    rows?: number
  }>
  ui_groups?: Array<{
    id: string
    label: string
    hint?: string
    order?: number
  }>
  dimension_field_requirements?: Record<string, string[]>
  dimension_elements?: Record<
    string,
    Array<{
      id: string
      label: string
      required?: boolean
      maps_to_fields?: string[]
      extract_hints?: string[]
      feeds_checklist?: string[]
    }>
  >
  material_intake_policy?: {
    philosophy?: string
    business_action?: string
    archive_source_files?: boolean
    submit_always_required?: string[]
    user_confirm_fields?: string[]
    business_responsibility_hint?: string
    gate_a_by?: string
    accepted_upload_types?: string[]
  }
}

export interface ScenarioFormData {
  project_name: string
  rules_pack_id?: string
  country: string
  state: string
  city: string
  industry: string
  action_type: string
  investment_destination?: string
  investment_structure?: string
  funding_source?: string
  project_content_scale?: string
  description: string
  known_risks?: string
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
  industry_pack_id?: string
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
  rules_pack_id?: string | null
  country: string
  state: string
  city: string
  industry: string
  action_type: string
  investment_structure: string | null
  investment_destination: string | null
  project_content_scale: string | null
  funding_source: string | null
  description: string
  known_risks: string | null
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
  material_feedback?: MaterialFeedback | null
  material_scope_dimensions?: string[]
  can_revise?: boolean
  revision_round?: number
  document_extract?: DocumentExtractSnapshot | null
  investigation_adequacy?: InvestigationAdequacy | null
  gate_a_allows_review?: boolean
  can_return_materials?: boolean
  incremental_regen?: IncrementalRegen | null
  conflict_flags?: ConflictFlag[]
  investigation_settings?: InvestigationSettings | null
  playbook_deviations?: PlaybookDeviation[]
  grounding_report?: GroundingReport | null
  verification_report?: VerificationReport | null
  material_scope_findings?: MaterialScopeFinding[]
  issue_suggestions?: IssueSuggestion[]
  gap_explanations?: GapExplanations | null
  red_team?: RedTeamResult | null
  unverified_facts?: UnverifiedFact[]
  agent_steps?: AgentStep[]
}

export interface MaterialScopeFinding {
  rule_id: string
  label: string
  risk: string
  risk_label?: string
  guidance?: string
  feeds_checklist?: string[]
}

export interface IssueSuggestion {
  code: string
  title: string
  confidence: string
  fact_anchor: string
  rationale?: string
}

export interface GapExplanations {
  items?: Array<{
    code: string
    questions_zh?: string[]
    questions_pt?: string[]
    material_gaps?: string[]
    suggested_documents?: string[]
  }>
}

export interface RedTeamResult {
  challenges?: Array<{
    code: string
    questions: Array<{ question: string; severity: string }>
    red_team_note?: string
  }>
}

export interface UnverifiedFact {
  field?: string
  snippet?: string
  score?: number
  status?: string
}

export interface AgentStep {
  step: string
  status: string
  count?: number
}

export interface GroundingReport {
  total_hits?: number
  grounded_hits?: number
  grounding_rate?: number
  ungrounded_codes?: string[]
  requires_legal_check?: boolean
}

export interface VerificationReport {
  all_passed?: boolean
  summary?: string
  blocked_export_recommendation?: boolean
  passes?: Array<{
    id: string
    label: string
    passed: boolean
    detail: string
  }>
}

export interface PlaybookDeviation {
  id: string
  code: string
  title: string
  comment?: string | null
  recorded_at?: string
}

export interface InvestigationSettings {
  match_threshold?: number
  retrieval_top_k?: number
  expansion_enabled?: boolean
}

export interface ConflictFlag {
  id: string
  conflict_type: string
  severity: 'low' | 'medium' | 'high' | string
  title: string
  summary: string
  material_claim?: string
  source_label?: string
  suggested_action?: string
  affected_brief_sections?: string[]
}

export interface InvestigationAdequacyElement {
  id: string
  label: string
  required: boolean
  status: 'covered' | 'at_risk' | 'missing' | 'not_applicable'
  rationale: string
  excerpt: string
  source_label: string
  linked_codes: string[]
  avg_match_score: number
  passed_count: number
  blocked_count: number
  carry_forward?: boolean
}

export interface InvestigationAdequacyDimension {
  dimension_id: string
  dimension_name: string
  dimension_name_pt: string
  is_complete: boolean
  elements: InvestigationAdequacyElement[]
  law_preview: GateLawPreviewHit[]
  missing_element_ids: string[]
}

export interface TierReport {
  S1?: number
  S2?: number
  S3?: number
  s3_codes?: string[]
  has_hard_block?: boolean
}

export interface InvestigationAdequacy {
  mode: string
  compliance_dimensions: string[]
  is_material_complete: boolean
  is_investigation_ready: boolean
  suggest_material_return: string[]
  auto_missing_elements: string[]
  material_precheck_missing: string[]
  element_labels: Record<string, string>
  dimensions: InvestigationAdequacyDimension[]
  tier_report?: TierReport
  gap_summary?: {
    missing_count: number
    at_risk_count: number
    s2_count: number
    s3_count: number
    zero_hit_count: number
  }
  brief_summary: {
    passed_count: number
    blocked_count: number
    status?: string
  }
  carry_forward_stats?: {
    elements_carried?: number
    elements_recomputed?: number
  }
}

export interface IncrementalRegen {
  mode: 'incremental' | string
  changed_fields: string[]
  target_elements: string[]
  target_codes: string[]
  frozen_codes: string[]
  regenerated_at: string
  rag_stats?: {
    refreshed?: number
    carried?: number
    zero_hit_items?: string[]
  }
  adequacy_stats?: {
    elements_carried?: number
    elements_recomputed?: number
  }
  review_stats?: {
    items_carried?: number
    items_invalidated?: number
    items_refreshed?: number
  }
}

export interface DocumentExtractFileSnapshot {
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
  compliance_dimensions?: string[]
  facts: Array<{ field: string; value: string; source_snippet?: string | null; source_filename?: string | null }>
  disclaimer?: string
  llm_skipped?: string | null
}

export interface ExtractFieldConflict {
  field: string
  label: string
  sources: Array<{ filename: string; value: string }>
  merge_note: string
}

export interface DocumentExtractSnapshot {
  filename: string
  file_count?: number
  files?: DocumentExtractFileSnapshot[]
  mode: string
  source?: string
  extracted_at?: string | null
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
  compliance_dimensions?: string[]
  facts: Array<{ field: string; value: string; source_snippet?: string | null; source_filename?: string | null }>
  disclaimer?: string
  llm_skipped?: string | null
  field_conflicts?: ExtractFieldConflict[]
  archived_files?: Array<{
    id: string
    filename: string
    stored_name: string
    size: number
    content_type?: string
    archived_at?: string | null
  }>
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

export interface MaterialFeedbackItem {
  field_key: string
  label: string
  dimensions: string[]
}

export interface MaterialElementFeedbackItem {
  element_id: string
  label: string
  dimensions: string[]
}

export interface MaterialFeedback {
  return_kind: string
  is_returned: boolean
  action_required: boolean
  summary: string
  return_note?: string | null
  selected_dimensions: string[]
  missing_fields: string[]
  missing_elements?: string[]
  missing_by_dimension: Record<string, string[]>
  missing_elements_by_dimension?: Record<string, string[]>
  field_labels: Record<string, string>
  element_labels?: Record<string, string>
  items: MaterialFeedbackItem[]
  element_items?: MaterialElementFeedbackItem[]
}

export interface GateElementPreview {
  id: string
  label: string
  required: boolean
  status: 'filled' | 'missing' | 'not_applicable'
  excerpt: string
  source_label: string
  matched_hints?: string[]
  filled_fields?: string[]
  feeds_checklist?: string[]
}

export interface GateLawPreviewHit {
  id: string
  title_zh: string
  title_pt: string
  source_label: string
  url: string
  excerpt_zh: string
  preview_score: number
}

export interface GateDimensionBlock {
  dimension_id: string
  dimension_name: string
  dimension_name_pt: string
  is_complete: boolean
  elements: GateElementPreview[]
  law_preview: GateLawPreviewHit[]
}

export interface MaterialReviewPreview {
  compliance_dimensions: string[]
  gate_mode?: string
  is_complete?: boolean
  dimensions?: GateDimensionBlock[]
  auto_missing_elements?: string[]
  element_labels?: Record<string, string>
  required_fields: string[]
  auto_missing_fields: string[]
  missing_by_dimension: Record<string, string[]>
  field_values: Record<string, unknown>
  field_labels: Record<string, string>
  material_fields: RulesCatalog['material_fields']
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
  business_archived?: boolean
  legal_deleted?: boolean
  legal_deleted_at?: string | null
  has_document_extract?: boolean
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
  carry_forward?: boolean
  invalidated?: boolean
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
  version_label?: string | null
}
