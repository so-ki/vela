<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import BusinessReviewModal from '@/components/BusinessReviewModal.vue'
import MaterialFieldSections from '@/components/MaterialFieldSections.vue'
import { REVIEW_FIELD_LABELS, allReviewFieldsFromCatalog, collectMissingSubmitRequiredFields, reviewFieldsForDimensions, type CustomReviewField } from '@/config/businessMaterialReviewFields'
import {
  applySceneDefaults,
  countryLabelForCatalog,
  regionLabelForCatalog,
  sceneDefaultsFromCatalog,
} from '@/config/sceneClassification'
import { createDemoScenario, createScenario, extractDocumentsFromFiles, fetchDemoTemplate, fetchRulesCatalog, fetchScenario, reviseAndResubmitScenario, submitMaterialsScenario } from '@/api/client'
import type { DocumentExtractBatchResult, DocumentExtractResult } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useMaterialReviewDraftStore } from '@/stores/materialReviewDraft'
import type { DimensionInfo, RulesCatalog, ScenarioFormData } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const draft = useMaterialReviewDraftStore()
const editMode = computed(() => route.name === 'scenario-edit')
const editScenarioId = computed(() => (editMode.value ? Number(route.params.id) : null))
const catalog = ref<RulesCatalog | null>(null)
const loading = ref(false)
const submitting = ref(false)
const extracting = ref(false)
const error = ref<string | null>(null)
const extractBatch = ref<DocumentExtractBatchResult | null>(null)
const pendingFiles = ref<File[]>([])
const extractFailedNotes = ref<string[]>([])
const showFormDetails = ref(false)
const reviewModalOpen = ref(false)
const reviewModalPhase = ref<'editable' | 'confirm'>('editable')
const modalError = ref<string | null>(null)
const showFieldValidation = ref(false)
const materialScopeDimensions = ref<string[]>([])
const rejectedFieldKeys = ref<string[]>([])
const hiddenReviewFieldKeys = ref<string[]>([])
const reviewCustomFields = ref<CustomReviewField[]>([])
const reviewRowOrder = ref<string[]>([])

const FIELD_LABELS: Record<string, string> = REVIEW_FIELD_LABELS

const LEGAL_FIELD_PLACEHOLDERS: Record<string, string> = {
  project_name: 'BYD 坎皮纳斯新能源工厂',
  investment_structure: '100% 外资全资子公司',
  employee_count: '450',
  facility_notes: '32,000 m² + 20,000 m²',
  capacity_notes: '首年 1000 台客车及电池',
  description: '请用 3～5 句话描述投资场景…',
  remarks: '其他需说明事项',
}

const activeReviewFields = computed(() => {
  // 业务新建：始终展示完整 14 项核对表（对齐境外投资材料业务确认项）
  if (businessUploadOnly.value) {
    return allReviewFieldsFromCatalog(catalog.value)
  }
  if (editMode.value && materialScopeDimensions.value.length) {
    return reviewFieldsForDimensions(catalog.value, materialScopeDimensions.value)
  }
  return allReviewFieldsFromCatalog(catalog.value)
})

const validationIssues = computed(() => collectValidationIssues())

const extractResult = computed(() => extractBatch.value?.merged ?? null)
const perFileResults = computed(() => extractBatch.value?.files ?? [])
const hasMultiFileExtract = computed(() => perFileResults.value.length > 1)

const extractConflicts = computed(() => extractBatch.value?.conflicts ?? [])

const conflictFieldKeys = computed(() => extractConflicts.value.map((item) => item.field))

const extractModeLabel = computed(() => {
  if (!extractResult.value) return '手动填写'
  if (hasMultiFileExtract.value) return '多文件合并'
  return extractResult.value.mode === 'llm' ? 'AI 抽取' : '规则抽取'
})

const reviewFacts = computed(() => extractResult.value?.facts ?? [])

const reviewDisclaimer = computed(() => {
  if (extractResult.value?.disclaimer) return extractResult.value.disclaimer
  if (auth.isBusiness) {
    return '请核对抽取信息；如需修改请点击「信息修改」。确认无误后再提交材料。不构成法律意见。'
  }
  return '以下信息来自上传方案抽取或提交表单，仅供核对。'
})

const reviewMissingKeys = computed(() =>
  collectMissingSubmitRequiredFields(form.value, activeReviewFields.value, catalog.value),
)

const businessResponsibilityHint = computed(
  () => catalog.value?.material_intake_policy?.business_responsibility_hint as string | undefined,
)

/** 业务新建：仅上传 + 核对 Modal；手填表单只在法务端或业务补充(edit)页出现 */
const businessUploadOnly = computed(() => auth.isBusiness && !editMode.value)

