<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import {
  confirmScenarioScope,
  previewMaterialReview,
  returnScenarioMaterials,
  downloadScenarioMaterialFile,
} from '@/api/client'
import { reviewFieldsForDimensions, uiGroupLabelForField } from '@/config/businessMaterialReviewFields'
import type { DimensionInfo, MaterialReviewPreview, RulesCatalog, Scenario } from '@/types/scenario'

const props = defineProps<{
  scenario: Scenario
  catalog: RulesCatalog
}>()

const emit = defineEmits<{
  scopeConfirmed: [scenario: Scenario]
  materialsReturned: []
}>()

const selected = ref<string[]>([])
const submitting = ref(false)
const returning = ref(false)
const previewLoading = ref(false)
const materialPreview = ref<MaterialReviewPreview | null>(null)
const legalMissingFields = ref<string[]>([])
const returnNote = ref('')
const error = ref<string | null>(null)

const archivedFiles = computed(() => props.scenario.document_extract?.archived_files ?? [])

async function downloadArchivedFile(storedName: string, filename: string) {
  await downloadScenarioMaterialFile(props.scenario.id, storedName, filename)
}

const suggestedDimensions = computed(() => {
  const fromExtract = props.scenario.document_extract?.compliance_dimensions || []
  return fromExtract.filter((id) => props.catalog.dimensions.some((d) => d.id === id))
})

const visibleFields = computed(() => reviewFieldsForDimensions(props.catalog, selected.value))

const canConfirm = computed(
  () =>
    selected.value.length > 0 &&
    !submitting.value &&
    !returning.value &&
    (materialPreview.value?.auto_missing_fields.length ?? 0) === 0,
)

const canReturn = computed(
  () =>
    selected.value.length > 0 &&
    legalMissingFields.value.length > 0 &&
    !submitting.value &&
    !returning.value,
)

const groupedMissing = computed(() => {
  const preview = materialPreview.value
  if (!preview) return []
  const groups: Array<{ dimensionId: string; dimensionName: string; fields: string[] }> = []
  for (const dim of selected.value) {
    const fields = preview.missing_by_dimension[dim] || []
    if (!fields.length) continue
    const dimInfo = props.catalog.dimensions.find((d) => d.id === dim)
    groups.push({
      dimensionId: dim,
      dimensionName: dimInfo?.name || dim,
      fields,
    })
  }
  return groups
})

function fieldLabel(key: string) {
  const base = materialPreview.value?.field_labels[key] || key
  const group = uiGroupLabelForField(key, props.catalog)
  return group ? `${group} · ${base}` : base
}

function displayFieldValue(key: string) {
  const value = materialPreview.value?.field_values[key]
  if (value === null || value === undefined || value === '') return '—'
  if (key === 'employee_count') return `${value} 人`
  return String(value)
}

function toggleDimension(id: string) {
  const set = new Set(selected.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  selected.value = [...set]
}

function toggleMissingField(key: string) {
  const set = new Set(legalMissingFields.value)
  if (set.has(key)) set.delete(key)
  else set.add(key)
  legalMissingFields.value = [...set]
}

async function refreshMaterialPreview() {
  if (selected.value.length === 0) {
    materialPreview.value = null
    legalMissingFields.value = []
    return
  }
  previewLoading.value = true
  error.value = null
  try {
    const preview = (await previewMaterialReview(
      props.scenario.id,
      selected.value,
    )) as MaterialReviewPreview
    materialPreview.value = preview
    legalMissingFields.value = [...preview.auto_missing_fields]
  } catch (e: unknown) {
    materialPreview.value = null
    legalMissingFields.value = []
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '材料完整性预览失败'
    }
  } finally {
    previewLoading.value = false
  }
}

watch(selected, () => {
  void refreshMaterialPreview()
})

onMounted(async () => {
  if (suggestedDimensions.value.length) {
    selected.value = [...suggestedDimensions.value]
  } else if (props.catalog.dimensions.length) {
    selected.value = props.catalog.dimensions.map((d: DimensionInfo) => d.id)
  }
  await refreshMaterialPreview()
})

async function confirmScope() {
  if (!canConfirm.value) return
  submitting.value = true
  error.value = null
  try {
    const updated = await confirmScenarioScope(props.scenario.id, selected.value, false)
    emit('scopeConfirmed', updated)
  } catch (e: unknown) {
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '确认失败，请稍后重试'
    } else {
      error.value = '确认失败，请稍后重试'
    }
  } finally {
    submitting.value = false
  }
}

async function returnMaterials() {
  if (!canReturn.value) return
  returning.value = true
  error.value = null
  try {
    await returnScenarioMaterials(props.scenario.id, {
      compliance_dimensions: selected.value,
      missing_fields: legalMissingFields.value,
      note: returnNote.value.trim() || null,
    })
    emit('materialsReturned')
  } catch (e: unknown) {
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '驳回失败，请稍后重试'
    } else {
      error.value = '驳回失败，请稍后重试'
    }
  } finally {
    returning.value = false
  }
}
</script>

