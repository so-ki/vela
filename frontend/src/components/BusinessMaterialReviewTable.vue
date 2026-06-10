<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import {
  allReviewFieldsFromCatalog,
  buildDefaultRowOrder,
  buildReviewDisplayItems,
  buildReviewFieldLabels,
  canDeleteReviewField,
  customRowOrderId,
  fieldsGroupedByUiGroup,
  filterSectionsByExtractedData,
  isStandaloneCustomField,
  isSectionCustomField,
  mergedCustomFieldsForTarget,
  moveRowOrder,
  normalizeFieldLabelForMatch,
  normalizeRowOrder,
  standardRowOrderId,
  type CustomReviewField,
  type CustomReviewFieldLayout,
  type ReviewDisplayItem,
  type ReviewFieldDef,
} from '@/config/businessMaterialReviewFields'
import type { ExtractFieldConflict, RulesCatalog } from '@/types/scenario'
import type { ScenarioFormData } from '@/types/scenario'
import ConflictHighlightTextarea from '@/components/ConflictHighlightTextarea.vue'
import AutoGrowTextarea from '@/components/AutoGrowTextarea.vue'

export type ReviewFact = {
  field: string
  value: string
  source_snippet?: string | null
  source_filename?: string | null
}

const props = withDefaults(
  defineProps<{
    editable?: boolean
    structuralEditing?: boolean
    dynamicVisibility?: boolean
    modeLabel?: string
    filename?: string | null
    extractedAt?: string | null
    disclaimer?: string | null
    facts?: ReviewFact[]
    catalog?: RulesCatalog | null
    missingKeys?: string[]
    rejectedKeys?: string[]
    conflictKeys?: string[]
    conflicts?: ExtractFieldConflict[]
    fields?: ReviewFieldDef[]
    responsibilityHint?: string | null
    hiddenFieldKeys?: string[]
    customFields?: CustomReviewField[]
    rowOrder?: string[]
  }>(),
  {
    editable: false,
    structuralEditing: false,
    dynamicVisibility: true,
    modeLabel: '手动填写',
    filename: null,
    extractedAt: null,
    disclaimer: null,
    facts: () => [],
    catalog: null,
    missingKeys: () => [],
    rejectedKeys: () => [],
    conflictKeys: () => [],
    conflicts: () => [],
    fields: undefined,
    responsibilityHint: null,
    hiddenFieldKeys: () => [],
    customFields: () => [],
    rowOrder: () => [],
  },
)

const emit = defineEmits<{
  'update:hiddenFieldKeys': [keys: string[]]
  'update:customFields': [fields: CustomReviewField[]]
  'update:rowOrder': [order: string[]]
}>()

const form = defineModel<ScenarioFormData>({ required: true })

const activeFields = computed(() => props.fields ?? allReviewFieldsFromCatalog(props.catalog))
const baseUiSections = computed(() => fieldsGroupedByUiGroup(activeFields.value, props.catalog))
const fieldLabels = computed(() => buildReviewFieldLabels(props.catalog))

const visibleUiSections = computed(() => {
  if (!props.dynamicVisibility) return baseUiSections.value
  return filterSectionsByExtractedData(baseUiSections.value, form.value, props.catalog, {
    hiddenFieldKeys: props.hiddenFieldKeys,
  })
})

const normalizedRowOrder = computed(() =>
  normalizeRowOrder(props.rowOrder, visibleUiSections.value, props.customFields, {
    hiddenFieldKeys: props.hiddenFieldKeys,
    includeEmptyCustom: props.structuralEditing,
  }),
)

const displayItems = computed(() =>
  buildReviewDisplayItems(normalizedRowOrder.value, visibleUiSections.value, props.customFields, props.catalog),
)

const tableColspan = computed(() => {
  let cols = 2
  if (props.structuralEditing) cols += 2
  return cols
})

const CUSTOM_FIELD_ROWS = 6
const factsExpanded = ref(false)
const draggingRowId = ref<string | null>(null)
const dragOverRowId = ref<string | null>(null)

