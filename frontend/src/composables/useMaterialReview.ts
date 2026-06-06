import { computed, type ComputedRef, type Ref } from 'vue'
import {
  REVIEW_FIELD_LABELS,
  allReviewFieldsFromCatalog,
  collectMissingSubmitRequiredFields,
  type CustomReviewField,
} from '@/config/businessMaterialReviewFields'
import type { DocumentExtractBatchResult, DocumentExtractResult } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { applySceneDefaults } from '@/config/sceneClassification'
import type { RulesCatalog, ScenarioFormData } from '@/types/scenario'

function applyBusinessSubmitDefaults<T extends Record<string, unknown>>(
  payload: T,
  catalog: RulesCatalog | null,
): T {
  return applySceneDefaults(payload, catalog)
}

export function useMaterialReview(options: {
  form: Ref<ScenarioFormData>
  extractBatch: Ref<DocumentExtractBatchResult | null>
  pendingFiles: Ref<File[]>
  hiddenReviewFieldKeys: Ref<string[]>
  reviewCustomFields: Ref<CustomReviewField[]>
  reviewRowOrder: Ref<string[]>
  catalog: Ref<RulesCatalog | null>
  editMode: ComputedRef<boolean> | Ref<boolean>
}) {
  const auth = useAuthStore()

  const activeReviewFields = computed(() => {
    if (auth.isBusiness && !options.editMode.value) {
      return allReviewFieldsFromCatalog(options.catalog.value)
    }
    return allReviewFieldsFromCatalog(options.catalog.value)
  })

  const extractResult = computed(() => options.extractBatch.value?.merged ?? null)
  const perFileResults = computed(() => options.extractBatch.value?.files ?? [])
  const hasMultiFileExtract = computed(() => perFileResults.value.length > 1)
  const extractConflicts = computed(() => options.extractBatch.value?.conflicts ?? [])
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
      return '请核对抽取信息；确认无误后再提交材料。不构成法律意见。'
    }
    return '以下信息来自上传方案抽取或提交表单，仅供核对。'
  })

  const reviewMissingKeys = computed(() =>
    collectMissingSubmitRequiredFields(options.form.value, activeReviewFields.value, options.catalog.value),
  )

  const businessResponsibilityHint = computed(
    () => options.catalog.value?.material_intake_policy?.business_responsibility_hint as string | undefined,
  )

  function collectValidationIssues(): string[] {
    const issues: string[] = []
    if (auth.isBusiness && !options.editMode.value && !options.pendingFiles.value.length) {
      issues.push('投资方案文件')
    }
    for (const key of collectMissingSubmitRequiredFields(
      options.form.value,
      activeReviewFields.value,
      options.catalog.value,
    )) {
      const label =
        options.catalog.value?.material_fields?.find((f) => f.key === key)?.label ||
        REVIEW_FIELD_LABELS[key] ||
        key
      if (key === 'description') {
        const desc = options.form.value.description.trim()
        if (desc && desc.length < 10) {
          issues.push(`${label}（至少 10 个字，当前 ${desc.length} 字）`)
          continue
        }
      }
      issues.push(label)
    }
    return issues
  }

  async function buildPayload() {
    const form = options.form.value
    const base = {
      ...form,
      project_name: form.project_name.trim(),
      description: form.description.trim(),
      investment_destination: form.investment_destination?.trim() || null,
      investment_structure: form.investment_structure?.trim() || null,
      funding_source: form.funding_source?.trim() || null,
      project_content_scale: form.project_content_scale?.trim() || null,
      known_risks: form.known_risks?.trim() || null,
      capacity_notes: form.capacity_notes?.trim() || null,
      facility_notes: form.facility_notes?.trim() || null,
      remarks: form.remarks?.trim() || null,
      employee_count: form.employee_count || null,
      board_date: form.board_date || null,
      start_date: form.start_date || null,
      production_date: form.production_date || null,
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
      const customFieldSnapshot = options.reviewCustomFields.value
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
          hidden_field_keys: [...options.hiddenReviewFieldKeys.value],
          custom_fields: customFieldSnapshot,
          field_display_order: [...options.reviewRowOrder.value],
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
        hidden_field_keys: [...options.hiddenReviewFieldKeys.value],
        custom_fields: customFieldSnapshot,
        field_display_order: [...options.reviewRowOrder.value],
      }
    }

    const { compliance_dimensions: _dims, ...businessBase } = base as typeof base & {
      compliance_dimensions?: string[]
    }
    const withDefaults = applyBusinessSubmitDefaults(businessBase, options.catalog.value)
    return {
      ...withDefaults,
      document_extract: buildDocumentExtractSnapshot(withDefaults),
    }
  }

  return {
    activeReviewFields,
    extractResult,
    perFileResults,
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
  }
}

export type MaterialReviewContext = ReturnType<typeof useMaterialReview>
