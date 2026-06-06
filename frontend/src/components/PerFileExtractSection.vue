<script setup lang="ts">
import { computed } from 'vue'
import BusinessMaterialReviewTable from '@/components/BusinessMaterialReviewTable.vue'
import type { DocumentExtractResult } from '@/api/client'
import type { ScenarioFormData } from '@/types/scenario'

const props = defineProps<{
  index: number
  result: DocumentExtractResult
}>()

const modeLabel = computed(() => (props.result.mode === 'llm' ? 'AI 抽取' : '规则抽取'))

const displayForm = computed<ScenarioFormData>(() => ({
  project_name: props.result.project_name || '',
  country: '',
  state: '',
  city: '',
  industry: '',
  action_type: '',
  investment_destination: props.result.investment_destination || '',
  investment_structure: props.result.investment_structure || '',
  funding_source: props.result.funding_source || '',
  project_content_scale: props.result.project_content_scale || '',
  description: [
    props.result.description,
    props.result.remarks?.trim(),
  ]
    .filter((part): part is string => Boolean(part?.trim()))
    .join(''),
  known_risks: props.result.known_risks || '',
  employee_count: props.result.employee_count ?? undefined,
  capacity_notes: props.result.capacity_notes || '',
  facility_notes: props.result.facility_notes || '',
  compliance_dimensions: props.result.compliance_dimensions || [],
  board_date: props.result.board_date || '',
  start_date: props.result.start_date || '',
  production_date: props.result.production_date || '',
  remarks: '',
}))
</script>

<template>
  <section class="panel per-file-extract-section">
    <div class="extract-table-head">
      <h3>文件 {{ index + 1 }}：{{ result.filename }}</h3>
      <p class="muted extract-table-meta">
        <span class="badge ok">{{ modeLabel }}</span>
        <span v-if="result.llm_skipped">· {{ result.llm_skipped }}</span>
      </p>
    </div>
    <BusinessMaterialReviewTable
      :model-value="displayForm"
      :editable="false"
      :dynamic-visibility="true"
      :mode-label="modeLabel"
      :filename="result.filename"
      :disclaimer="result.disclaimer"
      :facts="result.facts"
    />
  </section>
</template>
