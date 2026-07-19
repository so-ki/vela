import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import CompetitionWorkspaceView from './CompetitionWorkspaceView.vue'

const api = vi.hoisted(() => ({
  fetchScenario: vi.fn(),
  fetchMaterialLedger: vi.fn(),
  fetchFactRecords: vi.fn(),
  fetchLatestClaimCompilation: vi.fn(),
  fetchLatestResearchItems: vi.fn(),
  fetchLatestCoverageProof: vi.fn(),
  fetchDeliveryGateStatus: vi.fn(),
  fetchMechanismAuditEvents: vi.fn(),
}))

vi.mock('@/api/client', () => api)

const routerFor = () => createRouter({
  history: createMemoryHistory(),
  routes: [
    {
      path: '/competition/:id/:section?',
      name: 'competition-workspace',
      component: CompetitionWorkspaceView,
    },
    { path: '/rc0/:section?', name: 'rc0-workspace', component: { template: '<div />' } },
    { path: '/scenarios/:id/mechanism', name: 'mechanism', component: { template: '<div />' } },
    { path: '/scenarios/:id/extract', name: 'scenario-extract', component: { template: '<div />' } },
  ],
})

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchScenario.mockResolvedValue({
    id: 17,
    project_name: 'Aurora 储能系统集成工厂',
    country: 'BR',
    state: 'sao_paulo',
    city: '',
    industry: 'new_energy_manufacturing',
    action_type: 'greenfield_plant',
    scenario_scope: {
      snapshot: {
        capability_pack_version: '1.3.1',
        rules_artifact_version: '2.9',
        corpus_artifact_version: '1.13',
        snapshot_hash: 'a'.repeat(64),
      },
    },
    checklist: {
      sections: [{
        items: [{
          code: 'ENV-001',
          legal_hits: [{
            id: 'law-1',
            urn: 'urn:lex:br:test',
            title_zh: '环境许可测试法源',
            review_status: 'expert_verified',
            grounded: true,
            published_at: '2026-07-19',
          }],
        }],
      }],
    },
  })
  api.fetchMaterialLedger.mockResolvedValue([])
  api.fetchFactRecords.mockResolvedValue([{
    id: 'fact-1',
    subject: 'project',
    attribute: 'site',
    value: '圣保罗州，市级选址待定',
    assertion_polarity: 'affirmative',
    fact_time: '2026-07-19',
    block_id: 'upload:1',
    status: 'business_confirmed',
  }])
  const research = Array.from({ length: 30 }, (_, index) => ({
    id: `research-${index + 1}`,
    checklist_code: index === 0 ? 'ENV-001' : `ITEM-${String(index + 1).padStart(3, '0')}`,
    denominator_order: index + 1,
    title: index === 0 ? '环境许可路径' : `Pack item ${index + 1}`,
    dimension: index < 4 ? 'environment' : 'tax',
    scope_status: index < 4 ? 'in_scope' : 'out_of_scope_by_scope',
    screening_status: index === 0 ? 'selected_by_screening' : 'screened_out',
    disposition: index === 0 ? 'supported' : index < 4 ? 'uncovered' : null,
    research_status: index === 0 ? 'resolved' : index < 4 ? 'research_open' : 'out_of_scope',
    reason_codes: index === 0 ? [] : ['legal_claim_draft_missing'],
    linked_claim_id: index === 0 ? 'claim-1' : null,
  }))
  api.fetchLatestResearchItems.mockResolvedValue(research)
  api.fetchLatestClaimCompilation.mockResolvedValue({
    compiler_version: '0.3',
    input_hash: 'b'.repeat(64),
    output_hash: 'c'.repeat(64),
    claims: [{
      id: 'claim-1',
      checklist_code: 'ENV-001',
      statement: '限定的环境许可法务草稿。',
      status: 'supported',
      fact_refs: ['fact-1'],
      evidence_refs: ['ENV-001:law-1'],
      reason_codes: [],
      confirmation_note: '法务已确认。',
    }],
  })
  api.fetchLatestCoverageProof.mockResolvedValue({
    denominator_hash: 'd'.repeat(64),
    proof_hash: 'e'.repeat(64),
    proof: {
      schema_version: '0.2',
      pack_total: 30,
      scope_total: 4,
      out_of_scope_by_scope_count: 26,
      supported_count: 1,
      not_applicable_count: 0,
      rejected_count: 0,
      unanswerable_count: 0,
      uncovered_count: 3,
      answerability_rule: 'fixed denominator',
    },
  })
  api.fetchDeliveryGateStatus.mockResolvedValue({
    delivery_allowed: false,
    blocking_reasons: ['release_missing'],
    boundary: 'No active customer delivery release.',
    expert_attestation_id: null,
    uat_acceptance_id: null,
    deployment_evidence_id: null,
    release_id: null,
  })
  api.fetchMechanismAuditEvents.mockResolvedValue([{
    id: 1,
    user_id: 2,
    action: 'mechanism.claim_compile',
    resource_type: 'claim_compilation',
    resource_id: 'compilation-1',
    detail: 'scenario=17 denominator=30',
    created_at: '2026-07-19T12:00:00Z',
  }])
})

describe('competition live scenario workspace', () => {
  it('loads all eight core pages from the same formal scenario APIs', async () => {
    const router = routerFor()
    await router.push('/competition/17/overview')
    await router.isReady()
    const wrapper = mount(CompetitionWorkspaceView, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(api.fetchScenario).toHaveBeenCalledWith(17))

    for (const label of ['项目总览', '材料与事实', '固定 30 项', '法律研究', 'Claim 与缺口', 'CoverageProof', '交付中心', '审计记录']) {
      expect(wrapper.text()).toContain(label)
    }
    expect(wrapper.text()).toContain('LIVE SCENARIO API')
    expect(wrapper.text()).not.toContain('SYNTHETIC DEMO')
    expect(api.fetchLatestResearchItems).toHaveBeenCalledWith(17)
    expect(api.fetchMechanismAuditEvents).toHaveBeenCalledWith(17)
  })

  it('shows the real 30-item denominator, proof counts and blocked external release', async () => {
    const router = routerFor()
    await router.push('/competition/17/checklist')
    await router.isReady()
    const wrapper = mount(CompetitionWorkspaceView, { global: { plugins: [router] } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('ENV-001'))
    expect(wrapper.findAll('.rc0-checklist-row')).toHaveLength(30)

    await router.push('/competition/17/coverage')
    await nextTick()
    expect(wrapper.text()).toContain('Pack total')
    expect(wrapper.text()).toContain('0.2')

    await router.push('/competition/17/delivery')
    await nextTick()
    expect(wrapper.text()).toContain('blocked_external')
    expect(wrapper.text()).toContain('release_missing')

    await router.push('/competition/17/audit')
    await nextTick()
    expect(wrapper.text()).toContain('mechanism.claim_compile')
    expect(wrapper.text()).toContain('scenario=17 denominator=30')
  })
})
