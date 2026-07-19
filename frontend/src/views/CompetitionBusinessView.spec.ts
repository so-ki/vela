import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CompetitionBusinessView from './CompetitionBusinessView.vue'

const api = vi.hoisted(() => ({
  confirmCompetitionBusinessFact: vi.fn(),
  fetchCompetitionBusinessCenter: vi.fn(),
  submitCompetitionBusinessSupplement: vi.fn(),
  uploadCompetitionBusinessMaterial: vi.fn(),
}))

vi.mock('@/api/client', () => api)

const center = {
  scenario_id: 1,
  project_name: 'Aurora 储能系统集成工厂',
  materials: [{
    id: 'material-1',
    filename: 'aurora_project_brief.txt',
    uploaded_at: '2026-07-19T10:00:00Z',
    status: '已处理',
  }],
  facts: [{ id: 'fact-1', label: '目标地区', value: '圣保罗州', status: '已确认' }],
  supplements: [
    {
      id: 'site-status',
      title: '最终场址或选址状态',
      why: '用于确认项目所在地及后续手续办理范围。',
      accepted_materials: ['选址说明'],
      status: '待补充',
    },
    {
      id: 'hazardous-inventory',
      title: '危险品最大库存',
      why: '用于判断仓储、消防及安全管理所需的项目条件。',
      accepted_materials: ['物料清单'],
      status: '待补充',
    },
    {
      id: 'equipment-activity',
      title: '主要生产设备及活动分类',
      why: '用于识别实际生产活动、设备规模和配套设施需求。',
      accepted_materials: ['设备清单'],
      status: '待补充',
    },
  ],
  progress: [
    { label: '已提交', state: 'completed' },
    { label: '法务处理中', state: 'completed' },
    { label: '待业务补充', state: 'current' },
    { label: '已补充，等待法务复核', state: 'upcoming' },
    { label: '已完成', state: 'upcoming' },
  ],
  current_status: '待业务补充',
}

async function mountedView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/competition/:id/business', component: CompetitionBusinessView }],
  })
  await router.push('/competition/1/business')
  await router.isReady()
  const wrapper = mount(CompetitionBusinessView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchCompetitionBusinessCenter.mockResolvedValue(center)
  api.confirmCompetitionBusinessFact.mockResolvedValue(center)
  api.submitCompetitionBusinessSupplement.mockResolvedValue({
    ...center,
    current_status: '已补充，等待法务复核',
  })
})

describe('competition business center', () => {
  it('shows only the four business-facing regions and approved actions', async () => {
    const wrapper = await mountedView()
    expect(wrapper.text()).toContain('Aurora 项目材料与补件中心')
    for (const label of ['项目材料', '事实确认', '待补充信息', '处理进度']) {
      expect(wrapper.text()).toContain(label)
    }
    for (const label of ['最终场址或选址状态', '危险品最大库存', '主要生产设备及活动分类']) {
      expect(wrapper.text()).toContain(label)
    }
    const buttons = wrapper.findAll('button').map((button) => button.text())
    expect(buttons).toEqual(['上传材料', '确认事实', '补充材料', '提交法务'])
  })

  it('does not expose legal workspace terms', async () => {
    const text = (await mountedView()).text()
    for (const forbidden of [
      'ResearchItem',
      'Claim',
      'CoverageProof',
      '法律研究',
      '交付中心',
      '审计记录',
      '固定 30 项',
      'reason_code',
      'MISSING_FACT',
      'UNANSWERABLE',
    ]) {
      expect(text).not.toContain(forbidden)
    }
  })

  it('submits the supplement and shows the business-facing review status', async () => {
    const wrapper = await mountedView()
    await wrapper.get('button.business-action--primary').trigger('click')
    await flushPromises()
    expect(api.submitCompetitionBusinessSupplement).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('已补充，等待法务复核')
  })
})
