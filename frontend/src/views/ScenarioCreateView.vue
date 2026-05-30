<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { createDemoScenario, createScenario, fetchDemoTemplate, fetchRulesCatalog } from '@/api/client'
import type { DimensionInfo, RulesCatalog, ScenarioFormData } from '@/types/scenario'

const router = useRouter()
const catalog = ref<RulesCatalog | null>(null)
const loading = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)

const form = ref<ScenarioFormData>({
  project_name: '',
  country: 'brazil',
  state: 'sao_paulo',
  city: 'campinas',
  industry: 'new_energy',
  action_type: 'greenfield_plant',
  investment_structure: '',
  description: '',
  employee_count: undefined,
  capacity_notes: '',
  facility_notes: '',
  compliance_dimensions: [],
  board_date: '',
  start_date: '',
  production_date: '',
  remarks: '',
})

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    catalog.value = await fetchRulesCatalog()
    if (form.value.compliance_dimensions.length === 0 && catalog.value) {
      form.value.compliance_dimensions = catalog.value.dimensions.map((d: DimensionInfo) => d.id)
    }
    // 首次进入且表单为空时自动填入演示模板，避免空表单提交 422
    if (!form.value.project_name.trim() && !form.value.description.trim()) {
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

function toggleDimension(id: string) {
  const dims = form.value.compliance_dimensions
  const idx = dims.indexOf(id)
  if (idx >= 0) {
    if (dims.length > 1) dims.splice(idx, 1)
  } else {
    dims.push(id)
  }
}

async function submit() {
  if (!form.value.project_name.trim()) {
    error.value = '请填写项目名称'
    return
  }
  if (!form.value.description.trim() || form.value.description.trim().length < 10) {
    error.value = '业务描述至少需要 10 个字符，建议先点击「填入 BYD 演示模板」'
    return
  }
  if (form.value.compliance_dimensions.length === 0) {
    error.value = '请至少选择一个合规审查维度'
    return
  }
  submitting.value = true
  error.value = null
  try {
    const payload = {
      ...form.value,
      project_name: form.value.project_name.trim(),
      description: form.value.description.trim(),
      investment_structure: form.value.investment_structure?.trim() || null,
      capacity_notes: form.value.capacity_notes?.trim() || null,
      facility_notes: form.value.facility_notes?.trim() || null,
      remarks: form.value.remarks?.trim() || null,
      employee_count: form.value.employee_count || null,
      board_date: form.value.board_date || null,
      start_date: form.value.start_date || null,
      production_date: form.value.production_date || null,
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
  return '提交失败，请检查填写内容'
}
</script>

<template>
  <div class="scenario-page">
    <header class="page-header">
      <div>
        <p class="eyebrow dark">Step 2 · 规则库</p>
        <h1>提交协查场景</h1>
        <p class="muted">输入业务场景描述，系统将映射法律审查维度并生成《专项核查清单》。</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn-secondary" @click="loadDemo" :disabled="loading">填入 BYD 演示模板</button>
        <button type="button" class="btn-secondary" @click="submitDemoQuick" :disabled="submitting">
          一键生成演示清单
        </button>
      </div>
    </header>

    <form class="scenario-form panel" @submit.prevent="submit">
      <p class="error banner-error" v-if="error && !catalog">{{ error }}</p>
      <div class="form-section">
        <h2>基本信息</h2>
        <div class="form-grid">
          <label>
            <span>项目名称</span>
            <input v-model="form.project_name" required placeholder="BYD 坎皮纳斯新能源工厂" />
          </label>
          <label>
            <span>投资结构</span>
            <input v-model="form.investment_structure" placeholder="100% 外资全资子公司" />
          </label>
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
          <label>
            <span>雇员规模</span>
            <input v-model.number="form.employee_count" type="number" min="1" placeholder="450" />
          </label>
        </div>
      </div>

      <div class="form-section">
        <h2>业务描述（中文）</h2>
        <label>
          <textarea v-model="form.description" required rows="6" placeholder="请用 3～5 句话描述投资场景…" />
        </label>
        <div class="form-grid">
          <label>
            <span>产能说明</span>
            <input v-model="form.capacity_notes" placeholder="首年 1000 台客车及电池" />
          </label>
          <label>
            <span>厂房说明</span>
            <input v-model="form.facility_notes" placeholder="32,000 m² + 20,000 m²" />
          </label>
        </div>
      </div>

      <div class="form-section">
        <h2>合规审查维度</h2>
        <div class="dimension-grid" v-if="catalog">
          <label
            v-for="dim in catalog.dimensions"
            :key="dim.id"
            class="dimension-card"
            :class="{ active: form.compliance_dimensions.includes(dim.id) }"
          >
            <input
              type="checkbox"
              :checked="form.compliance_dimensions.includes(dim.id)"
              @change="toggleDimension(dim.id)"
            />
            <div>
              <strong>{{ dim.name }}</strong>
              <span class="dim-pt">{{ dim.name_pt }}</span>
              <p>{{ dim.description }}</p>
            </div>
          </label>
        </div>
      </div>

      <div class="form-section">
        <h2>时间线</h2>
        <div class="form-grid three">
          <label>
            <span>董事会/投委会日期</span>
            <input v-model="form.board_date" type="date" />
          </label>
          <label>
            <span>预计开工</span>
            <input v-model="form.start_date" type="date" />
          </label>
          <label>
            <span>预计投产</span>
            <input v-model="form.production_date" type="date" />
          </label>
        </div>
        <label>
          <span>备注</span>
          <input v-model="form.remarks" placeholder="其他需说明事项" />
        </label>
      </div>

      <p class="error" v-if="error">{{ error }}</p>

      <div class="form-actions">
        <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
        <button type="submit" class="btn-primary" :disabled="submitting">
          {{ submitting ? '生成中…' : '生成专项核查清单' }}
        </button>
      </div>
    </form>
  </div>
</template>
