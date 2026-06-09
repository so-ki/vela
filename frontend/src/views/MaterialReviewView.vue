<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, type Ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import BusinessMaterialReviewTable from '@/components/BusinessMaterialReviewTable.vue'
import AddFieldMenuPopover from '@/components/AddFieldMenuPopover.vue'
import { useMaterialReview } from '@/composables/useMaterialReview'
import { fetchRulesCatalog, reviseAndResubmitScenario, submitMaterialsScenario } from '@/api/client'
import { useMaterialReviewDraftStore } from '@/stores/materialReviewDraft'
import { useAuthStore } from '@/stores/auth'
import type { ScenarioFormData } from '@/types/scenario'

const router = useRouter()
const auth = useAuthStore()
const draft = useMaterialReviewDraftStore()
const {
  form,
  extractBatch,
  pendingFiles,
  hiddenFieldKeys,
  customFields,
  rowOrder,
  editScenarioId,
} = storeToRefs(draft)

const catalog = ref<Awaited<ReturnType<typeof fetchRulesCatalog>> | null>(null)
const loading = ref(true)
const submitting = ref(false)
const error = ref<string | null>(null)
const showFieldValidation = ref(false)
const phase = ref<'edit' | 'confirm'>('edit')

const addFieldMenuOpen = ref(false)
const sectionHeaderError = ref('')
const reviewTableRef = ref<InstanceType<typeof BusinessMaterialReviewTable> | null>(null)
const addFieldMenuRef = ref<HTMLElement | null>(null)

const editMode = computed(() => editScenarioId.value != null)

const formModel = form as Ref<ScenarioFormData>

const {
  activeReviewFields,
  extractResult,
  hasMultiFileExtract,
  extractConflicts,
  conflictFieldKeys,
  extractModeLabel,
  reviewFacts,
  reviewDisclaimer,
  reviewMissingKeys,
  businessResponsibilityHint,
  collectValidationIssues,
  buildPayload,
} = useMaterialReview({
  form: formModel,
  extractBatch,
  pendingFiles,
  hiddenReviewFieldKeys: hiddenFieldKeys,
  reviewCustomFields: customFields,
  reviewRowOrder: rowOrder,
  catalog,
  editMode,
})

function validateReview(): boolean {
  const issues = collectValidationIssues()
  if (issues.length) {
    error.value = `请补充以下信息：${issues.join('、')}`
    return false
  }
  error.value = null
  return true
}

function goToConfirm() {
  showFieldValidation.value = true
  if (!validateReview()) return
  showFieldValidation.value = false
  phase.value = 'confirm'
  nextTick(() => {
    document.querySelector('.material-review-confirm-body')?.scrollTo({ top: 0, behavior: 'instant' })
  })
}

function backToEdit() {
  phase.value = 'edit'
  error.value = null
}

function toggleAddFieldMenu() {
  addFieldMenuOpen.value = !addFieldMenuOpen.value
  if (addFieldMenuOpen.value) {
    sectionHeaderError.value = ''
  }
}

function addStandaloneField() {
  const result = reviewTableRef.value?.addCustomField('standalone')
  if (result?.ok) addFieldMenuOpen.value = false
}

function addSectionHeaderField() {
  sectionHeaderError.value = ''
  const result = reviewTableRef.value?.addCustomField('section')
  if (!result) {
    sectionHeaderError.value = '无法添加，请稍后重试'
    return
  }
  if (!result.ok) {
    sectionHeaderError.value = result.message
    return
  }
  addFieldMenuOpen.value = false
}

function onDocumentClick(event: MouseEvent) {
  if (!addFieldMenuOpen.value) return
  const target = event.target as Node | null
  if (addFieldMenuRef.value && target && !addFieldMenuRef.value.contains(target)) {
    addFieldMenuOpen.value = false
  }
}

function extractApiError(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const resp = (e as { response?: { data?: { detail?: string } } }).response
    if (typeof resp?.data?.detail === 'string') return resp.data.detail
  }
  return '操作失败，请稍后重试'
}

async function finalSubmit() {
  showFieldValidation.value = true
  if (!validateReview()) {
    phase.value = 'edit'
    return
  }
  showFieldValidation.value = false
  submitting.value = true
  error.value = null
  try {
    const payload = await buildPayload()
    const uploadFiles = pendingFiles.value.length ? pendingFiles.value : undefined
    if (editMode.value && editScenarioId.value) {
      const scenario = await reviseAndResubmitScenario(editScenarioId.value, payload, uploadFiles)
      draft.clear()
      await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
      return
    }
    const scenario = await submitMaterialsScenario(payload, uploadFiles)
    draft.clear()
    await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
  } catch (e: unknown) {
    error.value = extractApiError(e)
  } finally {
    submitting.value = false
  }
}

