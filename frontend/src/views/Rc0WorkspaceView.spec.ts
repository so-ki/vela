import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { rc0SyntheticCase, syntheticRecordGroups } from '@/demo/rc0SyntheticCase'
import Rc0WorkspaceView from './Rc0WorkspaceView.vue'

const buildRouter = () => createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/rc0/:section?', name: 'rc0-workspace', component: Rc0WorkspaceView }],
})

describe('RC0 synthetic workspace', () => {
  it('forces the four demo-only boundary fields onto every synthetic record', () => {
    expect(rc0SyntheticCase.simulated).toBe(true)
    expect(rc0SyntheticCase.evidence_origin).toBe('synthetic_demo')
    expect(rc0SyntheticCase.status).toBe('demo_only')
    expect(rc0SyntheticCase.formal_release_allowed).toBe(false)

    for (const record of syntheticRecordGroups.flat()) {
      expect(record).toMatchObject({
        simulated: true,
        evidence_origin: 'synthetic_demo',
        status: 'demo_only',
        formal_release_allowed: false,
      })
    }
  })

  it('renders all required navigation, boundary labels and non-happy-path states', async () => {
    const router = buildRouter()
    await router.push('/rc0/overview')
    await router.isReady()
    const wrapper = mount(Rc0WorkspaceView, { global: { plugins: [router] } })

    for (const label of ['项目总览', '材料与事实', '调查清单', '法律研究', 'Claim 与缺口', 'CoverageProof', '交付中心', '审计记录']) {
      expect(wrapper.text()).toContain(label)
    }
    expect(wrapper.text()).toContain('SYNTHETIC DEMO')
    expect(wrapper.text()).toContain('formal_release_allowed=false')
    for (const state of ['Loading', 'Empty', 'Error', 'Blocked', 'Read-only', 'Demo-only', 'Stale', 'Unknown version']) {
      expect(wrapper.text()).toContain(state)
    }
  })

  it('keeps legal research three-column and formal delivery externally blocked', async () => {
    const router = buildRouter()
    await router.push('/rc0/research')
    await router.isReady()
    const wrapper = mount(Rc0WorkspaceView, { global: { plugins: [router] } })
    expect(wrapper.text()).toContain('调查事项')
    expect(wrapper.text()).toContain('规则、要件与事实映射')
    expect(wrapper.text()).toContain('权威法源与证据')

    await router.push('/rc0/delivery')
    await nextTick()
    expect(wrapper.text()).toContain('Expert Attestation')
    expect(wrapper.text()).toContain('Deployment Evidence')
    expect(wrapper.text()).toContain('blocked_external')
    expect(wrapper.text()).toContain('formal release blocked')
  })

  it('uses native focusable controls and announces the selected research item', async () => {
    const router = buildRouter()
    await router.push('/rc0/research')
    await router.isReady()
    const wrapper = mount(Rc0WorkspaceView, { global: { plugins: [router] } })
    const researchButtons = wrapper.findAll('.rc0-research-items button')
    const sectionLinks = wrapper.findAll('.rc0-section-nav a')

    expect(researchButtons).toHaveLength(3)
    expect(sectionLinks).toHaveLength(8)
    expect(researchButtons.every((button) => button.attributes('type') === 'button')).toBe(true)
    expect(researchButtons[0].attributes('aria-pressed')).toBe('true')

    await researchButtons[1].trigger('click')
    expect(researchButtons[0].attributes('aria-pressed')).toBe('false')
    expect(researchButtons[1].attributes('aria-pressed')).toBe('true')
    expect(wrapper.text()).toContain('技术责任与活动登记')
  })

  it('exports an explicitly synthetic JSON artifact', async () => {
    const router = buildRouter()
    await router.push('/rc0/overview')
    await router.isReady()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const createObjectURL = vi.fn(() => 'blob:rc0-demo')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const wrapper = mount(Rc0WorkspaceView, { global: { plugins: [router] } })

    await wrapper.get('button').trigger('click')
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:rc0-demo')

    click.mockRestore()
    Reflect.deleteProperty(URL, 'createObjectURL')
    Reflect.deleteProperty(URL, 'revokeObjectURL')
  })
})