const showInlineMaterialForm = computed(() => {
  if (businessUploadOnly.value) return false
  if (auth.isBusiness) return editMode.value
  return true
})

const canOpenReviewModal = computed(
  () => auth.isBusiness && (!!extractResult.value || editMode.value),
)

const form = ref<ScenarioFormData>(createInitialForm())

function createInitialForm(): ScenarioFormData {
  const defaults = sceneDefaultsFromCatalog(catalog.value)
  return {
    project_name: '',
    rules_pack_id: defaults.rules_pack_id,
    country: defaults.country,
    state: defaults.state,
    city: defaults.city,
    industry: defaults.industry,
    action_type: defaults.action_type,
    investment_destination: '',
    investment_structure: '',
    funding_source: '',
    project_content_scale: '',
    description: '',
    known_risks: '',
    employee_count: undefined,
    capacity_notes: '',
    facility_notes: '',
    compliance_dimensions: [],
    board_date: '',
    start_date: '',
    production_date: '',
    remarks: '',
  }
}

/** 业务端：空白表单（地点/行业等在提交时由系统补默认值，不在界面预填） */
function createEmptyBusinessForm(): ScenarioFormData {
  return {
    project_name: '',
    country: '',
    state: '',
    city: '',
    industry: '',
    action_type: '',
    investment_destination: '',
    investment_structure: '',
    funding_source: '',
    project_content_scale: '',
    description: '',
    known_risks: '',
    employee_count: undefined,
    capacity_notes: '',
    facility_notes: '',
    compliance_dimensions: [],
    board_date: '',
    start_date: '',
    production_date: '',
    remarks: '',
  }
}

function applyBusinessSubmitDefaults<T extends Record<string, unknown>>(payload: T): T {
  return applySceneDefaults(payload, catalog.value)
}

const activeRegionLabel = computed(() => regionLabelForCatalog(catalog.value))
const activeCountryLabel = computed(() => countryLabelForCatalog(catalog.value))

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    catalog.value = await fetchRulesCatalog()
    if (!auth.isBusiness && !editMode.value) {
      const defaults = sceneDefaultsFromCatalog(catalog.value)
      form.value = {
        ...form.value,
        rules_pack_id: defaults.rules_pack_id,
        country: defaults.country,
        state: defaults.state,
        city: defaults.city,
        industry: defaults.industry,
        action_type: defaults.action_type,
      }
    }
    if (editMode.value && editScenarioId.value) {
      const scenario = await fetchScenario(editScenarioId.value)
      if (!scenario.can_revise) {
        error.value = '该项目当前不可补充编辑，请返回进度页查看状态'
        return
      }
      form.value = {
        project_name: scenario.project_name,
        country: scenario.country,
        state: scenario.state,
        city: scenario.city,
        industry: scenario.industry,
        action_type: scenario.action_type,
        investment_destination: scenario.investment_destination || '',
        investment_structure: scenario.investment_structure || '',
        funding_source: scenario.funding_source || '',
        project_content_scale: scenario.project_content_scale || '',
        description: scenario.description,
        known_risks: scenario.known_risks || '',
        employee_count: scenario.employee_count ?? undefined,
        capacity_notes: scenario.capacity_notes || '',
        facility_notes: scenario.facility_notes || '',
        compliance_dimensions: [],
        board_date: scenario.board_date || '',
        start_date: scenario.start_date || '',
        production_date: scenario.production_date || '',
        remarks: scenario.remarks || '',
      }
      if (auth.isBusiness) {
        showFormDetails.value = true
      }
      materialScopeDimensions.value = [...(scenario.material_scope_dimensions || scenario.material_feedback?.selected_dimensions || [])]
      rejectedFieldKeys.value = [...(scenario.material_feedback?.missing_fields || [])]
      return
    }
    if (auth.isBusiness) {
      form.value = createEmptyBusinessForm()
    }
    if (!auth.isBusiness && form.value.compliance_dimensions.length === 0 && catalog.value) {
      form.value.compliance_dimensions = catalog.value.dimensions.map((d: DimensionInfo) => d.id)
    }
    if (!auth.isBusiness && !form.value.project_name.trim() && !form.value.description.trim()) {
      await loadDemo()
    }
  } catch (e: unknown) {
    error.value = extractApiError(e)
  } finally {
    loading.value = false
  }
})

async function loadDemo() {
  error.value = null
  try {
    const tpl = await fetchDemoTemplate()
    form.value = {
      ...form.value,
      ...tpl,
      board_date: tpl.board_date || '',
      start_date: tpl.start_date || '',
      production_date: tpl.production_date || '',
    }
  } catch (e: unknown) {
    error.value = extractApiError(e)
  }
}