function backToUpload() {
  router.push({ name: 'scenario-create' })
}

onMounted(async () => {
  if (!auth.isBusiness) {
    await router.replace({ name: 'dashboard' })
    return
  }
  if (!draft.ready || !form.value) {
    await router.replace({ name: 'scenario-create' })
    return
  }
  try {
    catalog.value = await fetchRulesCatalog()
  } catch (e: unknown) {
    error.value = extractApiError(e)
  } finally {
    loading.value = false
  }
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div class="material-review-page">
    <header class="page-header material-review-page-head">
      <div>
        <p class="eyebrow dark">业务协查 · 材料核对</p>
        <h1>修改材料信息</h1>
        <p class="muted">
          <span class="badge ok">{{ extractModeLabel }}</span>
          可改字、删除、拖动排序；「新建字段」可添加标题行或内容分组。
        </p>
      </div>
      <button type="button" class="btn-secondary" @click="backToUpload">返回上传</button>
    </header>

    <p v-if="loading" class="muted">加载中…</p>

    <template v-else-if="phase === 'edit'">
      <div class="panel material-review-page-body">
        <section>
          <div v-if="hasMultiFileExtract" class="extract-table-head">
            <h3>合并核对表</h3>
          </div>
          <BusinessMaterialReviewTable
            ref="reviewTableRef"
            v-model="formModel"
            v-model:hidden-field-keys="hiddenFieldKeys"
            v-model:custom-fields="customFields"
            v-model:row-order="rowOrder"
            :editable="true"
            :structural-editing="true"
            :dynamic-visibility="true"
            :mode-label="extractModeLabel"
            :filename="extractResult?.filename ?? null"
            :disclaimer="reviewDisclaimer"
            :facts="reviewFacts"
            :fields="activeReviewFields"
            :catalog="catalog"
            :missing-keys="showFieldValidation ? reviewMissingKeys : []"
            :conflict-keys="conflictFieldKeys"
            :conflicts="extractConflicts"
            :responsibility-hint="businessResponsibilityHint"
          >
            <template #before-facts>
              <div ref="addFieldMenuRef" class="add-field-control">
                <button type="button" class="btn-secondary" @click.stop="toggleAddFieldMenu">+ 新建字段</button>
                <AddFieldMenuPopover
                  v-if="addFieldMenuOpen"
                  :error="sectionHeaderError"
                  class="add-field-popover--above"
                  @standalone="addStandaloneField"
                  @section="addSectionHeaderField"
                />
              </div>
              <button type="button" class="btn-primary" @click="goToConfirm">完成修改</button>
            </template>
          </BusinessMaterialReviewTable>
        </section>
      </div>

      <p v-if="error" class="error">{{ error }}</p>
    </template>

    <Teleport to="body">
      <div v-if="phase === 'confirm'" class="modal-overlay business-review-overlay">
        <div class="modal-card business-review-modal material-review-confirm-modal" role="dialog" aria-modal="true">
          <header class="business-review-modal-head">
            <div>
              <h2>确认提交内容</h2>
              <p class="muted">
                <span class="badge ok">{{ extractModeLabel }}</span>
                以下为即将提交的内容，请再次确认；如需修改请点击「返回修改」。
              </p>
            </div>
          </header>

          <div class="business-review-modal-body material-review-confirm-body">
            <BusinessMaterialReviewTable
              v-model="formModel"
              v-model:hidden-field-keys="hiddenFieldKeys"
              v-model:custom-fields="customFields"
              v-model:row-order="rowOrder"
              :editable="false"
              :structural-editing="false"
              :dynamic-visibility="true"
              :mode-label="extractModeLabel"
              :filename="extractResult?.filename ?? null"
              :disclaimer="reviewDisclaimer"
              :facts="reviewFacts"
              :fields="activeReviewFields"
              :catalog="catalog"
              :conflict-keys="conflictFieldKeys"
              :conflicts="extractConflicts"
              :responsibility-hint="businessResponsibilityHint"
            />
          </div>

          <p v-if="error" class="error modal-error">{{ error }}</p>

          <div class="modal-actions business-review-modal-actions">
            <button type="button" class="btn-secondary" @click="backToEdit">返回修改</button>
            <button type="button" class="btn-primary" :disabled="submitting" @click="finalSubmit">
              {{ submitting ? '提交中…' : '提交' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