watch(
  [visibleUiSections, () => props.customFields, () => props.hiddenFieldKeys, () => props.structuralEditing],
  () => {
    const normalized = normalizedRowOrder.value
    const defaultOrder = buildDefaultRowOrder(visibleUiSections.value, props.customFields)
    if (!props.rowOrder.length) {
      emit('update:rowOrder', defaultOrder)
      return
    }
    if (normalized.join('|') !== props.rowOrder.join('|')) {
      emit('update:rowOrder', normalized)
    }
  },
  { immediate: true },
)

function placeholderFor(_key: string, _field?: ReviewFieldDef): string {
  return ''
}

function scrollToSection(sectionId: string) {
  document.getElementById(`material-section-${sectionId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function isMissing(key: string) {
  return props.missingKeys.includes(key)
}

function isRejected(key: string) {
  return props.rejectedKeys.includes(key)
}

function isConflict(key: string) {
  return props.conflictKeys.includes(key)
}

function conflictFor(key: string) {
  return props.conflicts.find((item) => item.field === key)
}

function displayValue(_key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function factLabel(field: string) {
  return fieldLabels.value[field] || field
}

function rowClass(key: string) {
  return {
    'row-missing': isMissing(key) || isRejected(key),
    'row-conflict': isConflict(key) && !isMissing(key) && !isRejected(key),
  }
}

function rowOrderIdForItem(item: ReviewDisplayItem): string | null {
  if (item.type === 'standard') return standardRowOrderId(item.key)
  if (item.type === 'custom') return customRowOrderId(item.field.id)
  if (item.type === 'section' && item.customSectionId) {
    return customRowOrderId(item.customSectionId)
  }
  return null
}

function clearFormField(key: ReviewFieldDef['key']) {
  if (key === 'project_name') form.value.project_name = ''
  else if (key === 'investment_destination') form.value.investment_destination = ''
  else if (key === 'investment_structure') form.value.investment_structure = ''
  else if (key === 'funding_source') form.value.funding_source = ''
  else if (key === 'project_content_scale') form.value.project_content_scale = ''
  else if (key === 'description') form.value.description = ''
  else if (key === 'known_risks') form.value.known_risks = ''
  else if (key === 'board_date') form.value.board_date = ''
  else if (key === 'start_date') form.value.start_date = ''
  else if (key === 'production_date') form.value.production_date = ''
}

function removeStandardField(key: ReviewFieldDef['key']) {
  if (!canDeleteReviewField(key, props.catalog)) return
  clearFormField(key)
  const fieldDef = activeFields.value.find((f) => f.key === key)
  const mergedIds = mergedCustomFieldsForTarget(props.customFields, key, fieldDef?.label).map(
    (field) => field.id,
  )
  const nextCustomFields = props.customFields.filter((field) => !mergedIds.includes(field.id))
  if (nextCustomFields.length !== props.customFields.length) {
    emit('update:customFields', nextCustomFields)
  }
  const nextHidden = props.hiddenFieldKeys.includes(key)
    ? props.hiddenFieldKeys
    : [...props.hiddenFieldKeys, key]
  emit('update:hiddenFieldKeys', nextHidden)
  emit(
    'update:rowOrder',
    normalizedRowOrder.value.filter((rowId) => rowId !== standardRowOrderId(key)),
  )
}

function mergedFieldsFor(key: string, label?: string) {
  return mergedCustomFieldsForTarget(props.customFields, key, label).filter((field) => {
    if (props.structuralEditing) return true
    return field.label.trim() || field.value.trim()
  })
}

export type AddCustomFieldResult =
  | { ok: true; kind: 'standalone'; customId: string }
  | { ok: true; kind: 'section'; customId: string; sectionLabel: string }
  | { ok: true; kind: 'merged'; customId: string; targetKey: string; targetLabel: string }
  | { ok: false; message: string }

function resolveMergeTarget(input: string): { key: string; label: string } | null {
  const needle = normalizeFieldLabelForMatch(input)
  if (!needle) return null
  const visible = visibleUiSections.value.flatMap((section) => section.fields)
  for (const field of visible) {
    if (normalizeFieldLabelForMatch(field.label) === needle) {
      return { key: field.key, label: field.label }
    }
  }
  for (const field of visible) {
    const normalized = normalizeFieldLabelForMatch(field.label)
    if (normalized.includes(needle) || needle.includes(normalized)) {
      return { key: field.key, label: field.label }
    }
  }
  return null
}

function scrollToReviewRow(target: { kind: 'standard'; key: string } | { kind: 'custom'; id: string }) {
  nextTick(() => {
    nextTick(() => {
      const selector =
        target.kind === 'standard'
          ? `[data-review-row-key="${target.key}"]`
          : `[data-review-custom-id="${target.id}"]`
      document.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  })
}

function addCustomField(
  layout: CustomReviewFieldLayout = 'standalone',
  targetLabel?: string,
): AddCustomFieldResult {
  const id = `custom_${Date.now()}`

  if (layout === 'section') {
    const raw = (targetLabel || '').trim()
    const field: CustomReviewField = {
      id,
      label: raw,
      value: '',
      layout: 'section',
    }
    emit('update:customFields', [...props.customFields, field])
    emit('update:rowOrder', [...normalizedRowOrder.value, customRowOrderId(id)])
    nextTick(() => {
      document.getElementById(`material-section-custom-section-${id}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    })
    return { ok: true, kind: 'section', customId: id, sectionLabel: raw }
  }

  if (layout === 'merged') {
    const raw = (targetLabel || '').trim()
    if (!raw) return { ok: false, message: '请输入要合并到的字段名称' }
    const resolved = resolveMergeTarget(raw)
    if (!resolved) {
      return { ok: false, message: `未找到字段「${raw}」，请与左侧字段名一致` }
    }
    const field: CustomReviewField = {
      id,
      label: '',
      value: '',
      layout: 'merged',
      mergeTargetLabel: resolved.label,
      mergeTargetKey: resolved.key,
    }
    emit('update:customFields', [...props.customFields, field])
    scrollToReviewRow({ kind: 'standard', key: resolved.key })
    return { ok: true, kind: 'merged', customId: id, targetKey: resolved.key, targetLabel: resolved.label }
  }

  const field: CustomReviewField = {
    id,
    label: '',
    value: '',
    layout: 'standalone',
  }
  emit('update:customFields', [...props.customFields, field])
  emit('update:rowOrder', [...normalizedRowOrder.value, customRowOrderId(id)])
  scrollToReviewRow({ kind: 'custom', id })
  return { ok: true, kind: 'standalone', customId: id }
}

