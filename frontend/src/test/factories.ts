import type { User } from '@/types'
import type {
  CapabilityPackIdentity,
  RulesCatalog,
  Scenario,
  ScenarioScopeProposal,
  ScenarioScopeSnapshot,
} from '@/types/scenario'

export const TEST_CAPABILITY_PACK: CapabilityPackIdentity = {
  pack_id: 'brazil_new_energy_greenfield',
  version: '1.0.0',
  pack_hash: 'pack-hash',
  status: 'active',
  display_name: '巴西 · 新能源制造 · 绿地设厂',
  description: '正式能力包',
  country: 'BR',
  industry: 'new_energy_manufacturing',
  action_type: 'greenfield_plant',
  languages: ['zh-CN', 'pt-BR'],
}

export function makeCatalog(
  capabilityOverrides: Partial<CapabilityPackIdentity> = {},
): RulesCatalog {
  return {
    capability_pack: { ...TEST_CAPABILITY_PACK, ...capabilityOverrides },
    rules_pack_id: 'brazil_new_energy',
    jurisdiction: { id: 'BR', name: '巴西', name_pt: 'Brasil' },
    industries: [{ id: 'new_energy_manufacturing', name: '新能源制造' }],
    action_types: [{ id: 'greenfield_plant', name: '绿地设厂' }],
    dimensions: [
      { id: 'labor', name: '劳工', name_pt: 'Trabalho', description: '劳动合规', order: 1 },
    ],
    supported_locations: [
      {
        country: 'BR',
        state: 'SP',
        state_name: '圣保罗州',
        city: 'Campinas',
        city_name: '坎皮纳斯',
      },
    ],
    material_fields: [],
    material_intake_policy: { submit_always_required: [] },
  }
}

export function makeProposal(): ScenarioScopeProposal {
  return {
    pack_id: TEST_CAPABILITY_PACK.pack_id,
    pack_version: TEST_CAPABILITY_PACK.version,
    pack_hash: TEST_CAPABILITY_PACK.pack_hash,
    rules_pack_id: 'brazil_new_energy',
    country: 'BR',
    state: 'SP',
    city: 'Campinas',
    industry: TEST_CAPABILITY_PACK.industry,
    action_type: TEST_CAPABILITY_PACK.action_type,
    proposal_hash: 'proposal-hash-0000000000000001',
    labels: {
      country: '巴西',
      industry: '新能源制造',
      action_type: '绿地设厂',
      pack: TEST_CAPABILITY_PACK.display_name,
    },
  }
}

export function makeSnapshot(
  overrides: Partial<ScenarioScopeSnapshot> = {},
): ScenarioScopeSnapshot {
  return {
    capability_pack_id: TEST_CAPABILITY_PACK.pack_id,
    capability_pack_version: TEST_CAPABILITY_PACK.version,
    capability_pack_hash: TEST_CAPABILITY_PACK.pack_hash,
    issue_modules: ['labor'],
    rules_artifact_id: 'brazil_new_energy',
    rules_artifact_version: '2.9',
    rules_artifact_hash: 'rules-hash',
    corpus_artifact_id: 'brazil_legal_corpus',
    corpus_artifact_version: '1.9',
    corpus_artifact_hash: 'corpus-hash',
    retrieval_config: {},
    output_profile: {},
    rules_pack_id: 'brazil_new_energy',
    country: 'BR',
    state: 'SP',
    city: 'Campinas',
    industry: TEST_CAPABILITY_PACK.industry,
    action_type: TEST_CAPABILITY_PACK.action_type,
    rules_pack_version: '2.9',
    rules_pack_hash: 'rules-hash',
    corpus_version: '1.9',
    corpus_manifest_hash: 'corpus-hash',
    generation_config_hash: 'generation-config-hash',
    compliance_dimensions: ['labor'],
    selected_issue_codes: ['LAB-X'],
    match_threshold: 75,
    retrieval_top_k: 1,
    expansion_enabled: true,
    expansion_candidate_top_k: 2,
    expansion_min_keyword_score: 0.1,
    expansion_context_limit: 1200,
    polish: false,
    include_playbook_suggestions: false,
    playbook_suggestion_codes: [],
    profile_hash: 'profile-hash',
    code_adjustments: {},
    intent_dimension_expansion: false,
    fit_decision: 'accept_warning',
    generation_input_id: 'generation-input-id',
    generation_input_hash: 'generation-input-hash',
    audit_metadata: {
      confirmed_by: 2,
      confirmed_by_name: '演示法务',
      confirmed_at: '2026-07-14T00:00:00Z',
      labels: makeProposal().labels,
    },
    snapshot_hash: 'snapshot-hash',
    ...overrides,
  }
}

