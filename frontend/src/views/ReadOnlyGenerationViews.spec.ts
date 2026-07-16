import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BriefView from './BriefView.vue'
import ChecklistView from './ChecklistView.vue'
import ColdStartView from './ColdStartView.vue'
import DashboardView from './DashboardView.vue'
import { makeScenario } from '@/test/factories'

const client = vi.hoisted(() => ({
  fetchScenario: vi.fn(), fetchBrief: vi.fn(), fetchLlmStatus: vi.fn(), submitScenarioForReview: vi.fn(),
  fetchSystemStatus: vi.fn(), fetchScenarios: vi.fn(), fetchOnboardingStatus: vi.fn(),
  fetchLegalStatus: vi.fn(), fetchLegalMonitor: vi.fn(), fetchCorpusAgentStatus: vi.fn(),
  fetchRulesCatalog: vi.fn(), fetchPlaybookDeviations: vi.fn(), archiveScenario: vi.fn(),
  deleteScenario: vi.fn(), restoreDeletedScenario: vi.fn(), scanLegalMonitor: vi.fn(),
  runCorpusMaintenanceAgent: vi.fn(), ackCorpusAgentNotification: vi.fn(), unarchiveScenario: vi.fn(),
  fetchInterviewScript: vi.fn(), startInterview: vi.fn(), submitInterviewAnswer: vi.fn(),
  uploadInterviewAttachment: vi.fn(), completeInterview: vi.fn(),
}))

const auth = vi.hoisted(() => ({ isLegal: true, isBusiness: false }))
const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))

vi.mock('@/api/client', () => client)
vi.mock('vue-router', async () => {
  const vue = await import('vue')
  return {
    RouterLink: vue.defineComponent({ template: '<a><slot /></a>' }),
    useRoute: () => ({ params: { id: '7' }, hash: '', query: {} }),
    useRouter: () => navigation,
  }
})
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => auth,
}))
vi.mock('@/components/LlmSettingsPanel.vue', () => ({ default: { template: '<div />' } }))

const generatedScenario = makeScenario({
  status: 'pending_legal_review',
  overrides: { id: 7 },
})

describe('read-only generated views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    auth.isLegal = true
    auth.isBusiness = false
    client.fetchScenario.mockResolvedValue(generatedScenario)
    client.fetchLlmStatus.mockResolvedValue(null)
    client.fetchSystemStatus.mockResolvedValue({})
    client.fetchScenarios.mockResolvedValue([])
    client.fetchOnboardingStatus.mockResolvedValue({ completed: true, required: true, role: 'legal' })
    client.fetchLegalStatus.mockResolvedValue(null)
    client.fetchLegalMonitor.mockResolvedValue(null)
    client.fetchCorpusAgentStatus.mockResolvedValue(null)
    client.fetchRulesCatalog.mockResolvedValue(null)
    client.fetchPlaybookDeviations.mockResolvedValue(null)
  })

  it('ChecklistView mount only reads persisted scenario data', async () => {
    const wrapper = mount(ChecklistView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(client.fetchScenario).toHaveBeenCalledOnce()
    expect(Object.keys(client).some((name) => name.toLowerCase().includes('retrieve'))).toBe(false)
    expect(wrapper.text()).toContain('已冻结能力包')
    expect(wrapper.text()).toContain('巴西 · 新能源制造 · 绿地设厂')
    expect(wrapper.text()).toContain('版本 1.0.0')
  })

  it('BriefView GET failure never falls back to POST generation', async () => {
    client.fetchBrief.mockRejectedValue(new Error('missing'))
    const wrapper = mount(BriefView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(client.fetchBrief).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('不会隐式触发生成')
    expect(Object.keys(client).includes('generateBrief')).toBe(false)
  })

  it('Dashboard mount never calls the removed demo/sample wrapper', async () => {
    mount(DashboardView, { global: { stubs: { RouterLink: true, LlmSettingsPanel: true } } })
    await flushPromises()
    expect(client.fetchScenarios).toHaveBeenCalledOnce()
    expect(Object.keys(client).includes('createFullSample')).toBe(false)
  })

  it('business dashboard does not query or enter Legal Playbook onboarding', async () => {
    auth.isLegal = false
    auth.isBusiness = true
    mount(DashboardView, { global: { stubs: { RouterLink: true, LlmSettingsPanel: true } } })
    await flushPromises()
    expect(client.fetchOnboardingStatus).not.toHaveBeenCalled()
    expect(navigation.replace).not.toHaveBeenCalled()
  })

  it('Legal Playbook status failure stays fail-closed and can be retried', async () => {
    client.fetchOnboardingStatus.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount(DashboardView, {
      global: { stubs: { RouterLink: true, LlmSettingsPanel: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('无法确认 Legal Playbook 配置状态')
    expect(navigation.replace).not.toHaveBeenCalled()

    client.fetchOnboardingStatus.mockResolvedValueOnce({ completed: true, required: true, role: 'legal' })
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(client.fetchOnboardingStatus).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('无法确认 Legal Playbook 配置状态')
  })

  it('a dashboard bootstrap failure leaves a retryable error instead of a permanent loading state', async () => {
    client.fetchSystemStatus.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount(DashboardView, {
      global: { stubs: { RouterLink: true, LlmSettingsPanel: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('工作台数据加载失败')
    expect(wrapper.text()).not.toBe('加载中…')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(client.fetchSystemStatus).toHaveBeenCalledTimes(2)
    expect(client.fetchScenarios).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('工作台数据加载失败')
  })

  it('business users cannot start the Legal Playbook interview component', async () => {
    auth.isLegal = false
    auth.isBusiness = true
    mount(ColdStartView)
    await flushPromises()

    expect(navigation.replace).toHaveBeenCalledWith({ name: 'dashboard' })
    expect(client.fetchOnboardingStatus).not.toHaveBeenCalled()
    expect(client.fetchInterviewScript).not.toHaveBeenCalled()
    expect(client.startInterview).not.toHaveBeenCalled()
  })
})
