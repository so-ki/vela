import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MaterialReviewView from './MaterialReviewView.vue'
import { useAuthStore } from '@/stores/auth'
import { useMaterialReviewDraftStore } from '@/stores/materialReviewDraft'
import { makeBusinessUser, makeCatalog, makeScenario } from '@/test/factories'
import type { DocumentExtractBatchResult } from '@/api/client'

const api = vi.hoisted(() => ({
  fetchRulesCatalog: vi.fn(),
  reviseAndResubmitScenario: vi.fn(),
  submitMaterialsScenario: vi.fn(),
  acceptDisclaimer: vi.fn(),
  fetchMe: vi.fn(),
  login: vi.fn(),
}))

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))

vi.mock('@/api/client', () => api)
vi.mock('vue-router', () => ({ useRouter: () => router }))

const MaterialReviewTableStub = defineComponent({
  template: '<div><slot name="before-facts" /></div>',
})

describe('Capability Pack submission boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    setActivePinia(createPinia())

    const auth = useAuthStore()
    auth.user = makeBusinessUser()

    const draft = useMaterialReviewDraftStore()
    draft.setDraft({
      form: {
        project_name: '测试项目',
        country: '', state: '', city: '', industry: '', action_type: '',
        investment_structure: '全资子公司',
        description: '这是用于验证正式能力包失败关闭行为的项目说明。',
        compliance_dimensions: [],
      },
      extractBatch: null,
      pendingFiles: [new File(['test'], 'project.txt', { type: 'text/plain' })],
    })
  })

  it('keeps acknowledgement and submission disabled when catalog validation fails', async () => {
    api.fetchRulesCatalog.mockRejectedValue(new Error('registry unavailable'))
    const wrapper = mount(MaterialReviewView, {
      global: {
        stubs: {
          BusinessMaterialReviewTable: MaterialReviewTableStub,
          AddFieldMenuPopover: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text() === '完成修改')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('能力包加载失败')
    const acknowledgement = wrapper.find('.scope-acknowledgement input')
    const submit = wrapper.find('.business-review-modal-actions button.btn-primary')
    expect(acknowledgement.attributes('disabled')).toBeDefined()
    expect(submit.attributes('disabled')).toBeDefined()
    await submit.trigger('click')
    expect(api.submitMaterialsScenario).not.toHaveBeenCalled()
  })

  it('preserves scan warnings and grounding metadata in the submitted extraction snapshot', async () => {
    const extractBatch: DocumentExtractBatchResult = {
      files: [
        {
          filename: 'project.pdf',
          mode: 'rules',
          compliance_dimensions: ['labor'],
          facts: [
            {
              field: 'project_name',
              value: '测试项目',
              verification_status: 'weak_grounding',
              grounding_score: 0.42,
            },
          ],
          disclaimer: '仅供核对',
          scan_or_empty: true,
          extraction_warning: '扫描件无法完整抽取',
        },
      ],
      merged: {
        filename: 'project.pdf',
        mode: 'rules',
        project_name: '测试项目',
        description: '这是用于验证扫描件警告完整提交的项目说明。',
        compliance_dimensions: ['labor'],
        facts: [
          {
            field: 'project_name',
            value: '测试项目',
            verification_status: 'weak_grounding',
            grounding_score: 0.42,
          },
        ],
        disclaimer: '仅供核对',
        scan_or_empty: true,
        extraction_warning: '扫描件无法完整抽取',
      },
      failed: [],
      conflicts: [],
    }
    const pendingFile = new File(['test'], 'project.pdf', { type: 'application/pdf' })
    const draft = useMaterialReviewDraftStore()
    draft.setDraft({
      form: {
        project_name: '测试项目',
        country: '', state: '', city: '', industry: '', action_type: '',
        investment_structure: '全资子公司',
        description: '这是用于验证扫描件警告完整提交的项目说明。',
        compliance_dimensions: [],
      },
      extractBatch,
      pendingFiles: [pendingFile],
    })
    api.fetchRulesCatalog.mockResolvedValue(makeCatalog())
    api.submitMaterialsScenario.mockResolvedValue(makeScenario({ status: 'pending_scope', frozen: false }))

    const wrapper = mount(MaterialReviewView, {
      global: {
        stubs: {
          BusinessMaterialReviewTable: MaterialReviewTableStub,
          AddFieldMenuPopover: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text() === '完成修改')!.trigger('click')
    await wrapper.get('.scope-acknowledgement input').setValue(true)
    await wrapper.get('.business-review-modal-actions button.btn-primary').trigger('click')
    await flushPromises()

    expect(api.submitMaterialsScenario).toHaveBeenCalledWith(
      expect.objectContaining({
        document_extract: expect.objectContaining({
          scan_or_empty: true,
          extraction_warning: '扫描件无法完整抽取',
          facts: [
            expect.objectContaining({
              verification_status: 'weak_grounding',
              grounding_score: 0.42,
            }),
          ],
          files: [
            expect.objectContaining({
              scan_or_empty: true,
              extraction_warning: '扫描件无法完整抽取',
            }),
          ],
        }),
      }),
      [pendingFile],
    )
  })
})
