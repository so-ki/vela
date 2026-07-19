import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MechanismView from './MechanismView.vue'
import { makeScenario } from '@/test/factories'
import type { ClaimCompilation, CoverageProof, FactRecord } from '@/types/mechanism'
import type { Scenario } from '@/types/scenario'

const client = vi.hoisted(() => ({
  compileMechanismClaims: vi.fn(),
  confirmFactRecord: vi.fn(),
  confirmMechanismClaim: vi.fn(),
  createCoverageProof: vi.fn(),
  createFactRecord: vi.fn(),
  fetchFactRecords: vi.fn(),
  fetchDeliveryGateStatus: vi.fn(),
  fetchLatestClaimCompilation: vi.fn(),
  fetchLatestCoverageProof: vi.fn(),
  fetchMaterialLedger: vi.fn(),
  fetchMechanismCoverageTasks: vi.fn(),
  fetchScenario: vi.fn(),
}))

const auth = vi.hoisted(() => ({ isBusiness: true, isLegal: false }))

vi.mock('@/api/client', () => client)
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('vue-router', async () => {
  const vue = await import('vue')
  return {
    RouterLink: vue.defineComponent({ template: '<a><slot /></a>' }),
    useRoute: () => ({ params: { id: '9' } }),
  }
})

const fact: FactRecord = {
  id: 'fact-1',
  scenario_id: 9,
  subject: '项目公司',
  attribute: '用地面积',
  value: '20 公顷',
  fact_time: '2026-07-18',
  block_id: 'site-area',
  fact_pack_version: '1.3.1',
  source_document: '项目说明.pdf',
  assertion_polarity: 'unspecified',
  status: 'submitted',
  confirmation_note: null,
  business_confirmed_by: null,
  business_confirmed_at: null,
  created_by: 1,
  created_at: '2026-07-18T00:00:00Z',
}

const scenario: Scenario = makeScenario({
  status: 'review_in_progress',
  overrides: {
    checklist: {
      id: 4,
      title: '专项核查清单',
      version: '1.0',
      total_items: 1,
      jurisdiction: 'BR',
      detected_industry: 'new_energy_manufacturing',
      detected_industry_name: '新能源制造',
      detected_action_type: 'greenfield_plant',
      detected_action_type_name: '绿地设厂',
      selected_dimensions: ['environment'],
      sections: [
        {
          dimension_id: 'environment',
          dimension_name: '环境许可',
          dimension_name_pt: 'Licenciamento ambiental',
          description: '环境许可维度',
          items: [
            {
              code: 'ENV-01',
              title: '核对许可阶段',
              description: '核对许可阶段',
              priority: 'high',
              relevance_score: 100,
              rationale: '测试',
              matched_triggers: [],
              status: 'matched',
              legal_hits: [
                {
                  id: 'law-1',
                  source: 'official',
                  source_label: '官方法源',
                  urn: 'urn:test:law-1',
                  url: 'https://official.example/law-1',
                  title_pt: 'Regra de teste',
                  title_zh: '测试规则',
                  excerpt_pt: 'Trecho',
                  excerpt_zh: '摘录',
                  validity: 'active',
                  level: 'federal',
                  published_at: '2026-01-01',
                  match_score: 95,
                  vector_similarity: 0,
                  keyword_overlap: 1,
                  requires_review: true,
                  review_status: 'provisional',
                  citation_status: 'excerpt_matched',
                  grounding_score: 1,
                  grounded: true,
                },
              ],
            },
          ],
        },
      ],
      disclaimer: '仅供协查参考',
      created_at: '2026-07-18T00:00:00Z',
    },
  },
})

function compilationWith(status: 'awaiting_human_confirmation' | 'supported'): ClaimCompilation {
  return {
    id: 'comp-1',
    scenario_id: 9,
    compiler_version: '0.1',
    input_hash: 'i'.repeat(64),
    output_hash: 'o'.repeat(64),
    denominator_count: 1,
    ready_count: status === 'awaiting_human_confirmation' ? 1 : 0,
    refused_count: 0,
    input_snapshot: {},
    created_by: 2,
    created_at: '2026-07-18T00:00:00Z',
    research_items: [],
    claims: [
      {
        id: 'claim-1',
        compilation_id: 'comp-1',
        scenario_id: 9,
        checklist_code: 'ENV-01',
        statement: '项目需核对环境许可阶段。',
        status,
        fact_refs: ['fact-1'],
        evidence_refs: ['ENV-01:law-1'],
        reason_codes: [],
        confirmed_by: status === 'supported' ? 2 : null,
        confirmed_at: status === 'supported' ? '2026-07-18T01:00:00Z' : null,
        confirmation_note: status === 'supported' ? '已核对事实与引证' : null,
        created_at: '2026-07-18T00:00:00Z',
        updated_at: '2026-07-18T00:00:00Z',
      },
    ],
  }
}

