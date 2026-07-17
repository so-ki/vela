import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CapabilityPackCard from './CapabilityPackCard.vue'
import type { CapabilityPackDisplay } from '@/types/scenario'

const pack: CapabilityPackDisplay = {
  pack_id: 'brazil_new_energy_greenfield',
  version: '1.0.0',
  pack_hash: 'pack-hash',
  status: 'active',
  content_status: 'provisional',
  display_name: '巴西 · 新能源制造 · 绿地设厂',
  description: '巴西新能源制造绿地投资法律协查。',
  country: 'BR',
  state: 'sao_paulo',
  industry: 'new_energy_manufacturing',
  action_type: 'greenfield_plant',
  languages: ['zh-CN', 'pt-BR'],
}

describe('CapabilityPackCard', () => {
  it('renders the controlled pilot and provisional legal-content boundary', () => {
    const wrapper = mount(CapabilityPackCard, { props: { pack } })

    expect(wrapper.text()).toContain('当前受控试点能力包')
    expect(wrapper.text()).toContain('巴西 · 新能源制造 · 绿地设厂')
    expect(wrapper.text()).toContain('版本 1.0.0')
    expect(wrapper.text()).toContain('工程可用')
    expect(wrapper.text()).toContain('法律内容为临时版本')
    expect(wrapper.text()).toContain('须由巴西执业律师或相关专家逐项复核')
    expect(wrapper.text()).not.toContain('完整法律协查支持')
    expect(wrapper.attributes('data-pack-id')).toBe('brazil_new_energy_greenfield')
  })

  it('renders frozen identity without presenting it as editable current catalog', () => {
    const wrapper = mount(CapabilityPackCard, {
      props: { pack: { ...pack, status: 'frozen' }, frozen: true },
    })

    expect(wrapper.text()).toContain('已冻结试点能力包')
    expect(wrapper.text()).toContain('工程配置已冻结')
  })

  it('fails closed when the authoritative pack is unavailable', () => {
    const wrapper = mount(CapabilityPackCard, { props: { pack: null } })

    expect(wrapper.text()).toContain('能力包加载失败')
    expect(wrapper.text()).toContain('已禁止确认与提交')
  })

  it('does not label an unverified proposal as operational', () => {
    const wrapper = mount(CapabilityPackCard, {
      props: { pack: { ...pack, status: 'unverified' } },
    })

    expect(wrapper.text()).toContain('待工程复核的能力包')
    expect(wrapper.text()).toContain('待工程复核')
    expect(wrapper.text()).not.toContain('工程可用')
  })
})