type ScenarioFactoryOptions = {
  status?: string
  frozen?: boolean
  snapshot?: ScenarioScopeSnapshot | null
  overrides?: Partial<Scenario>
}

export function makeScenario(options: ScenarioFactoryOptions = {}): Scenario {
  const status = options.status ?? 'scope_generation_failed'
  const hasFrozenSnapshot = options.frozen ?? true
  const snapshot = options.snapshot === undefined
    ? (hasFrozenSnapshot ? makeSnapshot() : null)
    : options.snapshot
  const scopeStatus = snapshot
    ? status === 'scope_generating'
      ? 'generating'
      : status === 'scope_generation_failed'
        ? 'generation_failed'
        : 'generated'
    : 'proposed'

  return {
    id: 9,
    project_name: '测试项目',
    rules_pack_id: 'brazil_new_energy',
    scenario_scope: {
      schema_version: '2.0',
      status: scopeStatus,
      proposed: makeProposal(),
      business_ack: {
        acknowledged: true,
        acknowledged_by: 1,
        acknowledged_by_name: '演示业务',
        acknowledged_at: '2026-07-14T00:00:00Z',
        statement_version: 'scope-notice-v1',
      },
      fit_assessment: {
        result: 'requires_legal_confirmation',
        reasons: ['需法务确认'],
      },
      snapshot,
    },
    is_demo: false,
    country: 'BR',
    state: 'SP',
    city: 'Campinas',
    industry: TEST_CAPABILITY_PACK.industry,
    action_type: TEST_CAPABILITY_PACK.action_type,
    investment_structure: null,
    investment_destination: null,
    project_content_scale: null,
    funding_source: null,
    description: '用于前端测试的巴西新能源制造绿地设厂项目。',
    known_risks: null,
    employee_count: null,
    capacity_notes: null,
    facility_notes: null,
    compliance_dimensions: snapshot?.compliance_dimensions ?? [],
    board_date: null,
    start_date: null,
    production_date: null,
    remarks: null,
    status,
    created_at: '2026-07-14T00:00:00Z',
    checklist: {
      id: 4,
      title: '专项核查清单',
      version: '1.0',
      total_items: 0,
      jurisdiction: 'BR',
      detected_industry: TEST_CAPABILITY_PACK.industry,
      detected_industry_name: '新能源制造',
      detected_action_type: TEST_CAPABILITY_PACK.action_type,
      detected_action_type_name: '绿地设厂',
      selected_dimensions: snapshot?.compliance_dimensions ?? [],
      sections: [],
      disclaimer: '仅供协查参考',
      created_at: '2026-07-14T00:00:00Z',
    },
    document_extract: {
      filename: 'project.txt',
      mode: 'rules',
      compliance_dimensions: ['labor'],
      facts: [],
      archived_files: [],
    },
    issue_suggestions: [],
    material_scope_findings: [],
    unverified_facts: [],
    ...options.overrides,
  }
}

export function makeBusinessUser(): User {
  return {
    id: 1,
    email: 'biz@demo.vela',
    full_name: '演示业务',
    organization: 'Demo Corp · 投资部',
    role: 'business',
    is_active: true,
    disclaimer_accepted: true,
    disclaimer_accepted_at: '2026-07-14T00:00:00Z',
    created_at: '2026-07-14T00:00:00Z',
  }
}