function ensureAllDimensions() {
  if (!auth.isBusiness && catalog.value && form.value.compliance_dimensions.length === 0) {
    form.value.compliance_dimensions = catalog.value.dimensions.map((d: DimensionInfo) => d.id)
  }
}

function toggleDimension(id: string) {
  const set = new Set(form.value.compliance_dimensions)
  if (set.has(id)) {
    set.delete(id)
  } else {
    set.add(id)
  }
  form.value.compliance_dimensions = [...set]
}

async function buildPayload() {
  const base = {
    ...form.value,
    project_name: form.value.project_name.trim(),
    description: form.value.description.trim(),
    investment_destination: form.value.investment_destination?.trim() || null,
    investment_structure: form.value.investment_structure?.trim() || null,
    funding_source: form.value.funding_source?.trim() || null,
    project_content_scale: form.value.project_content_scale?.trim() || null,
    known_risks: form.value.known_risks?.trim() || null,
    capacity_notes: form.value.capacity_notes?.trim() || null,
    facility_notes: form.value.facility_notes?.trim() || null,
    remarks: form.value.remarks?.trim() || null,
    employee_count: form.value.employee_count || null,
    board_date: form.value.board_date || null,
    start_date: form.value.start_date || null,
    production_date: form.value.production_date || null,
  }

  function buildFactsFromForm() {
    const entries: Array<{ field: string; value: string; source_snippet: string | null }> = []
    const push = (field: string, value: string | number | null | undefined) => {
      const text = value === null || value === undefined ? '' : String(value).trim()
      if (text) entries.push({ field, value: text, source_snippet: null })
    }
    push('project_name', base.project_name)
    push('investment_destination', base.investment_destination)
    push('investment_structure', base.investment_structure)
    push('funding_source', base.funding_source)
    push('project_content_scale', base.project_content_scale)
    push('employee_count', base.employee_count)
    push('capacity_notes', base.capacity_notes)
    push('facility_notes', base.facility_notes)
    push('description', base.description)
    push('known_risks', base.known_risks)
    push('board_date', base.board_date)
    push('start_date', base.start_date)
    push('production_date', base.production_date)
    push('remarks', base.remarks)
    return entries
  }

  const extractFieldSnapshot = (file: DocumentExtractResult) => ({
    filename: file.filename,
    mode: file.mode,
    project_name: file.project_name ?? null,
    investment_destination: file.investment_destination ?? null,
    investment_structure: file.investment_structure ?? null,
    funding_source: file.funding_source ?? null,
    project_content_scale: file.project_content_scale ?? null,
    description: file.description ?? null,
    known_risks: file.known_risks ?? null,
    employee_count: file.employee_count ?? null,
    capacity_notes: file.capacity_notes ?? null,
    facility_notes: file.facility_notes ?? null,
    board_date: file.board_date ?? null,
    start_date: file.start_date ?? null,
    production_date: file.production_date ?? null,
    remarks: file.remarks ?? null,
    compliance_dimensions: file.compliance_dimensions || [],
    facts: file.facts,
    disclaimer: file.disclaimer,
    llm_skipped: file.llm_skipped ?? null,
  })

  const mergedFormSnapshot = (withDefaults: Record<string, unknown>) => ({
    project_name: withDefaults.project_name,
    investment_destination: withDefaults.investment_destination,
    investment_structure: withDefaults.investment_structure,
    funding_source: withDefaults.funding_source,
    project_content_scale: withDefaults.project_content_scale,
    description: withDefaults.description,
    known_risks: withDefaults.known_risks,
    employee_count: withDefaults.employee_count,
    capacity_notes: withDefaults.capacity_notes,
    facility_notes: withDefaults.facility_notes,
    board_date: withDefaults.board_date,
    start_date: withDefaults.start_date,
    production_date: withDefaults.production_date,
    remarks: withDefaults.remarks,
  })

  function buildDocumentExtractSnapshot(withDefaults: Record<string, unknown>) {
    const merged = extractResult.value
    const fileSnapshots = perFileResults.value.map((file) => extractFieldSnapshot(file))
    const customFieldSnapshot = reviewCustomFields.value
      .filter((field) => field.label.trim() || field.value.trim())
      .map((field) => ({
        id: field.id,
        label: field.label.trim(),
        value: field.value.trim(),
        layout: field.layout ?? 'standalone',
        merge_target_key: field.mergeTargetKey ?? null,
        merge_target_label: field.mergeTargetLabel ?? null,
      }))

    if (merged) {
      const facts = merged.facts?.length ? merged.facts : buildFactsFromForm()
      for (const field of customFieldSnapshot) {
        const mergeHint = field.merge_target_label
          ? `（合并@${field.merge_target_label}）`
          : field.merge_target_key
            ? `（合并@${field.merge_target_key}）`
            : ''
        facts.push({
          field: `custom:${field.id}`,
          value: `${field.label}${mergeHint}`,
          source_snippet: field.value.slice(0, 80) || null,
        })
      }
      return {
        filename: merged.filename,
        file_count: fileSnapshots.length || 1,
        files: fileSnapshots,
        mode: merged.mode,
        source: 'upload',
        ...mergedFormSnapshot(withDefaults),
        compliance_dimensions: merged.compliance_dimensions || [],
        facts,
        disclaimer: reviewDisclaimer.value,
        llm_skipped: merged.llm_skipped ?? null,
        field_conflicts: extractConflicts.value,
        hidden_field_keys: [...hiddenReviewFieldKeys.value],
        custom_fields: customFieldSnapshot,
        field_display_order: [...reviewRowOrder.value],
      }
    }

    return {
      filename: '（手动填写）',
      file_count: 0,
      files: [],
      mode: 'manual',
      source: 'manual',
      ...mergedFormSnapshot(withDefaults),
      compliance_dimensions: [],
      facts: buildFactsFromForm(),
      disclaimer: reviewDisclaimer.value,
      hidden_field_keys: [...hiddenReviewFieldKeys.value],
      custom_fields: customFieldSnapshot,
      field_display_order: [...reviewRowOrder.value],
    }
  }

  if (auth.isBusiness) {
    const { compliance_dimensions: _dims, ...businessBase } = base as typeof base & { compliance_dimensions?: string[] }
    const withDefaults = applyBusinessSubmitDefaults(businessBase)
    return {
      ...withDefaults,
      document_extract: buildDocumentExtractSnapshot(withDefaults),
    }
  }
  ensureAllDimensions()
  if (extractResult.value) {
    const merged = extractResult.value
    const fileSnapshots = perFileResults.value.map((file) => extractFieldSnapshot(file))
    return {
      ...base,
      compliance_dimensions: form.value.compliance_dimensions,
      document_extract: {
        filename: merged.filename,
        file_count: fileSnapshots.length || 1,
        files: fileSnapshots,
        mode: merged.mode,
        source: 'upload',
        project_name: merged.project_name ?? base.project_name,
        investment_destination: merged.investment_destination ?? base.investment_destination,
        investment_structure: merged.investment_structure ?? base.investment_structure,
        funding_source: merged.funding_source ?? base.funding_source,
        project_content_scale: merged.project_content_scale ?? base.project_content_scale,
        description: merged.description ?? base.description,
        known_risks: merged.known_risks ?? base.known_risks,
        employee_count: merged.employee_count ?? base.employee_count,
        capacity_notes: merged.capacity_notes ?? base.capacity_notes,
        facility_notes: merged.facility_notes ?? base.facility_notes,
        board_date: merged.board_date ?? base.board_date,
        start_date: merged.start_date ?? base.start_date,
        production_date: merged.production_date ?? base.production_date,
        remarks: merged.remarks ?? base.remarks,
        compliance_dimensions: merged.compliance_dimensions?.length
          ? merged.compliance_dimensions
          : base.compliance_dimensions,
        facts: merged.facts,
        disclaimer: merged.disclaimer,
        llm_skipped: merged.llm_skipped ?? null,
      },
    }
  }
  return {
    ...base,
    compliance_dimensions: form.value.compliance_dimensions,
    document_extract: {
      filename: '（手动填写）',
      mode: 'manual',
      source: 'manual',
      project_name: base.project_name,
      investment_structure: base.investment_structure,
      description: base.description,
      employee_count: base.employee_count,
      capacity_notes: base.capacity_notes,
      facility_notes: base.facility_notes,
      remarks: base.remarks,
      compliance_dimensions: base.compliance_dimensions,
      facts: [
        { field: 'project_name', value: base.project_name, source_snippet: null },
        { field: 'description', value: base.description, source_snippet: null },
      ],
      disclaimer: '业务侧手动填写提交，未上传方案文件；提交后可在此回看表单内容。',
    },
  }
}

