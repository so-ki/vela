import type { ScenarioFormData, RulesCatalog } from '@/types/scenario'

/** 核对表字段类型；后续增删改字段优先维护规则库 catalog，此处为离线回退 */
export type ReviewFieldType = 'text' | 'number' | 'textarea' | 'date'

export type ReviewFieldKey = keyof Pick<
  ScenarioFormData,
  | 'project_name'
  | 'investment_destination'
  | 'investment_structure'
  | 'funding_source'
  | 'project_content_scale'
  | 'description'
  | 'known_risks'
  | 'board_date'
  | 'start_date'
  | 'production_date'
>

export interface UiGroupDef {
  id: string
  label: string
  hint?: string
  order?: number
}

export interface ReviewFieldDef {
  key: ReviewFieldKey
  label: string
  type: ReviewFieldType
  section: 'core' | 'timeline'
  ui_group?: string
  required?: boolean
  userConfirm?: boolean
  businessOptional?: boolean
  minLength?: number
  rows?: number
}

export interface CatalogMaterialField {
  key: string
  label: string
  type: ReviewFieldType
  section: 'core' | 'timeline'
  ui_group?: string
  always_required?: boolean
  min_length?: number
  rows?: number
  policies?: { user_confirm?: boolean; business_optional?: boolean }
}

export type CustomReviewFieldLayout = 'standalone' | 'merged' | 'section'

export interface CustomReviewField {
  id: string
  label: string
  value: string
  layout: CustomReviewFieldLayout
  /** @deprecated 保留兼容；新建合并字段请用 mergeTargetLabel */
  mergeTargetKey?: string
  mergeTargetLabel?: string
}

export function isStandaloneCustomField(field: CustomReviewField): boolean {
  return (field.layout ?? 'standalone') === 'standalone'
}

export function isSectionCustomField(field: CustomReviewField): boolean {
  return field.layout === 'section'
}

export function isMergedCustomField(field: CustomReviewField): boolean {
  return field.layout === 'merged' && Boolean(field.mergeTargetLabel || field.mergeTargetKey)
}

export function isRowOrderedCustomField(field: CustomReviewField): boolean {
  return isStandaloneCustomField(field) || isSectionCustomField(field)
}

export function normalizeFieldLabelForMatch(label: string): string {
  return label.trim().replace(/（可选）/g, '').replace(/\s+/g, '').toLowerCase()
}

export function mergedCustomFieldsForTarget(
  fields: CustomReviewField[],
  targetKey: string,
  targetLabel?: string,
): CustomReviewField[] {
  const normalizedLabel = normalizeFieldLabelForMatch(targetLabel || '')
  return fields.filter((field) => {
    if (!isMergedCustomField(field)) return false
    const manualTarget = normalizeFieldLabelForMatch(field.mergeTargetLabel || field.mergeTargetKey || '')
    if (manualTarget && normalizedLabel && manualTarget === normalizedLabel) return true
    if (field.mergeTargetKey && field.mergeTargetKey === targetKey) return true
    if (manualTarget && manualTarget === normalizeFieldLabelForMatch(targetKey)) return true
    return false
  })
}

export interface MaterialUiSection {
  id: string
  label: string
  hint?: string
  fields: ReviewFieldDef[]
}

export const DEFAULT_UI_GROUPS: UiGroupDef[] = [
  { id: 'project', label: '项目信息', order: 1 },
  { id: 'narrative', label: '业务描述与风险', order: 2 },
  { id: 'timeline', label: '关键时间线', order: 3 },
]

/** 当前默认核对表字段（规则库不可用时的回退） */
export const BUSINESS_MATERIAL_REVIEW_FIELDS: ReviewFieldDef[] = [
  { key: 'project_name', label: '项目名称', type: 'text', section: 'core', ui_group: 'project', required: true, minLength: 1 },
  { key: 'investment_destination', label: '投资目的地', type: 'text', section: 'core', ui_group: 'project', minLength: 2 },
  { key: 'investment_structure', label: '投资结构', type: 'text', section: 'core', ui_group: 'project', required: true, userConfirm: true, minLength: 2 },
  { key: 'funding_source', label: '资金来源', type: 'textarea', section: 'core', ui_group: 'project', userConfirm: true, rows: 2, minLength: 2 },
  { key: 'project_content_scale', label: '主要内容', type: 'textarea', section: 'core', ui_group: 'project', rows: 2, minLength: 5 },
  { key: 'description', label: '业务描述', type: 'textarea', section: 'core', ui_group: 'narrative', rows: 6, required: true, userConfirm: true, minLength: 10 },
  { key: 'known_risks', label: '已知风险与关注事项', type: 'textarea', section: 'core', ui_group: 'narrative', userConfirm: true, rows: 3 },
  { key: 'board_date', label: '董事会日期', type: 'date', section: 'timeline', ui_group: 'timeline' },
  { key: 'start_date', label: '预计开工', type: 'date', section: 'timeline', ui_group: 'timeline' },
  { key: 'production_date', label: '预计投产', type: 'date', section: 'timeline', ui_group: 'timeline' },
]

