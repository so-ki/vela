<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import BusinessMaterialReviewTable from '@/components/BusinessMaterialReviewTable.vue'
import AddFieldMenuPopover from '@/components/AddFieldMenuPopover.vue'
import PerFileExtractSection from '@/components/PerFileExtractSection.vue'
import type { CustomReviewField, ReviewFieldDef } from '@/config/businessMaterialReviewFields'
import type { DocumentExtractResult } from '@/api/client'
import type { ExtractFieldConflict, RulesCatalog } from '@/types/scenario'
import type { ScenarioFormData } from '@/types/scenario'

const open = defineModel<boolean>('open', { default: false })
const phase = defineModel<'editable' | 'confirm'>('phase', { default: 'editable' })
const form = defineModel<ScenarioFormData>({ required: true })
const hiddenFieldKeys = defineModel<string[]>('hiddenFieldKeys', { default: () => [] })
const customFields = defineModel<CustomReviewField[]>('customFields', { default: () => [] })
const rowOrder = defineModel<string[]>('rowOrder', { default: () => [] })

const informationEditing = ref(false)
const addFieldMenuOpen = ref(false)
const sectionHeaderError = ref('')
const reviewTableRef = ref<InstanceType<typeof BusinessMaterialReviewTable> | null>(null)
const addFieldMenuRef = ref<HTMLElement | null>(null)

withDefaults(
  defineProps<{
    editMode?: boolean
    submitting?: boolean
    extractModeLabel?: string
    filename?: string | null
    disclaimer?: string | null
    facts?: Array<{ field: string; value: string; source_snippet?: string | null; source_filename?: string | null }>
    perFileResults?: DocumentExtractResult[]
    hasMultiFileExtract?: boolean
    missingKeys?: string[]
    rejectedKeys?: string[]
    conflictKeys?: string[]
    conflicts?: ExtractFieldConflict[]
    fields?: ReviewFieldDef[]
    catalog?: RulesCatalog | null
    responsibilityHint?: string | null
    error?: string | null
  }>(),
  {
    editMode: false,
    submitting: false,
    extractModeLabel: '手动填写',
    filename: null,
    disclaimer: null,
    facts: () => [],
    perFileResults: () => [],
    hasMultiFileExtract: false,
    missingKeys: () => [],
    rejectedKeys: () => [],
    conflictKeys: () => [],
    conflicts: () => [],
    catalog: null,
    responsibilityHint: null,
    error: null,
  },
)

const emit = defineEmits<{
  close: []
  preview: []
  'back-to-edit': []
  submit: []
}>()

function handleBackdropClick() {
  if (phase.value === 'editable' && !informationEditing.value) {
    emit('close')
  }
}

function toggleInformationEditing() {
  informationEditing.value = !informationEditing.value
  addFieldMenuOpen.value = false
}

function handleClose() {
  informationEditing.value = false
  addFieldMenuOpen.value = false
  emit('close')
}

function toggleAddFieldMenu() {
  addFieldMenuOpen.value = !addFieldMenuOpen.value
  if (addFieldMenuOpen.value) {
    sectionHeaderError.value = ''
  }
}