function collectValidationIssues(): string[] {
  const issues: string[] = []
  if (auth.isBusiness && !editMode.value && !pendingFiles.value.length) {
    issues.push('投资方案文件')
  }
  for (const key of collectMissingSubmitRequiredFields(form.value, activeReviewFields.value, catalog.value)) {
    const label = catalog.value?.material_fields?.find((f) => f.key === key)?.label || FIELD_LABELS[key] || key
    if (key === 'description') {
      const desc = form.value.description.trim()
      if (desc && desc.length < 10) {
        issues.push(`${label}（至少 10 个字，当前 ${desc.length} 字）`)
        continue
      }
    }
    issues.push(label)
  }
  ensureAllDimensions()
  if (!auth.isBusiness && form.value.compliance_dimensions.length === 0) {
    issues.push('协查范围（至少选择一个合规维度）')
  }
  return issues
}

function validateForm(target: 'page' | 'modal' = 'page'): boolean {
  const issues = collectValidationIssues()
  if (issues.length) {
    const msg = `请补充以下信息：${issues.join('、')}`
    if (target === 'modal') modalError.value = msg
    else error.value = msg
    return false
  }
  if (target === 'modal') modalError.value = null
  else error.value = null
  return true
}

function goToMaterialReview() {
  error.value = null
  if (!pendingFiles.value.length) {
    error.value = '请先上传至少一个方案文件'
    return
  }
  if (extracting.value) {
    error.value = '文件抽取中，请稍候再确认'
    return
  }
  if (!extractResult.value) {
    error.value = '尚未完成抽取，请稍候或重新上传'
    return
  }
  draft.setDraft({
    form: { ...form.value },
    extractBatch: extractBatch.value,
    pendingFiles: pendingFiles.value,
    hiddenFieldKeys: [...hiddenReviewFieldKeys.value],
    customFields: [...reviewCustomFields.value],
    rowOrder: [...reviewRowOrder.value],
  })
  void router.push({ name: 'material-review' })
}