const fullProof: CoverageProof = {
  id: 'proof-1',
  scenario_id: 9,
  compilation_id: 'comp-1',
  denominator_ref: 'scenario-checklist',
  denominator_hash: 'd'.repeat(64),
  denominator_count: 1,
  covered_count: 1,
  uncovered_count: 0,
  unanswerable_count: 0,
  proof: { covered_checklist_codes: ['ENV-01'] },
  proof_hash: 'p'.repeat(64),
  created_by: 2,
  created_at: '2026-07-18T02:00:00Z',
}

describe('MechanismView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    auth.isBusiness = true
    auth.isLegal = false
    client.fetchScenario.mockResolvedValue(scenario)
    client.fetchMaterialLedger.mockResolvedValue([])
    client.fetchMechanismCoverageTasks.mockResolvedValue([])
    client.fetchFactRecords.mockResolvedValue([fact])
    client.fetchLatestClaimCompilation.mockResolvedValue(null)
    client.fetchLatestCoverageProof.mockResolvedValue(null)
    client.fetchDeliveryGateStatus.mockResolvedValue({
      schema_version: '1.1',
      scenario_id: 9,
      evaluated_at: '2026-07-18T00:00:00Z',
      delivery_allowed: false,
      blocking_reasons: ['active_delivery_release_missing'],
      snapshot_hash: null,
      release_id: null,
      release_hash: null,
      expert_attestation_id: null,
      uat_acceptance_id: null,
      deployment_evidence_id: null,
      boundary: '外部证据尚未进入系统',
    })
  })

  it('lets business register and confirm only its facts while explaining the legal boundary', async () => {
    const created = { ...fact, id: 'fact-2' }
    const confirmed = {
      ...fact,
      status: 'business_confirmed' as const,
      confirmation_note: '已与项目材料核对',
      business_confirmed_by: 1,
      business_confirmed_at: '2026-07-18T03:00:00Z',
    }
    client.createFactRecord.mockResolvedValue(created)
    client.confirmFactRecord.mockResolvedValue(confirmed)

    const wrapper = mount(MechanismView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('不是正式法律意见')
    expect(wrapper.text()).toContain('未获客户交付许可')
    expect(wrapper.text()).not.toContain('Claim Compiler')

    await wrapper.get('[data-testid="fact-subject"]').setValue('项目公司')
    await wrapper.get('[data-testid="fact-attribute"]').setValue('装机规模')
    await wrapper.get('[data-testid="fact-value"]').setValue('100 MW')
    await wrapper.get('[data-testid="fact-time"]').setValue('截至提交日')
    await wrapper.get('[data-testid="fact-block"]').setValue('capacity')
    await wrapper.get('[data-testid="create-fact"]').trigger('submit')
    await flushPromises()

    expect(client.createFactRecord).toHaveBeenCalledWith(
      9,
      expect.objectContaining({
        subject: '项目公司',
        attribute: '装机规模',
        fact_pack_version: '1.3.1',
      }),
    )

    await wrapper.get('[data-testid="fact-note-fact-1"]').setValue('已与项目材料核对')
    await wrapper.get('[data-testid="confirm-fact-fact-1"]').trigger('click')
    await flushPromises()
    expect(client.confirmFactRecord).toHaveBeenCalledWith(9, 'fact-1', '已与项目材料核对')
  })

  it('keeps provisional evidence distinct from supported claims and requires legal decisions', async () => {
    auth.isBusiness = false
    auth.isLegal = true
    client.fetchLatestClaimCompilation.mockResolvedValue(compilationWith('awaiting_human_confirmation'))
    client.fetchLatestCoverageProof.mockResolvedValue(null)
    client.compileMechanismClaims.mockResolvedValue(compilationWith('awaiting_human_confirmation'))
    client.confirmMechanismClaim.mockResolvedValue(compilationWith('supported').claims[0])
    client.createCoverageProof.mockResolvedValue(fullProof)

    const wrapper = mount(MechanismView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    const configure = wrapper.findAll('button').find((button) => button.text().includes('配置 Claim'))
    expect(configure).toBeDefined()
    await configure!.trigger('click')
    expect(wrapper.text()).toContain('临时法源')
    expect(wrapper.text()).toContain('待法务人工确认')
    expect(wrapper.text()).toContain('客户交付发布链')

    await wrapper.get('[data-testid="compile-claims"]').trigger('click')
    await flushPromises()
    expect(client.compileMechanismClaims).toHaveBeenCalledWith(9, [])

    await wrapper.get('[data-testid="claim-note-claim-1"]').setValue('已核对事实与法条定位')
    await wrapper.get('[data-testid="support-claim-claim-1"]').trigger('click')
    await flushPromises()
    expect(client.confirmMechanismClaim).toHaveBeenCalledWith(
      9,
      'claim-1',
      'confirmed',
      '已核对事实与法条定位',
    )

    await wrapper.get('[data-testid="generate-proof"]').trigger('click')
    await flushPromises()
    expect(client.createCoverageProof).toHaveBeenCalledWith(9, 'comp-1')
    expect(wrapper.text()).toContain('机制层不存在待决 Claim')
    expect(wrapper.text()).toContain('未获客户交付许可')
  })
})
