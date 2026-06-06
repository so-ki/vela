import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { CustomReviewField } from '@/config/businessMaterialReviewFields'
import type { DocumentExtractBatchResult } from '@/api/client'
import type { ScenarioFormData } from '@/types/scenario'

export const useMaterialReviewDraftStore = defineStore('materialReviewDraft', () => {
  const ready = ref(false)
  const form = ref<ScenarioFormData | null>(null)
  const extractBatch = ref<DocumentExtractBatchResult | null>(null)
  const pendingFiles = ref<File[]>([])
  const hiddenFieldKeys = ref<string[]>([])
  const customFields = ref<CustomReviewField[]>([])
  const rowOrder = ref<string[]>([])
  const editScenarioId = ref<number | null>(null)

  function setDraft(payload: {
    form: ScenarioFormData
    extractBatch: DocumentExtractBatchResult | null
    pendingFiles: File[]
    hiddenFieldKeys?: string[]
    customFields?: CustomReviewField[]
    rowOrder?: string[]
    editScenarioId?: number | null
  }) {
    form.value = payload.form
    extractBatch.value = payload.extractBatch
    pendingFiles.value = [...payload.pendingFiles]
    hiddenFieldKeys.value = [...(payload.hiddenFieldKeys ?? [])]
    customFields.value = [...(payload.customFields ?? [])]
    rowOrder.value = [...(payload.rowOrder ?? [])]
    editScenarioId.value = payload.editScenarioId ?? null
    ready.value = true
  }

  function clear() {
    ready.value = false
    form.value = null
    extractBatch.value = null
    pendingFiles.value = []
    hiddenFieldKeys.value = []
    customFields.value = []
    rowOrder.value = []
    editScenarioId.value = null
  }

  return {
    ready,
    form,
    extractBatch,
    pendingFiles,
    hiddenFieldKeys,
    customFields,
    rowOrder,
    editScenarioId,
    setDraft,
    clear,
  }
})