function openReviewModalEditable() {
  reviewModalPhase.value = 'editable'
  reviewModalOpen.value = true
  modalError.value = null
  showFieldValidation.value = false
  nextTick(() => {
    document.querySelector('.business-review-modal-body')?.scrollTo({ top: 0, behavior: 'instant' })
  })
}

function openReviewModalFromForm() {
  if (businessUploadOnly.value) {
    goToMaterialReview()
    return
  }
  showFieldValidation.value = true
  if (!validateForm('modal')) return
  openReviewModalEditable()
}

function closeReviewModal() {
  reviewModalOpen.value = false
  reviewModalPhase.value = 'editable'
  modalError.value = null
  showFieldValidation.value = false
}

function goToConfirmPreview() {
  showFieldValidation.value = true
  if (!validateForm('modal')) return
  showFieldValidation.value = false
  modalError.value = null
  reviewModalPhase.value = 'confirm'
}

function backToEditableFromConfirm() {
  reviewModalPhase.value = 'editable'
  modalError.value = null
}

async function finalSubmitFromModal() {
  showFieldValidation.value = true
  if (!validateForm('modal')) {
    reviewModalPhase.value = 'editable'
    return
  }
  showFieldValidation.value = false
  modalError.value = null
  submitting.value = true
  try {
    const payload = await buildPayload()
    const uploadFiles = pendingFiles.value.length ? pendingFiles.value : undefined
    if (editMode.value && editScenarioId.value) {
      const scenario = await reviseAndResubmitScenario(editScenarioId.value, payload, uploadFiles)
      closeReviewModal()
      await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
      return
    }
    const scenario = await submitMaterialsScenario(payload, uploadFiles)
    closeReviewModal()
    await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
  } catch (e: unknown) {
    modalError.value = extractApiError(e)
  } finally {
    submitting.value = false
  }
}

async function submit() {
  if (!validateForm('page')) return
  submitting.value = true
  error.value = null
  try {
    const payload = await buildPayload()
    const uploadFiles = pendingFiles.value.length ? pendingFiles.value : undefined
    if (editMode.value && editScenarioId.value) {
      const scenario = await reviseAndResubmitScenario(editScenarioId.value, payload, uploadFiles)
      await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
      return
    }
    if (auth.isBusiness) {
      const scenario = await submitMaterialsScenario(payload, uploadFiles)
      await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
      return
    }
    const scenario = await createScenario(payload)
    router.push({ name: 'checklist', params: { id: scenario.id } })
  } catch (e: unknown) {
    error.value = extractApiError(e)
  } finally {
    submitting.value = false
  }
}

async function submitDemoQuick() {
  submitting.value = true
  error.value = null
  try {
    const scenario = await createDemoScenario()
    router.push({ name: 'checklist', params: { id: scenario.id } })
  } catch (e: unknown) {
    error.value = extractApiError(e)
  } finally {
    submitting.value = false
  }
}