export const BUSINESS_MATERIAL_CORE_FIELDS = BUSINESS_MATERIAL_REVIEW_FIELDS.filter((f) => f.section === 'core')
export const BUSINESS_MATERIAL_TIMELINE_FIELDS = BUSINESS_MATERIAL_REVIEW_FIELDS.filter((f) => f.section === 'timeline')

export const REVIEW_FIELD_LABELS: Record<string, string> = Object.fromEntries(
  BUSINESS_MATERIAL_REVIEW_FIELDS.map((f) => [f.key, f.label]),
)

function mapCatalogField(field: CatalogMaterialField, catalog: RulesCatalog | null): ReviewFieldDef | null {
  if (!field.key) return null
  const userConfirmKeys = new Set(catalog?.material_intake_policy?.user_confirm_fields || [])
  return {
    key: field.key as ReviewFieldKey,
    label: field.label,
    type: field.type,
    section: field.section,
    ui_group: normalizeFieldUiGroup(field.ui_group),
    required: Boolean(field.always_required),
    userConfirm: Boolean(field.policies?.user_confirm || userConfirmKeys.has(field.key)),
    businessOptional: Boolean(field.policies?.business_optional),
    minLength: field.min_length,
    rows: field.rows,
  }
}

export function submitAlwaysRequiredKeys(catalog: RulesCatalog | null): string[] {
  const fromPolicy = catalog?.material_intake_policy?.submit_always_required
  if (fromPolicy?.length) return [...fromPolicy]
  return BUSINESS_MATERIAL_REVIEW_FIELDS.filter((f) => f.required).map((f) => f.key)
}

export function userConfirmFieldKeys(catalog: RulesCatalog | null): string[] {
  const fromPolicy = catalog?.material_intake_policy?.user_confirm_fields
  if (fromPolicy?.length) return [...fromPolicy]
  return BUSINESS_MATERIAL_REVIEW_FIELDS.filter((f) => f.userConfirm).map((f) => f.key)
}

/** 已废弃：运营/规模字段并入「项目信息」可选区，不再单独成组 */
const DEPRECATED_UI_GROUP_IDS = new Set(['operations'])

export function normalizeFieldUiGroup(uiGroup?: string): string {
  if (!uiGroup || DEPRECATED_UI_GROUP_IDS.has(uiGroup)) return 'project'
  return uiGroup
}

export function uiGroupsFromCatalog(catalog: RulesCatalog | null): UiGroupDef[] {
  const fromCatalog = catalog?.ui_groups?.length ? catalog.ui_groups : []
  const source = fromCatalog.length ? fromCatalog : DEFAULT_UI_GROUPS
  return [...source]
    .filter((g) => !DEPRECATED_UI_GROUP_IDS.has(g.id))
    .sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
}

export function allReviewFieldsFromCatalog(catalog: RulesCatalog | null): ReviewFieldDef[] {
  const fromCatalog = catalog?.material_fields?.length
    ? (catalog.material_fields as CatalogMaterialField[])
        .map((field) => mapCatalogField(field, catalog))
        .filter((f): f is ReviewFieldDef => f !== null)
    : []
  return fromCatalog.length ? fromCatalog : BUSINESS_MATERIAL_REVIEW_FIELDS
}

export function fieldsGroupedByUiGroup(
  fields: ReviewFieldDef[],
  catalog: RulesCatalog | null,
): MaterialUiSection[] {
  const groups = uiGroupsFromCatalog(catalog)
  const sections: MaterialUiSection[] = []

  for (const group of groups) {
    const groupFields = fields.filter((f) => normalizeFieldUiGroup(f.ui_group || 'project') === group.id)
    if (groupFields.length) {
      sections.push({
        id: group.id,
        label: group.label,
        hint: group.hint,
        fields: groupFields,
      })
    }
  }

  const groupedKeys = new Set(sections.flatMap((s) => s.fields.map((f) => f.key)))
  const orphans = fields.filter((f) => !groupedKeys.has(f.key))
  if (orphans.length) {
    sections.push({
      id: 'other',
      label: '其他信息',
      fields: orphans,
    })
  }

  return sections
}