defineExpose({
  addCustomField,
})

function updateCustomField(id: string, patch: Partial<CustomReviewField>) {
  emit(
    'update:customFields',
    props.customFields.map((field) => (field.id === id ? { ...field, ...patch } : field)),
  )
}

function removeCustomField(id: string) {
  const target = props.customFields.find((field) => field.id === id)
  emit(
    'update:customFields',
    props.customFields.filter((field) => field.id !== id),
  )
  if (target && (isStandaloneCustomField(target) || isSectionCustomField(target))) {
    emit(
      'update:rowOrder',
      normalizedRowOrder.value.filter((rowId) => rowId !== customRowOrderId(id)),
    )
  }
}

function onDragStart(rowId: string, event: DragEvent) {
  if (!props.structuralEditing) return
  draggingRowId.value = rowId
  dragOverRowId.value = null
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', rowId)
  }
}

function onDragOver(rowId: string, event: DragEvent) {
  if (!props.structuralEditing || !draggingRowId.value || draggingRowId.value === rowId) return
  event.preventDefault()
  dragOverRowId.value = rowId
}

function onDrop(rowId: string, event: DragEvent) {
  if (!props.structuralEditing || !draggingRowId.value) return
  event.preventDefault()
  emit('update:rowOrder', moveRowOrder(normalizedRowOrder.value, draggingRowId.value, rowId))
  draggingRowId.value = null
  dragOverRowId.value = null
}

function onDragEnd() {
  draggingRowId.value = null
  dragOverRowId.value = null
}

const sectionNavItems = computed(() => {
  const seen = new Set<string>()
  return displayItems.value
    .filter((item): item is Extract<ReviewDisplayItem, { type: 'section' }> => item.type === 'section')
    .filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })
})
</script>