function extractApiError(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const resp = (e as {
      response?: {
        status?: number
        data?: { detail?: string | Array<{ msg: string; loc?: string[] }> }
      }
    }).response
    if (resp?.status === 404) {
      return '后端未加载接口（404）。请重启服务：终端 Ctrl+C 后重新运行 ./scripts/start.sh'
    }
    const detail = resp?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const msgs = detail.map((d) => {
        const field = d.loc?.slice(-1)[0] || '字段'
        const label: Record<string, string> = {
          project_name: '项目名称',
          description: '业务描述',
          compliance_dimensions: '合规维度',
        }
        return `${label[field] || field}：${d.msg}`
      })
      return msgs.join('；')
    }
  }
  return '操作失败，请稍后重试'
}

function resetReviewStructureState() {
  hiddenReviewFieldKeys.value = []
  reviewCustomFields.value = []
  reviewRowOrder.value = []
}

function applyExtractResult(result: DocumentExtractResult, _options?: { openReviewTable?: boolean }) {
  resetReviewStructureState()
  if (result.project_name) form.value.project_name = result.project_name
  if (result.investment_destination) form.value.investment_destination = result.investment_destination
  if (result.investment_structure) form.value.investment_structure = result.investment_structure
  if (result.funding_source) form.value.funding_source = result.funding_source
  if (result.project_content_scale) form.value.project_content_scale = result.project_content_scale
  if (result.description) form.value.description = result.description
  if (result.known_risks) form.value.known_risks = result.known_risks
  if (result.employee_count) form.value.employee_count = result.employee_count
  if (result.capacity_notes) form.value.capacity_notes = result.capacity_notes
  if (result.facility_notes) form.value.facility_notes = result.facility_notes
  if (result.board_date) form.value.board_date = result.board_date
  if (result.start_date) form.value.start_date = result.start_date
  if (result.production_date) form.value.production_date = result.production_date
  if (result.remarks?.trim()) {
    const extra = result.remarks.trim()
    const desc = form.value.description.trim()
    if (extra && !desc.includes(extra)) {
      form.value.description = desc ? `${desc}${extra}` : extra
    }
  }
  if (!auth.isBusiness && result.compliance_dimensions?.length) {
    form.value.compliance_dimensions = result.compliance_dimensions
  }
  if (!auth.isBusiness) ensureAllDimensions()
  if (auth.isBusiness) {
    showFormDetails.value = true
  } else {
    showFormDetails.value = collectValidationIssues().length > 0
  }
}

function removePendingFile(index: number) {
  const next = pendingFiles.value.filter((_, i) => i !== index)
  pendingFiles.value = next
  if (!next.length) {
    extractBatch.value = null
    extractFailedNotes.value = []
    return
  }
  void runDocumentExtract(next)
}

async function runDocumentExtract(files: File[]) {
  if (!files.length) return

  extracting.value = true
  error.value = null
  extractFailedNotes.value = []
  try {
    const batch = await extractDocumentsFromFiles(files)
    extractBatch.value = batch
    extractFailedNotes.value = batch.failed
    pendingFiles.value = files
    applyExtractResult(batch.merged)
  } catch (e: unknown) {
    extractBatch.value = null
    error.value = extractApiError(e)
  } finally {
    extracting.value = false
  }
}

async function onDocumentSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = input.files ? Array.from(input.files) : []
  input.value = ''
  if (!selected.length) return

  const merged = [...pendingFiles.value]
  for (const file of selected) {
    if (!merged.some((existing) => existing.name === file.name && existing.size === file.size)) {
      merged.push(file)
    }
  }
  pendingFiles.value = merged
  await runDocumentExtract(merged)
}

function shouldHighlightField(fieldPrefix: string): boolean {
  if (auth.isBusiness && !showFieldValidation.value) return false
  return validationIssues.value.some((i) => i.startsWith(fieldPrefix))
}
</script>

