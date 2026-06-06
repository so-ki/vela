<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import BusinessMaterialReviewTable from '@/components/BusinessMaterialReviewTable.vue'
import PerFileExtractSection from '@/components/PerFileExtractSection.vue'
import { fetchScenario } from '@/api/client'
import type { DocumentExtractResult } from '@/api/client'
import type { Scenario, ScenarioFormData } from '@/types/scenario'

const route = useRoute()
const scenario = ref<Scenario | null>(null)
const form = ref<ScenarioFormData>({
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
})
const loading = ref(true)
const error = ref<string | null>(null)

const extract = computed(() => scenario.value?.document_extract)

const perFileResults = computed<DocumentExtractResult[]>(() => {
  const snapshot = extract.value
  if (!snapshot?.files?.length) return []
  return snapshot.files.map((file) => ({
    filename: file.filename,
    mode: file.mode,
    project_name: file.project_name,
    investment_destination: file.investment_destination,
    investment_structure: file.investment_structure,
    funding_source: file.funding_source,
    project_content_scale: file.project_content_scale,
    description: file.description,
    known_risks: file.known_risks,
    employee_count: file.employee_count,
    capacity_notes: file.capacity_notes,
    facility_notes: file.facility_notes,
    board_date: file.board_date,
    start_date: file.start_date,
    production_date: file.production_date,
    remarks: file.remarks,
    compliance_dimensions: file.compliance_dimensions || [],
    facts: file.facts,
    disclaimer: file.disclaimer || '',
    llm_skipped: file.llm_skipped,
  }))
})

const hasMultiFileExtract = computed(() => perFileResults.value.length > 1)

const modeLabel = computed(() => {
  const mode = extract.value?.mode
  if (hasMultiFileExtract.value) return '多文件合并'
  if (mode === 'llm') return 'AI 抽取'
  if (mode === 'rules') return '规则抽取'
  return '手动填写'
})

const reviewFacts = computed(() => extract.value?.facts ?? [])

onMounted(async () => {
  try {
    const data = await fetchScenario(Number(route.params.id))
    scenario.value = data
    form.value = {
      project_name: data.project_name,
      country: data.country,
      state: data.state,
      city: data.city,
      industry: data.industry,
      action_type: data.action_type,
      investment_destination: data.investment_destination || '',
      investment_structure: data.investment_structure || '',
      funding_source: data.funding_source || '',
      project_content_scale: data.project_content_scale || '',
      description: data.description,
      known_risks: data.known_risks || '',
      employee_count: data.employee_count ?? undefined,
      capacity_notes: data.capacity_notes || '',
      facility_notes: data.facility_notes || '',
      compliance_dimensions: data.compliance_dimensions || [],
      board_date: data.board_date || '',
      start_date: data.start_date || '',
      production_date: data.production_date || '',
      remarks: data.remarks || '',
    }
  } catch {
    error.value = '无法加载抽取信息'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="extract-review-page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error banner-error">{{ error }}</div>
    <template v-else-if="scenario">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">业务协查 · AI 抽取信息表</p>
          <h1>{{ scenario.project_name }}</h1>
          <p v-if="hasMultiFileExtract" class="muted">
            共 {{ perFileResults.length }} 个方案文件 · 以下为各文件抽取结果与合并核对表
          </p>
        </div>
        <div class="header-actions">
          <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
          <RouterLink :to="`/scenarios/${scenario.id}/progress`" class="btn-secondary link-btn">查看进度</RouterLink>
        </div>
      </header>

      <section v-if="hasMultiFileExtract" class="form-section per-file-review-block">
        <h2>各文件抽取结果</h2>
        <PerFileExtractSection
          v-for="(fileResult, idx) in perFileResults"
          :key="`${fileResult.filename}-${idx}`"
          :index="idx"
          :result="fileResult"
        />
      </section>

      <section :class="{ 'merged-review-block': hasMultiFileExtract }">
        <div v-if="hasMultiFileExtract" class="extract-table-head">
          <h2>合并核对表</h2>
          <p class="muted">提交时使用的合并去重结果（只读回看）。</p>
        </div>
        <BusinessMaterialReviewTable
          v-model="form"
          :editable="false"
          :dynamic-visibility="true"
          :mode-label="modeLabel"
          :filename="extract?.filename ?? null"
          :extracted-at="extract?.extracted_at ?? null"
          :disclaimer="extract?.disclaimer || '以下信息来自上传方案抽取或提交表单，仅供业务核对，不构成法律意见。'"
          :facts="reviewFacts"
        />
      </section>
    </template>
  </div>
</template>