<template>
  <div class="material-review">
    <div v-if="responsibilityHint" class="responsibility-banner">
      <strong>业务确认责任</strong>
      <p>{{ responsibilityHint }}</p>
      <p class="muted">提交前必填：项目名称、投资结构、业务描述。</p>
    </div>

    <div v-if="conflicts.length" class="conflict-banner">
      <strong>多文件字段冲突（{{ conflicts.length }} 项）</strong>
      <p class="muted">
        以下字段在不同文件中抽取结果不一致。请在字段编辑框内直接修改——<strong>红色文字</strong>为冲突片段，编辑过程中红色标注会保留。
      </p>
      <ul class="conflict-banner-list">
        <li v-for="item in conflicts" :key="item.field" class="conflict-banner-item conflict-banner-item--compact">
          <span class="badge warn">冲突</span>
          <strong>{{ item.label }}</strong>
          <span class="muted">（{{ item.merge_note }}）</span>
        </li>
      </ul>
    </div>

    <div v-if="disclaimer" class="disclaimer-banner">{{ disclaimer }}</div>

    <nav v-if="sectionNavItems.length > 1" class="material-section-nav" aria-label="核对表分组">
      <button
        v-for="section in sectionNavItems"
        :key="section.id"
        type="button"
        class="material-section-nav-btn"
        @click="scrollToSection(section.id)"
      >
        {{ section.label }}
      </button>
    </nav>

    <section
      v-if="displayItems.length || structuralEditing"
      class="panel extract-table-panel material-ui-review-section"
    >
      <div class="extract-table-head">
        <h2>协查材料核对</h2>
        <p class="muted extract-table-meta">
          <span class="badge ok">{{ modeLabel }}</span>
          <span v-if="filename">来源文件：{{ filename }}</span>
          <span v-if="extractedAt">· 抽取于 {{ new Date(extractedAt).toLocaleString('zh-CN') }}</span>
        </p>
      </div>

      <p v-if="structuralEditing" class="muted section-hint">
        拖动手柄可调整顺序；「新建字段」可添加标题行或内容分组。
      </p>

      <table class="extract-fields-table material-review-table">
        <tbody>
          <template v-for="item in displayItems" :key="`${item.type}-${item.type === 'section' ? item.id : item.type === 'standard' ? item.key : item.field.id}`">
            <tr
              v-if="item.type === 'section'"
              :id="item.customSectionId ? `material-section-custom-section-${item.customSectionId}` : `material-section-${item.id}`"
              class="material-section-divider-row"
              :class="{ 'material-section-divider-row--custom': Boolean(item.customSectionId) }"
              :draggable="structuralEditing && Boolean(item.customSectionId)"
              @dragstart="item.customSectionId && onDragStart(rowOrderIdForItem(item)!, $event)"
              @dragover="item.customSectionId && onDragOver(rowOrderIdForItem(item)!, $event)"
              @drop="item.customSectionId && onDrop(rowOrderIdForItem(item)!, $event)"
              @dragend="onDragEnd"
            >
              <td :colspan="tableColspan">
                <div class="material-section-divider-head">
                  <button
                    v-if="structuralEditing && item.customSectionId"
                    type="button"
                    class="row-drag-handle material-section-drag-handle"
                    aria-label="拖动排序"
                    @mousedown.stop
                  >
                    ⋮⋮
                  </button>
                  <template v-if="structuralEditing && item.customSectionId">
                    <input
                      :value="item.label"
                      class="cell-input material-section-title-input"
                      placeholder="内容标题"
                      @input="updateCustomField(item.customSectionId, { label: ($event.target as HTMLInputElement).value })"
                    />
                    <button
                      type="button"
                      class="btn-text btn-danger-text"
                      @click="removeCustomField(item.customSectionId)"
                    >
                      删除
                    </button>
                  </template>
                  <h3 v-else class="material-ui-review-heading material-ui-review-heading--inline">
                    {{ item.label.trim() || '—' }}
                  </h3>
                </div>
              </td>
            </tr>

            <tr
              v-else
              :class="[
                item.type === 'standard' ? rowClass(item.key) : 'row-custom',
                {
                  'row-dragging': draggingRowId === rowOrderIdForItem(item),
                  'row-drag-over': dragOverRowId === rowOrderIdForItem(item),
                },
              ]"
              :data-review-row-key="item.type === 'standard' ? item.key : undefined"
              :data-review-custom-id="item.type === 'custom' ? item.field.id : undefined"
              :draggable="structuralEditing && Boolean(rowOrderIdForItem(item))"
              @dragstart="onDragStart(rowOrderIdForItem(item)!, $event)"
              @dragover="onDragOver(rowOrderIdForItem(item)!, $event)"
              @drop="onDrop(rowOrderIdForItem(item)!, $event)"
              @dragend="onDragEnd"
            >
              <td v-if="structuralEditing" class="col-drag">
                <button
                  type="button"
                  class="row-drag-handle"
                  aria-label="拖动排序"
                  @mousedown.stop
                >
                  ⋮⋮
                </button>
              </td>

              <template v-if="item.type === 'standard'">
                <th scope="row">
                  {{ item.field.label }}
                  <span v-if="item.field.required" class="required-mark">*</span>
                  <span v-if="isConflict(item.key)" class="badge warn">多文件冲突</span>
                  <span v-if="isRejected(item.key)" class="badge rejected">法务驳回</span>
                </th>
                <td>
                  <template v-if="editable">
                    <input
                      v-if="item.field.type === 'text'"
                      v-model="form[item.key]"
                      class="cell-input"
                      :class="{ 'input-conflict': isConflict(item.key) }"
                      :placeholder="placeholderFor(item.key, item.field)"
                    />
                    <input
                      v-else-if="item.field.type === 'number'"
                      v-model.number="form[item.key]"
                      type="number"
                      min="1"
                      class="cell-input"
                      :class="{ 'input-conflict': isConflict(item.key) }"
                      :placeholder="placeholderFor(item.key, item.field)"
                    />
                    <input
                      v-else-if="item.field.type === 'date'"
                      v-model="form[item.key]"
                      type="date"
                      class="cell-input"
                      :class="{ 'input-conflict': isConflict(item.key) }"
                    />
                    <ConflictHighlightTextarea
                      v-else-if="item.field.type === 'textarea' && conflictFor(item.key)"
                      v-model="form[item.key]"
                      :conflict-sources="conflictFor(item.key)!.sources"
                      :rows="item.field.rows"
                      :placeholder="placeholderFor(item.key, item.field)"
                    />
                    <AutoGrowTextarea
                      v-else
                      v-model="form[item.key]"
                      :input-class="`cell-textarea${isConflict(item.key) ? ' input-conflict' : ''}`"
                      :rows="item.field.rows"
                      :placeholder="placeholderFor(item.key, item.field)"
                    />
                    <div
                      v-for="merged in mergedFieldsFor(item.key, item.field.label)"
                      :key="merged.id"
                      class="merged-custom-field-block"
                    >
                      <div class="merged-custom-field-head">
                        <input
                          v-if="structuralEditing"
                          :value="merged.label"
                          class="cell-input cell-field-label"
                          placeholder="补充说明标题"
                          @input="updateCustomField(merged.id, { label: ($event.target as HTMLInputElement).value })"
                        />
                        <span v-else-if="merged.label" class="merged-custom-field-title">{{ merged.label }}</span>
                        <span class="badge muted-badge">合并</span>
                        <button
                          v-if="structuralEditing"
                          type="button"
                          class="btn-text btn-danger-text"
                          @click="removeCustomField(merged.id)"
                        >
                          删除
                        </button>
                      </div>
                      <textarea
                        v-if="editable"
                        :value="merged.value"
                        class="cell-textarea"
                        :rows="CUSTOM_FIELD_ROWS"
                        placeholder="填写要合并到该字段的补充内容"
                        @input="updateCustomField(merged.id, { value: ($event.target as HTMLTextAreaElement).value })"
                      />
                      <p v-else class="merged-custom-field-value">{{ merged.value || '—' }}</p>
                    </div>
                  </template>
                  <template v-else>
                    <ConflictHighlightTextarea
                      v-if="item.field.type === 'textarea' && conflictFor(item.key)"
                      :model-value="String(form[item.key] ?? '')"
                      :conflict-sources="conflictFor(item.key)!.sources"
                      :rows="item.field.rows"
                      readonly
                    />
                    <div v-else>{{ displayValue(item.key, form[item.key]) }}</div>
                    <div
                      v-for="merged in mergedFieldsFor(item.key, item.field.label)"
                      :key="merged.id"
                      class="merged-custom-field-block merged-custom-field-block--readonly"
                    >
                      <p v-if="merged.label" class="merged-custom-field-title">{{ merged.label }}</p>
                      <p class="merged-custom-field-value">{{ merged.value || '—' }}</p>
                    </div>
                  </template>
                </td>
                <td v-if="structuralEditing" class="col-row-actions">
                  <button
                    v-if="canDeleteReviewField(item.key, catalog)"
                    type="button"
                    class="btn-text btn-danger-text"
                    @click="removeStandardField(item.key)"
                  >
                    删除
                  </button>
                  <span v-else class="muted">—</span>
                </td>
              </template>

              <template v-else>
                <th scope="row">
                  <div class="custom-field-name-stack">
                    <template v-if="structuralEditing">
                      <input
                        :value="item.field.label"
                        class="cell-input cell-field-label"
                        placeholder="标题名称"
                        @input="updateCustomField(item.field.id, { label: ($event.target as HTMLInputElement).value })"
                      />
                    </template>
                    <template v-else>{{ item.field.label || '—' }}</template>
                  </div>
                </th>
                <td>
                  <template v-if="editable">
                    <textarea
                      :value="item.field.value"
                      class="cell-textarea"
                      :rows="CUSTOM_FIELD_ROWS"
                      placeholder="填写内容"
                      @input="updateCustomField(item.field.id, { value: ($event.target as HTMLTextAreaElement).value })"
                    />
                  </template>
                  <template v-else>{{ item.field.value || '—' }}</template>
                </td>
                <td v-if="structuralEditing" class="col-row-actions">
                  <button type="button" class="btn-text btn-danger-text" @click="removeCustomField(item.field.id)">
                    删除
                  </button>
                </td>
              </template>
            </tr>
          </template>
        </tbody>
      </table>
    </section>

    <div v-if="$slots['before-facts']" class="material-review-inline-actions">
      <slot name="before-facts" />
    </div>

    <section
      v-if="facts.length"
      class="panel extract-table-panel extract-facts-section"
      :class="{ 'extract-facts-section--expanded': factsExpanded }"
    >
      <button
        type="button"
        class="extract-facts-toggle"
        :aria-expanded="factsExpanded"
        @click="factsExpanded = !factsExpanded"
      >
        <span class="extract-facts-chevron" aria-hidden="true">{{ factsExpanded ? '▾' : '▸' }}</span>
        <span class="extract-facts-toggle-title">抽取依据明细</span>
        <span class="muted extract-facts-count">{{ facts.length }} 条</span>
      </button>
      <div v-show="factsExpanded" class="extract-facts-body">
        <p class="muted">每条对应方案原文片段，便于核对 AI / 规则抽取是否准确。</p>
        <table class="extract-fields-table extract-facts-table">
          <thead>
            <tr>
              <th>字段</th>
              <th>值</th>
              <th v-if="facts.some((f) => f.source_filename)">来源文件</th>
              <th>原文依据</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(fact, idx) in facts" :key="idx" :class="{ 'fact-unverified': fact.verification_status === 'unverified' }">
              <th scope="row">
                {{ factLabel(fact.field) }}
                <span v-if="fact.verification_status === 'unverified'" class="badge warn sm">待核对</span>
                <span v-else-if="fact.verification_status === 'verified'" class="badge ok sm">已验</span>
              </th>
              <td>{{ fact.value }}</td>
              <td v-if="facts.some((f) => f.source_filename)" class="muted">{{ fact.source_filename || '—' }}</td>
              <td class="muted">{{ fact.source_snippet || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