export function isOptionalReviewField(_field: ReviewFieldDef): boolean {
  return false
}

/** 核对表是否展示该字段 */
export function shouldShowReviewField(
  field: ReviewFieldDef,
  form: ScenarioFormData,
  catalog: RulesCatalog | null,
  options?: {
    hiddenFieldKeys?: Iterable<string>
    includeEmptyRequired?: boolean
  },
): boolean {
  const hidden = new Set(options?.hiddenFieldKeys ?? [])
  if (hidden.has(field.key)) return false

  const requiredKeys = new Set(submitAlwaysRequiredKeys(catalog))
  const includeEmptyRequired = options?.includeEmptyRequired ?? true
  if (includeEmptyRequired && requiredKeys.has(field.key)) return true
  return !isReviewFieldEmpty(field.key, form[field.key as ReviewFieldKey], field)
}

/** 仅展示有抽取/填写内容的字段；必填项始终保留 */
export function filterSectionsByExtractedData(
  sections: MaterialUiSection[],
  form: ScenarioFormData,
  catalog: RulesCatalog | null,
  options?: {
    hiddenFieldKeys?: Iterable<string>
    includeEmptyRequired?: boolean
  },
): MaterialUiSection[] {
  return sections
    .map((section) => ({
      ...section,
      fields: section.fields.filter((field) => shouldShowReviewField(field, form, catalog, options)),
    }))
    .filter((section) => section.fields.length > 0)
}

export function canDeleteReviewField(key: string, catalog: RulesCatalog | null): boolean {
  return !submitAlwaysRequiredKeys(catalog).includes(key)
}

export function standardRowOrderId(key: string): string {
  return `standard:${key}`
}

export function customRowOrderId(id: string): string {
  return `custom:${id}`
}

export function buildDefaultRowOrder(
  sections: MaterialUiSection[],
  customFields: CustomReviewField[],
): string[] {
  const order: string[] = []
  for (const section of sections) {
    for (const field of section.fields) {
      order.push(standardRowOrderId(field.key))
    }
  }
  for (const field of customFields) {
    if (isRowOrderedCustomField(field)) {
      order.push(customRowOrderId(field.id))
    }
  }
  return order
}

export function normalizeRowOrder(
  order: string[],
  sections: MaterialUiSection[],
  customFields: CustomReviewField[],
  options?: { hiddenFieldKeys?: Iterable<string>; includeEmptyCustom?: boolean },
): string[] {
  const hidden = new Set(options?.hiddenFieldKeys ?? [])
  const includeEmptyCustom = options?.includeEmptyCustom ?? false
  const valid = new Set<string>()

  for (const section of sections) {
    for (const field of section.fields) {
      if (!hidden.has(field.key)) {
        valid.add(standardRowOrderId(field.key))
      }
    }
  }
  for (const field of customFields) {
    if (isSectionCustomField(field)) {
      if (includeEmptyCustom || field.label.trim()) {
        valid.add(customRowOrderId(field.id))
      }
      continue
    }
    if (!isStandaloneCustomField(field)) continue
    if (includeEmptyCustom || field.label.trim() || field.value.trim()) {
      valid.add(customRowOrderId(field.id))
    }
  }

  const kept: string[] = []
  for (const rowId of order) {
    if (valid.has(rowId) && !kept.includes(rowId)) kept.push(rowId)
  }
  for (const rowId of valid) {
    if (!kept.includes(rowId)) kept.push(rowId)
  }
  return kept
}

export type ReviewDisplayItem =
  | { type: 'section'; id: string; label: string; customSectionId?: string }
  | { type: 'standard'; key: ReviewFieldKey; field: ReviewFieldDef }
  | { type: 'custom'; field: CustomReviewField }

