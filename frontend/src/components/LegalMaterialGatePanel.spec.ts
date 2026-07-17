import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LegalMaterialGatePanel from './LegalMaterialGatePanel.vue'
import { makeCatalog, makeScenario } from '@/test/factories'

const api = vi.hoisted(() => ({
  generateInvestigationPack: vi.fn(),
  retryInvestigationPack: vi.fn(),
  downloadScenarioMaterialFile: vi.fn(),
  fetchUserPreferences: vi.fn(),
  fetchScenario: vi.fn(),
}))

vi.mock('@/api/client', () => api)

const catalog = makeCatalog()

function scenario(status = 'scope_generation_failed', frozen = true) {
  return makeScenario({ status, frozen })
}

describe('LegalMaterialGatePanel frozen behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchUserPreferences.mockResolvedValue({ match_threshold: 95, retrieval_top_k: 10 })
    api.retryInvestigationPack.mockResolvedValue(scenario('pending_legal_review'))
  })

  it('locks every frozen field and ignores changed preferences', async () => {
    const wrapper = mount(LegalMaterialGatePanel, {
      props: { scenario: scenario(), catalog },
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()
    expect(api.fetchUserPreferences).not.toHaveBeenCalled()
    const ranges = wrapper.findAll('input[type="range"]')
    expect(ranges.map((item) => item.attributes('disabled'))).toEqual(['', ''])
    expect((ranges[0].element as HTMLInputElement).value).toBe('75')
    expect((ranges[1].element as HTMLInputElement).value).toBe('1')
    expect(wrapper.findAll('input[type="checkbox"]').every((item) => item.attributes('disabled') !== undefined)).toBe(true)
  })

  it('fails closed when catalog is unavailable', async () => {
    const wrapper = mount(LegalMaterialGatePanel, {
      props: { scenario: scenario('pending_scope', false), catalog: null },
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()
    expect(wrapper.find('button.btn-primary').attributes('disabled')).toBeDefined()
  })

  it('does not start a second generator while status is generating', async () => {
    const wrapper = mount(LegalMaterialGatePanel, {
      props: { scenario: scenario('scope_generating'), catalog },
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()
    const button = wrapper.find('button.btn-primary')
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    expect(api.retryInvestigationPack).not.toHaveBeenCalled()
    expect(api.generateInvestigationPack).not.toHaveBeenCalled()
  })

  it('rejects confirmation when catalog identity does not match the proposal', async () => {
    const mismatchedCatalog = makeCatalog({ pack_hash: 'different-pack-hash' })
    const wrapper = mount(LegalMaterialGatePanel, {
      props: { scenario: scenario('pending_scope', false), catalog: mismatchedCatalog },
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('能力包身份不一致')
    expect(wrapper.text()).toContain('待工程复核的能力包')
    expect(wrapper.text()).not.toContain('工程可用')
    expect(wrapper.find('input[type="checkbox"]').attributes('disabled')).toBeDefined()
    expect(api.generateInvestigationPack).not.toHaveBeenCalled()
  })

  it('reloads a snapshot frozen during a failed confirmation and retries only through the frozen endpoint', async () => {
    const failed = scenario('scope_generation_failed')
    api.generateInvestigationPack.mockRejectedValueOnce(new Error('generation failed'))
    api.fetchScenario.mockResolvedValueOnce(failed)

    const wrapper = mount(LegalMaterialGatePanel, {
      props: { scenario: scenario('pending_scope', false), catalog },
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()

    await wrapper.get('.scope-legal-confirmation input').setValue(true)
    const confirm = wrapper.findAll('button').find((button) => button.text() === '确认范围并生成')
    expect(confirm).toBeDefined()
    await confirm!.trigger('click')
    await flushPromises()

    expect(api.generateInvestigationPack).toHaveBeenCalledOnce()
    expect(api.fetchScenario).toHaveBeenCalledWith(9)
    const refreshed = wrapper.emitted('investigationGenerated')?.[0]?.[0]
    expect(refreshed).toEqual(failed)

    await wrapper.setProps({ scenario: failed })
    const retry = wrapper.findAll('button').find((button) => button.text() === '按冻结快照重试')
    expect(retry).toBeDefined()
    expect(retry!.attributes('disabled')).toBeUndefined()
    await retry!.trigger('click')
    await flushPromises()

    expect(api.retryInvestigationPack).toHaveBeenCalledWith(9)
    expect(api.generateInvestigationPack).toHaveBeenCalledTimes(1)
  })

  it('shows the frozen pack and retries by scenario id without current catalog', async () => {
    const wrapper = mount(LegalMaterialGatePanel, {
      props: { scenario: scenario('scope_generation_failed'), catalog: null },
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('已冻结试点能力包')
    expect(wrapper.text()).toContain('巴西 · 新能源制造 · 绿地设厂')
    expect(wrapper.text()).toContain('版本 1.3.0')
    const retry = wrapper.find('button.btn-primary')
    expect(retry.attributes('disabled')).toBeUndefined()
    await retry.trigger('click')
    await flushPromises()
    expect(api.retryInvestigationPack).toHaveBeenCalledWith(9)
    expect(api.generateInvestigationPack).not.toHaveBeenCalled()
  })
})