<template>
  <section class="panel review-gate-section">
    <div class="review-gate-head">
      <h2>① 协查范围与材料完整性</h2>
      <p class="muted">
        选择合规审查维度并核对业务提交表；缺项可字段级驳回，完整后确认范围并自动生成清单。
      </p>
    </div>

    <div class="review-gate-split">
      <aside class="review-gate-scope-column">
        <h3>协查范围</h3>
        <p class="muted scope-ai-hint" v-if="suggestedDimensions.length">
          AI 识别（仅供参考）：{{
            suggestedDimensions
              .map((id) => catalog.dimensions.find((d) => d.id === id)?.name)
              .filter(Boolean)
              .join('、')
          }}
        </p>
        <p class="muted scope-ai-hint" v-else>勾选本次协查覆盖的合规维度；右侧表格随选择实时更新。</p>
        <div class="dimension-grid dimension-grid-sidebar">
          <label
            v-for="dim in catalog.dimensions"
            :key="dim.id"
            class="dimension-card"
            :class="{ active: selected.includes(dim.id) }"
          >
            <input
              type="checkbox"
              :value="dim.id"
              :checked="selected.includes(dim.id)"
              @change="toggleDimension(dim.id)"
            />
            <div class="dimension-body">
              <strong>{{ dim.name }}</strong>
              <span class="dim-pt">{{ dim.name_pt }}</span>
              <p>{{ dim.description }}</p>
            </div>
          </label>
        </div>
      </aside>

      <div class="review-gate-material-column">
        <div v-if="archivedFiles.length" class="archived-files-block panel">
          <h3>归档方案文件</h3>
          <p class="muted">业务提交时上传的原始方案，可下载回看。</p>
          <ul class="archived-files-list">
            <li v-for="file in archivedFiles" :key="file.id">
              <button type="button" class="btn-link sm" @click="downloadArchivedFile(file.stored_name, file.filename)">
                {{ file.filename }}
              </button>
              <span class="muted">{{ (file.size / 1024).toFixed(0) }} KB</span>
            </li>
          </ul>
        </div>

        <template v-if="selected.length">
          <div class="material-gate-head">
            <h3>提交表完整性</h3>
            <p class="muted">
              按左侧所选维度展示对应字段；驳回对象为<strong>最终提交表</strong>，业务改表即可。
            </p>
            <p v-if="previewLoading" class="muted">正在检测材料完整性…</p>
          </div>

          <div v-if="materialPreview" class="material-gate-body">
            <div class="material-field-table-wrap">
              <table class="extract-fields-table material-review-table legal-material-table">
                <thead>
                  <tr>
                    <th class="col-field">字段</th>
                    <th class="col-value">提交值</th>
                    <th class="col-status">状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="field in visibleFields"
                    :key="field.key"
                    :class="{ 'row-missing': materialPreview.auto_missing_fields.includes(field.key) }"
                  >
                    <th scope="row" class="col-field">
                      <span v-if="uiGroupLabelForField(field.key, catalog)" class="field-group-tag">
                        {{ uiGroupLabelForField(field.key, catalog) }}
                      </span>
                      {{ field.label }}
                    </th>
                    <td class="col-value">{{ displayFieldValue(field.key) }}</td>
                    <td class="col-status">
                      <span
                        v-if="materialPreview.auto_missing_fields.includes(field.key)"
                        class="badge rejected status-badge"
                      >
                        缺项
                      </span>
                      <span v-else class="badge ok status-badge">已填</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="material-return-block">
              <h4>驳回缺项（按维度）</h4>
              <p class="muted">自动缺项已预选；您可取消或补充勾选其他字段。</p>

              <div v-for="group in groupedMissing" :key="group.dimensionId" class="missing-dimension-group">
                <strong>{{ group.dimensionName }}</strong>
                <div class="missing-field-checks">
                  <label
                    v-for="key in group.fields"
                    :key="`${group.dimensionId}-${key}`"
                    class="missing-field-check"
                  >
                    <input
                      type="checkbox"
                      :checked="legalMissingFields.includes(key)"
                      @change="toggleMissingField(key)"
                    />
                    {{ fieldLabel(key) }}
                  </label>
                </div>
              </div>

              <label class="return-note-field">
                <span>退回说明</span>
                <textarea v-model="returnNote" rows="2" placeholder="例如：请补充本地雇员规模与分阶段招聘计划" />
              </label>
            </div>
          </div>
        </template>
        <div v-else class="material-column-empty panel">
          <p class="muted">请先在左侧勾选至少一个合规维度，此处将展示对应提交表字段与缺项检测。</p>
        </div>
      </div>
    </div>

    <div v-if="selected.length" class="material-gate-footer">
      <p class="error" v-if="error">{{ error }}</p>

      <div class="form-actions material-gate-actions">
        <RouterLink :to="`/scenarios/${scenario.id}/extract`" class="btn-secondary link-btn sm">
          查看 AI 抽取表
        </RouterLink>
        <button type="button" class="btn-secondary" :disabled="!canReturn" @click="returnMaterials">
          {{ returning ? '驳回中…' : `驳回补充材料（${legalMissingFields.length} 项）` }}
        </button>
        <button type="button" class="btn-primary" :disabled="!canConfirm" @click="confirmScope">
          {{ submitting ? '生成中…' : `确认范围并生成清单（${selected.length} 个维度）` }}
        </button>
      </div>
      <p class="muted gate-hint" v-if="materialPreview?.auto_missing_fields.length">
        仍有 {{ materialPreview.auto_missing_fields.length }} 项自动缺项，请先驳回业务补充后再确认。
      </p>
    </div>
  </section>
</template>