export function buildReviewDisplayItems(
  rowOrder: string[],
  sections: MaterialUiSection[],
  customFields: CustomReviewField[],
  catalog: RulesCatalog | null,
): ReviewDisplayItem[] {
  const fieldByKey = new Map<string, ReviewFieldDef>()
  for (const section of sections) {
    for (const field of section.fields) {
      fieldByKey.set(field.key, field)
    }
  }
  const customById = new Map(customFields.map((field) => [field.id, field]))
  const groupLabels = Object.fromEntries(uiGroupsFromCatalog(catalog).map((group) => [group.id, group.label]))

  const items: ReviewDisplayItem[] = []
  let lastStandardGroup: string | null = null

  for (const rowId of rowOrder) {
    if (rowId.startsWith('standard:')) {
      const key = rowId.slice('standard:'.length)
      const field = fieldByKey.get(key)
      if (!field) continue
      const groupId = normalizeFieldUiGroup(field.ui_group)
      if (groupId !== lastStandardGroup) {
        items.push({
          type: 'section',
          id: groupId,
          label: groupLabels[groupId] || groupId,
        })
        lastStandardGroup = groupId
      }
      items.push({ type: 'standard', key: key as ReviewFieldKey, field })
      continue
    }

    if (rowId.startsWith('custom:')) {
      const id = rowId.slice('custom:'.length)
      const field = customById.get(id)
      if (!field) continue
      if (isSectionCustomField(field)) {
        items.push({
          type: 'section',
          id: `custom-section:${id}`,
          label: field.label,
          customSectionId: id,
        })
        lastStandardGroup = null
        continue
      }
      if (!isStandaloneCustomField(field)) continue
      items.push({ type: 'custom', field })
    }
  }

  return items
}

export function moveRowOrder(order: string[], fromRowId: string, toRowId: string): string[] {
  if (fromRowId === toRowId) return order
  const next = order.filter((rowId) => rowId !== fromRowId)
  const targetIndex = next.indexOf(toRowId)
  if (targetIndex === -1) {
    next.push(fromRowId)
    return next
  }
  next.splice(targetIndex, 0, fromRowId)
  return next
}

export function uiGroupLabelForField(key: string, catalog: RulesCatalog | null): string {
  const field = allReviewFieldsFromCatalog(catalog).find((f) => f.key === key)
  if (!field?.ui_group) return ''
  return uiGroupsFromCatalog(catalog).find((g) => g.id === field.ui_group)?.label || ''
}

/** 法务确认维度后，业务端仅展示该维度相关字段（含 always_required） */
export function reviewFieldsForDimensions(
  catalog: RulesCatalog | null,
  activeDimensions: string[] | null | undefined,
): ReviewFieldDef[] {
  const allFields = allReviewFieldsFromCatalog(catalog)
  if (!activeDimensions?.length) return allFields

  const dimReqs = catalog?.dimension_field_requirements || {}
  const keys = new Set<string>()
  for (const dim of activeDimensions) {
    for (const key of dimReqs[dim] || []) keys.add(key)
  }
  for (const field of catalog?.material_fields || []) {
    if (field.always_required && field.key) keys.add(field.key)
  }
  for (const field of allFields) {
    if (field.required) keys.add(field.key)
  }

  return allFields.filter((field) => keys.has(field.key))
}

export function isReviewFieldEmpty(key: string, value: unknown, field?: ReviewFieldDef): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return true
    if (field?.minLength && trimmed.length < field.minLength) return true
  }
  return false
}

/** 业务提交时：仅校验 submit_always_required（不含 Gate A 维度字段） */
export function collectMissingSubmitRequiredFields(
  form: ScenarioFormData,
  fields: ReviewFieldDef[],
  catalog: RulesCatalog | null,
): string[] {
  const requiredKeys = new Set(submitAlwaysRequiredKeys(catalog))
  const missing: string[] = []
  for (const field of fields) {
    if (!requiredKeys.has(field.key)) continue
    if (isReviewFieldEmpty(field.key, form[field.key], field)) {
      missing.push(field.key)
    }
  }
  return missing
}

/** @deprecated 使用 collectMissingSubmitRequiredFields；保留供 Gate A 等场景 */
export function collectMissingReviewFields(
  form: ScenarioFormData,
  fields: ReviewFieldDef[],
  catalog?: RulesCatalog | null,
): string[] {
  return collectMissingSubmitRequiredFields(form, fields, catalog ?? null)
}

export function buildReviewFieldLabels(catalog: RulesCatalog | null): Record<string, string> {
  return Object.fromEntries(allReviewFieldsFromCatalog(catalog).map((f) => [f.key, f.label]))
}