<template>
  <div class="scenario-page">
    <header class="page-header">
      <div>
        <p class="eyebrow dark">{{ editMode ? '业务协查 · 补充材料' : auth.isBusiness ? '业务协查' : 'Step 2 · 规则库' }}</p>
        <h1>{{ editMode ? '补充项目材料' : auth.isBusiness ? '上传投资方案' : '提交协查场景' }}</h1>
        <p class="muted" v-if="editMode">
          法务已退回本项目。请根据下方批注意见修改描述或补充说明，保存后将<strong>重新提交材料</strong>（仍是同一项目，法务将再次确认协查范围）。
        </p>
        <p class="muted" v-else-if="!auth.isBusiness">输入业务场景描述，系统将映射法律审查维度并生成《专项核查清单》。</p>
        <p class="muted material-intake-note" v-else-if="auth.isBusiness && !editMode">
          请<strong>上传巴西投资方案</strong>（可多个文件）；系统按<strong>巴西法域</strong>抽取并核对，不限于设厂场景。全部上传完成后点击<strong>确认并核对</strong>。
        </p>
        <p class="industry-pack-note" v-if="catalog?.pack?.name && auth.isBusiness && !editMode">
          协查法域：<strong>{{ activeCountryLabel }}</strong><span class="muted">（{{ activeRegionLabel }}首发）</span>
          · {{ catalog.pack.name }}
          <span v-if="catalog.rules_pack_id" class="muted"> · {{ catalog.rules_pack_id }}</span>
          <span v-if="catalog.pack.industry_focus"> · {{ catalog.pack.industry_focus }}</span>
          <span v-if="catalog.pack.focus"> · {{ catalog.pack.focus }}</span>
        </p>
        <p class="industry-pack-note" v-else-if="catalog?.pack?.name && !auth.isBusiness">
          协查法域：<strong>{{ activeCountryLabel }}</strong> · {{ catalog.pack.name }}
          <span v-if="catalog.pack.focus"> · {{ catalog.pack.focus }}</span>
        </p>
        <p class="warn-note role-mismatch-note" v-if="!editMode && !auth.isBusiness && route.name === 'scenario-create'">
          当前登录为<strong>法务账号</strong>（{{ auth.user?.email }}），此页展示的是法务端完整表单。业务端请使用 <strong>biz@demo.vela</strong> 登录，新建协查只需上传方案文件。
        </p>
      </div>
      <div class="header-actions" v-if="!editMode && !auth.isBusiness">
        <button type="button" class="btn-secondary" @click="loadDemo" :disabled="loading">填入 BYD 演示模板</button>
        <button type="button" class="btn-secondary" @click="submitDemoQuick" :disabled="submitting">
          {{ submitting ? '处理中…' : '一键生成演示清单' }}
        </button>
      </div>
    </header>

    <form class="scenario-form panel" @submit.prevent="submit">
      <p class="error banner-error" v-if="error && !catalog">{{ error }}</p>

      <div
        class="form-section doc-upload-section"
        :class="{ 'has-extract': !!extractResult }"
      >
        <h2>上传投资方案</h2>
        <p class="muted" v-if="auth.isBusiness && !editMode">
          支持 <strong>.txt / .md / .docx / .pdf</strong>（每个≤200MB，可上传多个）。上传后系统在后台抽取；<strong>全部文件就绪后</strong>再点「确认并核对」。原始文件将<strong>一并归档</strong>供法务回看。
        </p>
        <p class="muted" v-else>
          支持 <strong>.txt / .md / .docx / .pdf</strong>（每个≤200MB，可上传多个）。系统将逐文件抽取事实并合并预填表单；<strong>不会</strong>自动生成法律结论。
        </p>
        <div class="doc-upload-row">
          <label class="btn-secondary file-upload-btn">
            {{ extracting ? '抽取中…' : pendingFiles.length ? '继续添加文件' : '选择方案文件' }}
            <input
              type="file"
              multiple
              accept=".txt,.md,.docx,.pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf"
              :disabled="extracting"
              hidden
              @change="onDocumentSelected"
            />
          </label>
          <span class="muted" v-if="extractResult && !extracting">
            已解析 {{ pendingFiles.length }} 个文件 · {{ extractModeLabel }}
          </span>
          <span class="muted" v-else-if="extracting">正在抽取…</span>
        </div>
        <ul v-if="pendingFiles.length" class="upload-file-list">
          <li v-for="(file, idx) in pendingFiles" :key="`${file.name}-${file.size}`">
            <span>{{ file.name }}</span>
            <span class="muted">{{ (file.size / 1024).toFixed(0) }} KB</span>
            <span v-if="extractResult && !extracting" class="badge ok sm">已解析</span>
            <button
              type="button"
              class="btn-link sm"
              :disabled="extracting"
              @click="removePendingFile(idx)"
            >
              移除
            </button>
          </li>
        </ul>
        <p v-if="extractFailedNotes.length" class="warn-note">
          部分文件抽取失败已跳过：{{ extractFailedNotes.join('；') }}
        </p>
        <p v-if="extractConflicts.length" class="warn-note conflict-upload-note">
          检测到 <strong>{{ extractConflicts.length }}</strong> 项多文件字段冲突（{{
            extractConflicts.map((c) => c.label).join('、')
          }}）。打开核对表后将标黄提示，请确认合并结果后再提交。
        </p>
        <p
          v-if="auth.isBusiness && !editMode && !extractResult && !extracting"
          class="muted upload-entry-hint"
        >
          可继续添加文件；全部上传完成后点击「确认并核对」进入材料修改。
        </p>
      </div>

      <div
        class="form-section form-details-section"
        v-if="!auth.isBusiness && showInlineMaterialForm"
      >
        <h2>场景路由</h2>
        <p class="muted section-hint">结构化场景参数，用于选择协查规则包与默认法域（巴西首发）。</p>
        <div class="form-grid">
          <label>
            <span>国家</span>
            <input v-model="form.country" readonly />
          </label>
          <label>
            <span>州</span>
            <input v-model="form.state" readonly />
          </label>
          <label>
            <span>城市</span>
            <input v-model="form.city" readonly />
          </label>
          <label>
            <span>行业</span>
            <select v-model="form.industry">
              <option v-for="ind in catalog?.industries || []" :key="ind.id" :value="ind.id">
                {{ ind.name }}
              </option>
            </select>
          </label>
          <label>
            <span>动作类型</span>
            <select v-model="form.action_type">
              <option v-for="act in catalog?.action_types || []" :key="act.id" :value="act.id">
                {{ act.name }}
              </option>
            </select>
          </label>
        </div>
      </div>

      <MaterialFieldSections
        v-if="showInlineMaterialForm && !auth.isBusiness"
        v-model="form"
        :catalog="catalog"
        :fields="activeReviewFields"
        :is-business="auth.isBusiness"
        :required-mark="!auth.isBusiness"
        :highlight-label="shouldHighlightField"
        :placeholders="LEGAL_FIELD_PLACEHOLDERS"
      />

      <div class="form-section" v-if="catalog && !auth.isBusiness">
        <h2>协查范围</h2>
        <p class="muted">
          请选择本次协查需要覆盖的合规维度；系统将据此生成《专项核查清单》。
        </p>
        <div class="dimension-grid">
          <label
            v-for="dim in catalog.dimensions"
            :key="dim.id"
            class="dimension-card"
            :class="{ active: form.compliance_dimensions.includes(dim.id) }"
          >
            <input
              type="checkbox"
              :value="dim.id"
              :checked="form.compliance_dimensions.includes(dim.id)"
              @change="toggleDimension(dim.id)"
            />
            <div class="dimension-body">
              <strong>{{ dim.name }}</strong>
              <span class="dim-pt">{{ dim.name_pt }}</span>
              <p>{{ dim.description }}</p>
            </div>
          </label>
        </div>
      </div>

      <div
        v-if="businessUploadOnly && extractResult && !extracting"
        class="panel business-upload-summary"
      >
        <h2>已解析方案</h2>
        <p class="muted">
          共 {{ pendingFiles.length }} 个文件 · {{ extractModeLabel }}
        </p>
        <p class="muted">请确认文件已全部上传，再进入材料修改页核对抽取结果并提交。</p>
      </div>

      <p class="error" v-if="error">{{ error }}</p>

      <div class="form-actions">
        <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
        <button
          v-if="auth.isBusiness && businessUploadOnly && extractResult"
          type="button"
          class="btn-primary"
          :disabled="extracting"
          @click="goToMaterialReview"
        >
          确认并核对
        </button>
        <button
          v-else-if="auth.isBusiness && canOpenReviewModal && editMode"
          type="button"
          class="btn-primary"
          @click="openReviewModalFromForm"
        >
          打开核对表
        </button>
        <button v-else-if="!auth.isBusiness" type="submit" class="btn-primary" :disabled="submitting">
          {{ submitting ? '处理中…' : '生成专项核查清单' }}
        </button>
      </div>
    </form>

    <BusinessReviewModal
      v-if="auth.isBusiness && editMode"
      v-model:open="reviewModalOpen"
      v-model:phase="reviewModalPhase"
      v-model="form"
      v-model:hidden-field-keys="hiddenReviewFieldKeys"
      v-model:custom-fields="reviewCustomFields"
      v-model:row-order="reviewRowOrder"
      :edit-mode="editMode"
      :submitting="submitting"
      :extract-mode-label="extractModeLabel"
      :filename="extractResult?.filename ?? null"
      :disclaimer="reviewDisclaimer"
      :facts="reviewFacts"
      :per-file-results="perFileResults"
      :has-multi-file-extract="hasMultiFileExtract"
      :missing-keys="showFieldValidation ? reviewMissingKeys : []"
      :rejected-keys="rejectedFieldKeys"
      :conflict-keys="conflictFieldKeys"
      :conflicts="extractConflicts"
      :fields="activeReviewFields"
      :catalog="catalog"
      :responsibility-hint="businessResponsibilityHint"
      :error="modalError"
      @close="closeReviewModal"
      @preview="goToConfirmPreview"
      @back-to-edit="backToEditableFromConfirm"
      @submit="finalSubmitFromModal"
    />
  </div>
</template>
