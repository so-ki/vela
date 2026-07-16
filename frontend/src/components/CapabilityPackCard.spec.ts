import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CapabilityPackCard from './CapabilityPackCard.vue'

const pack = {
  pack_id: 'brazil_new_energy_greenfield',
  version: '1.0.0',
  pack_hash: 'pack-hash',
  status: 'active',
  display_name: '巴西 · 新能源制造 · 绿地设厂',
  description: '巴西新能源制造绿地投资法律协查。',
  country: 'BR',
  industry: 'new_energy_manufacturing',
  action_type: 'greenfield_plant',
  languages: ['zh-CN', 'pt-BR'],
}

describe('CapabilityPackCard', () => {
  it('renders the formal capability pack and MVP boundary', () => {
    const wrapper = mount(CapabilityPackCard, { props: { pack } })

    expect(wrapper.text()).toContain('当前已验证能力包')
    expect(wrapper.text()).toContain('巴西 · 新能源制造 · 绿地设厂')
    expect(wrapper.text()).toContain('版本 1.0.0')
    expect(wrapper.text()).toContain('正式支持')
    expect(wrapper.text()).toContain('当前 MVP 仅对该能力包提供完整法律协查支持')
    expect(wrapper.attributes('data-pack-id')).toBe('brazil_new_energy_greenfield')
  })

  it('renders frozen identity without presenting it as editable current catalog', () => {
    const wrapper = mount(CapabilityPackCard, {
      props: { pack: { ...pack, status: 'frozen' }, frozen: true },
    })

    expect(wrapper.text()).toContain('已冻结能力包')
    expect(wrapper.text()).toContain('已冻结')
  })

  it('fails closed when the authoritative pack is unavailable', () => {
    const wrapper = mount(CapabilityPackCard, { props: { pack: null } })

    expect(wrapper.text()).toContain('能力包加载失败')
    expect(wrapper.text()).toContain('已禁止确认与提交')
  })

  it('does not label an unverified proposal as formally supported', () => {
    const wrapper = mount(CapabilityPackCard, {
      props: { pack: { ...pack, status: 'unverified' } },
    })

    expect(wrapper.text()).toContain('待重新验证的能力包')
    expect(wrapper.text()).toContain('待重新验证')
    expect(wrapper.text()).not.toContain('正式支持')
  })
})
