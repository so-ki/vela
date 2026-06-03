<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { fetchScenario } from '@/api/client'
import type { DocumentExtractSnapshot, Scenario } from '@/types/scenario'

const route = useRoute()
const scenario = ref<Scenario | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const FIELD_LABELS: Record<string, string> = {
  project_name: '项目名称',
  description: '业务描述',
  investment_structure: '投资结构',
  employee_count: '雇员规模',
  capacity_notes: '产能说明',
  facility_notes: '厂房说明',
  remarks: '备注',
  compliance_dimensions: '协查维度',
}

const extract = computed(() => scenario.value?.document_extract)

const formRows = computed(() => {
  const e = extract.value
  if (!e) return []
  const rows: Array<{ label: string; value: string }> = []
  const push = (key: keyof DocumentExtractSnapshot, label: string, formatter?: (v: unknown) => string) => {
    const raw = e[key]
    if (raw === null || raw === undefined || raw === '') return
    if (Array.isArray(raw)) {
      if (raw.length) rows.push({ label, value: raw.join('、') })
      return
    }
    rows.push({ label, value: formatter ? formatter(raw) : String(raw) })
  }
  push('project_name', '项目名称')
  push('investment_structure', '投资结构')
  push('employee_count', '雇员规模', (v) => `${v} 人`)
  push('capacity_notes', '产能说明')
  push('facility_notes', '厂房说明')
  push('description', '业务描述')
  push('remarks', '备注')
  return rows
})

const modeLabel = computed(() => {
  const mode = extract.value?.mode
  if (mode === 'llm') return 'AI 抽取'
  if (mode === 'rules') return '规则抽取'
  return '手动填写'
})

function factLabel(field: string) {
  return FIELD_LABELS[field] || field
}

onMounted(async () => {
  try {
    scenario.value = await fetchScenario(Number(route.params.id))
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
    <template v-else-if="scenario && extract">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">业务协查 · AI 抽取信息表</p>
          <h1>{{ scenario.project_name }}</h1>
          <p class="meta">
            <span class="badge ok">{{ modeLabel }}</span>
            <span class="muted" v-if="extract.filename">来源文件：{{ extract.filename }}</span>
            <span class="muted" v-if="extract.extracted_at">
              · 抽取于 {{ new Date(extract.extracted_at).toLocaleString('zh-CN') }}
            </span>
          </p>
        </div>
        <div class="header-actions">
          <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
          <RouterLink :to="`/scenarios/${scenario.id}/progress`" class="btn-secondary link-btn">查看进度</RouterLink>
        </div>
      </header>

      <div class="disclaimer-banner">
        {{ extract.disclaimer || '以下信息来自上传方案抽取或提交表单，仅供业务核对，不构成法律意见。' }}
      </div>

      <section class="panel extract-table-panel">
        <h2>预填字段一览</h2>
        <table class="extract-fields-table" v-if="formRows.length">
          <thead>
            <tr>
              <th>字段</th>
              <th>抽取 / 填入值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in formRows" :key="row.label">
              <th scope="row">{{ row.label }}</th>
              <td>{{ row.value }}</td>
            </tr>
          </tbody>
        </table>
        <p class="muted" v-else>暂无结构化字段。</p>
      </section>

      <section class="panel extract-table-panel" v-if="extract.facts?.length">
        <h2>抽取依据明细</h2>
        <p class="muted">每条对应方案原文片段，便于核对 AI / 规则抽取是否准确。</p>
        <table class="extract-fields-table extract-facts-table">
          <thead>
            <tr>
              <th>字段</th>
              <th>值</th>
              <th>原文依据</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(fact, idx) in extract.facts" :key="idx">
              <th scope="row">{{ factLabel(fact.field) }}</th>
              <td>{{ fact.value }}</td>
              <td class="muted">{{ fact.source_snippet || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>
