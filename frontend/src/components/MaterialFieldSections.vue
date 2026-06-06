<script setup lang="ts">
import { computed } from 'vue'
import {
  allReviewFieldsFromCatalog,
  fieldsGroupedByUiGroup,
  type ReviewFieldDef,
} from '@/config/businessMaterialReviewFields'
import type { RulesCatalog, ScenarioFormData } from '@/types/scenario'

const props = withDefaults(
  defineProps<{
    catalog?: RulesCatalog | null
    fields?: ReviewFieldDef[]
    isBusiness?: boolean
    requiredMark?: boolean
    highlightLabel?: (label: string) => boolean
    placeholders?: Record<string, string>
  }>(),
  {
    catalog: null,
    fields: undefined,
    isBusiness: true,
    requiredMark: false,
    highlightLabel: () => false,
    placeholders: () => ({}),
  },
)

const form = defineModel<ScenarioFormData>({ required: true })

const activeFields = computed(() => props.fields ?? allReviewFieldsFromCatalog(props.catalog ?? null))

const uiSections = computed(() => fieldsGroupedByUiGroup(activeFields.value, props.catalog ?? null))

function placeholderFor(field: ReviewFieldDef): string {
  if (props.isBusiness) return ''
  return props.placeholders[field.key] || ''
}

function isFullWidth(field: ReviewFieldDef): boolean {
  return field.type === 'textarea' && field.key === 'description'
}
</script>

<template>
  <div
    v-for="section in uiSections"
    :key="section.id"
    class="form-section material-ui-section"
    :class="`material-ui-section--${section.id}`"
  >
    <h2>{{ section.label }}</h2>
    <p v-if="section.hint" class="muted section-hint">{{ section.hint }}</p>

    <div
      class="form-grid"
      :class="{
        three: section.id === 'timeline',
        'narrative-grid': section.id === 'narrative',
      }"
    >
      <label
        v-for="field in section.fields"
        :key="field.key"
        :class="{
          'field-missing': highlightLabel(field.label),
          'field-full-width': isFullWidth(field),
        }"
      >
        <span>
          {{ field.label }}
          <span v-if="requiredMark && field.required" class="required-mark">*</span>
        </span>
        <input
          v-if="field.type === 'text'"
          v-model="form[field.key]"
          :required="requiredMark && field.required"
          :placeholder="placeholderFor(field)"
        />
        <input
          v-else-if="field.type === 'number'"
          v-model.number="form[field.key]"
          type="number"
          min="1"
          :placeholder="placeholderFor(field)"
        />
        <input
          v-else-if="field.type === 'date'"
          v-model="form[field.key]"
          type="date"
        />
        <textarea
          v-else
          v-model="form[field.key]"
          :required="requiredMark && field.required && field.key === 'description'"
          :rows="field.rows || 3"
          :placeholder="placeholderFor(field)"
        />
      </label>
    </div>
  </div>
</template>