function addStandaloneField() {
  const result = reviewTableRef.value?.addCustomField('standalone')
  if (result?.ok) {
    addFieldMenuOpen.value = false
  }
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

watch(open, (isOpen) => {
  if (!isOpen) {
    informationEditing.value = false
    addFieldMenuOpen.value = false
    return
  }
  nextTick(() => {
    document.querySelector('.business-review-modal-body')?.scrollTo({ top: 0, behavior: 'instant' })
  })
})

watch(phase, (next) => {
  if (next === 'confirm') {
    informationEditing.value = false
    addFieldMenuOpen.value = false
  }
})

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="modal-overlay business-review-overlay"
      @click.self="handleBackdropClick"
    >
      <div
        class="modal-card business-review-modal"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="phase === 'editable' ? 'review-modal-title-edit' : 'review-modal-title-confirm'"
      >
        <header class="business-review-modal-head">
          <div>
            <h2 :id="phase === 'editable' ? 'review-modal-title-edit' : 'review-modal-title-confirm'">
              {{
                phase === 'confirm'
                  ? '确认提交内容'
                  : informationEditing
                    ? '修改材料信息'
                    : '核对抽取信息'
              }}
            </h2>
            <p class="muted">
              <span class="badge ok">{{ extractModeLabel }}</span>
              <template v-if="phase === 'confirm'">
                以下为即将提交的内容，请再次确认；如需修改请点击「返回修改」。
              </template>
              <template v-else-if="informationEditing">
                可改字、删除、拖动排序；「新建字段」可添加标题行或内容分组。
              </template>
              <template v-else>
                仅展示方案中抽取到的信息；发现错误请点击「信息修改」。
              </template>
            </p>
          </div>
          <button
            v-if="phase === 'editable' && !informationEditing"
            type="button"
            class="modal-close-btn"
            aria-label="关闭"
            @click="handleClose"
          >
            ×
          </button>
        </header>

        <div class="business-review-modal-body">
          <section v-if="hasMultiFileExtract && phase === 'editable'" class="per-file-review-block">
            <h3>各文件抽取结果</h3>
            <p class="muted">以下为每个方案文件的独立抽取结果（只读）；请在下方「合并核对表」中编辑最终提交内容。</p>
            <PerFileExtractSection
              v-for="(fileResult, idx) in perFileResults"
              :key="`${fileResult.filename}-${idx}`"
              :index="idx"
              :result="fileResult"
            />
          </section>

          <section :class="{ 'merged-review-block': hasMultiFileExtract && phase === 'editable' }">
            <div v-if="hasMultiFileExtract && phase === 'editable'" class="extract-table-head">
              <h3>合并核对表</h3>
            </div>
            <BusinessMaterialReviewTable
              ref="reviewTableRef"
              v-model="form"
              v-model:hidden-field-keys="hiddenFieldKeys"
              v-model:custom-fields="customFields"
              v-model:row-order="rowOrder"
              :editable="phase === 'editable' && informationEditing"
              :structural-editing="phase === 'editable' && informationEditing"
              :dynamic-visibility="true"
              :mode-label="extractModeLabel"
              :filename="filename"
              :disclaimer="disclaimer"
              :facts="facts"
              :fields="fields"
              :catalog="catalog"
              :missing-keys="phase === 'editable' ? missingKeys : []"
              :rejected-keys="rejectedKeys"
              :conflict-keys="conflictKeys"
              :conflicts="conflicts"
              :responsibility-hint="responsibilityHint"
            />
          </section>
        </div>

        <p v-if="error" class="error modal-error">{{ error }}</p>

        <div class="modal-actions business-review-modal-actions">
          <template v-if="phase === 'editable'">
            <template v-if="informationEditing">
              <div class="modal-edit-actions">
                <div ref="addFieldMenuRef" class="add-field-control">
                  <button type="button" class="btn-secondary" @click.stop="toggleAddFieldMenu">
                    + 新建字段
                  </button>
                  <AddFieldMenuPopover
                    v-if="addFieldMenuOpen"
                    :error="sectionHeaderError"
                    class="add-field-popover--above"
                    @standalone="addStandaloneField"
                    @section="addSectionHeaderField"
                  />
                </div>
                <button type="button" class="btn-primary" @click="toggleInformationEditing">完成修改</button>
              </div>
            </template>
            <template v-else>
              <button type="button" class="btn-secondary" @click="toggleInformationEditing">信息修改</button>
              <button type="button" class="btn-secondary" @click="handleClose">关闭</button>
              <button type="button" class="btn-primary" @click="emit('preview')">下一步：确认提交</button>
            </template>
          </template>
          <template v-else>
            <button type="button" class="btn-secondary" @click="emit('back-to-edit')">返回修改</button>
            <button type="button" class="btn-primary" :disabled="submitting" @click="emit('submit')">
              {{ submitting ? '提交中…' : editMode ? '提交' : '提交' }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>
