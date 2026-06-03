<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { confirmScenarioScope, fetchRulesCatalog, fetchScenario } from '@/api/client'
import type { DimensionInfo, RulesCatalog, Scenario } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const scenario = ref<Scenario | null>(null)
const catalog = ref<RulesCatalog | null>(null)
const selected = ref<string[]>([])
const loading = ref(true)
const submitting = ref(false)
const error = ref<string | null>(null)

const suggestedDimensions = computed(() => {
  const fromExtract = scenario.value?.document_extract?.compliance_dimensions || []
  return fromExtract.filter((id) => catalog.value?.dimensions.some((d) => d.id === id))
})

const canConfirm = computed(() => selected.value.length > 0 && !submitting.value)

onMounted(async () => {
  try {
    const id = Number(route.params.id)
    const [sc, cat] = await Promise.all([fetchScenario(id), fetchRulesCatalog()])
    scenario.value = sc
    catalog.value = cat
    if (sc.status !== 'pending_scope') {
      error.value = '该项目已确认协查范围或不在待确认状态'
      return
    }
    if (suggestedDimensions.value.length) {
      selected.value = [...suggestedDimensions.value]
    } else if (cat.dimensions.length) {
      selected.value = cat.dimensions.map((d: DimensionInfo) => d.id)
    }
  } catch {
    error.value = '无法加载项目，请返回工作台重试'
  } finally {
    loading.value = false
  }
})

function toggleDimension(id: string) {
  const set = new Set(selected.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  selected.value = [...set]
}

async function confirmScope() {
  if (!scenario.value || !canConfirm.value) return
  submitting.value = true
  error.value = null
  try {
    const updated = await confirmScenarioScope(scenario.value.id, selected.value, false)
    await router.push({ name: 'review', params: { id: updated.id } })
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
</script>

<template>
  <div class="scope-page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error && !scenario" class="error banner-error">{{ error }}</div>
    <template v-else-if="scenario && catalog">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">法务协查 · 范围确认</p>
          <h1>{{ scenario.project_name }}</h1>
          <p class="muted">
            业务已提交项目材料。请根据投资场景<strong>选择必要的合规审查维度</strong>，确认后将自动生成核查清单、法条绑定与双语简报。
          </p>
        </div>
        <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
      </header>

      <section class="panel">
        <h2>业务材料摘要</h2>
        <dl class="extract-summary">
          <div v-if="scenario.investment_structure">
            <dt>投资结构</dt>
            <dd>{{ scenario.investment_structure }}</dd>
          </div>
          <div v-if="scenario.employee_count">
            <dt>雇员规模</dt>
            <dd>{{ scenario.employee_count }} 人</dd>
          </div>
          <div>
            <dt>业务描述</dt>
            <dd>{{ scenario.description }}</dd>
          </div>
          <div v-if="scenario.capacity_notes">
            <dt>产能说明</dt>
            <dd>{{ scenario.capacity_notes }}</dd>
          </div>
          <div v-if="scenario.facility_notes">
            <dt>厂房说明</dt>
            <dd>{{ scenario.facility_notes }}</dd>
          </div>
        </dl>
        <RouterLink :to="`/scenarios/${scenario.id}/extract`" class="btn-secondary link-btn sm">
          查看 AI 抽取表
        </RouterLink>
      </section>

      <section class="panel">
        <h2>协查范围</h2>
        <p class="muted" v-if="suggestedDimensions.length">
          AI 从方案中识别到可能相关的维度（仅供参考）：{{ suggestedDimensions.map((id) => catalog.dimensions.find((d) => d.id === id)?.name).filter(Boolean).join('、') }}
        </p>
        <p class="muted" v-else>
          请勾选本次协查需要覆盖的合规维度；未选中的维度不会进入核查清单。
        </p>
        <div class="dimension-grid">
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
        <p class="error" v-if="error">{{ error }}</p>
        <div class="form-actions">
          <button type="button" class="btn-primary" :disabled="!canConfirm" @click="confirmScope">
            {{ submitting ? '生成中…' : `确认范围并生成清单（${selected.length} 个维度）` }}
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
