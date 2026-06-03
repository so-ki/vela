<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { createDemoScenario, createScenario, extractDocumentFromFile, fetchDemoTemplate, fetchRulesCatalog, fetchScenario, generateAndSubmitDemo, generateAndSubmitScenario, reviseAndResubmitScenario } from '@/api/client'
import type { DocumentExtractResult } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { DimensionInfo, RulesCatalog, ScenarioFormData } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const editMode = computed(() => route.name === 'scenario-edit')
const editScenarioId = computed(() => (editMode.value ? Number(route.params.id) : null))
const catalog = ref<RulesCatalog | null>(null)
const loading = ref(false)
const submitting = ref(false)
const extracting = ref(false)
const error = ref<string | null>(null)
const extractResult = ref<DocumentExtractResult | null>(null)

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
        investment_structure: scenario.investment_structure || '',
        description: scenario.description,
        employee_count: scenario.employee_count ?? undefined,
        capacity_notes: scenario.capacity_notes || '',
        facility_notes: scenario.facility_notes || '',
        compliance_dimensions: scenario.compliance_dimensions,
        board_date: scenario.board_date || '',
        start_date: scenario.start_date || '',
        production_date: scenario.production_date || '',
        remarks: scenario.remarks || '',
      }
      return
    }
    if (form.value.compliance_dimensions.length === 0 && catalog.value) {
      form.value.compliance_dimensions = catalog.value.dimensions.map((d: DimensionInfo) => d.id)
    }
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

function ensureAllDimensions() {
  if (catalog.value && form.value.compliance_dimensions.length === 0) {
    form.value.compliance_dimensions = catalog.value.dimensions.map((d: DimensionInfo) => d.id)
  }
}

async function buildPayload() {
  return {
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
}

function validateForm(): boolean {
  if (!form.value.project_name.trim()) {
    error.value = '请填写项目名称'
    return false
  }
  if (!form.value.description.trim() || form.value.description.trim().length < 10) {
    error.value = '业务描述至少需要 10 个字符，建议先点击「填入 BYD 演示模板」'
    return false
  }
  ensureAllDimensions()
  return true
}

async function submit() {
  if (!validateForm()) return
  submitting.value = true
  error.value = null
  try {
    const payload = await buildPayload()
    if (editMode.value && editScenarioId.value) {
      const scenario = await reviseAndResubmitScenario(editScenarioId.value, payload, false)
      await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
      return
    }
    if (auth.isBusiness) {
      const scenario = await generateAndSubmitScenario(payload, false)
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
    if (auth.isBusiness) {
      const scenario = await generateAndSubmitDemo(false)
      await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
      return
    }
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

function applyExtractResult(result: DocumentExtractResult) {
  if (result.project_name) form.value.project_name = result.project_name
  if (result.investment_structure) form.value.investment_structure = result.investment_structure
  if (result.description) form.value.description = result.description
  if (result.employee_count) form.value.employee_count = result.employee_count
  if (result.capacity_notes) form.value.capacity_notes = result.capacity_notes
  if (result.facility_notes) form.value.facility_notes = result.facility_notes
  if (result.remarks) form.value.remarks = result.remarks
  if (result.compliance_dimensions?.length) {
    form.value.compliance_dimensions = result.compliance_dimensions
  }
}

async function onDocumentSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  extracting.value = true
  error.value = null
  extractResult.value = null
  try {
    const result = await extractDocumentFromFile(file)
    extractResult.value = result
    applyExtractResult(result)
  } catch (e: unknown) {
    error.value = extractApiError(e)
  } finally {
    extracting.value = false
  }
}
</script>

<template>
  <div class="scenario-page">
    <header class="page-header">
      <div>
        <p class="eyebrow dark">{{ editMode ? '业务协查 · 补充材料' : auth.isBusiness ? '业务协查' : 'Step 2 · 规则库' }}</p>
        <h1>{{ editMode ? '补充项目材料' : auth.isBusiness ? '提交投资项目' : '提交协查场景' }}</h1>
        <p class="muted" v-if="editMode">
          法务已退回本项目。请根据下方批注意见修改描述或补充说明，保存后将<strong>重新生成清单并提交法务</strong>（仍是同一项目）。
        </p>
        <p class="muted" v-else-if="auth.isBusiness">
          填写项目信息后，系统将自动生成清单、检索法条、汇编简报，并<strong>直接提交法务复核</strong>。您只需跟踪进度。
        </p>
        <p class="muted" v-else>输入业务场景描述，系统将映射法律审查维度并生成《专项核查清单》。</p>
        <p class="industry-pack-note" v-if="catalog?.pack?.name">
          当前行业专包：<strong>{{ catalog.pack.name }}</strong>
          <span v-if="catalog.pack.focus"> · {{ catalog.pack.focus }}</span>
        </p>
      </div>
      <div class="header-actions" v-if="!editMode">
        <button type="button" class="btn-secondary" @click="loadDemo" :disabled="loading">填入 BYD 演示模板</button>
        <button v-if="auth.isBusiness" type="button" class="btn-secondary" @click="submitDemoQuick" :disabled="submitting">
          {{ submitting ? '提交中…' : '演示项目一键提交法务' }}
        </button>
        <button v-else type="button" class="btn-secondary" @click="submitDemoQuick" :disabled="submitting">
          一键生成演示清单
        </button>
      </div>
    </header>

    <form class="scenario-form panel" @submit.prevent="submit">
      <p class="error banner-error" v-if="error && !catalog">{{ error }}</p>

      <div class="form-section doc-upload-section">
        <h2>上传投资方案（可选）</h2>
        <p class="muted">
          支持 <strong>.txt / .md / .docx</strong>（≤2MB）。系统将抽取项目名称、用工、产能等事实预填表单；<strong>不会</strong>自动生成法律结论。
        </p>
        <div class="doc-upload-row">
          <label class="btn-secondary file-upload-btn">
            {{ extracting ? '抽取中…' : '选择方案文件' }}
            <input
              type="file"
              accept=".txt,.md,.docx,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              :disabled="extracting"
              hidden
              @change="onDocumentSelected"
            />
          </label>
          <span class="muted" v-if="extractResult">
            已解析 {{ extractResult.filename }} · {{ extractResult.mode === 'llm' ? 'AI 抽取' : '规则抽取' }}
          </span>
        </div>
        <div class="extract-preview panel-inner" v-if="extractResult">
          <p class="muted">{{ extractResult.disclaimer }}</p>
          <ul class="extract-facts" v-if="extractResult.facts.length">
            <li v-for="(fact, idx) in extractResult.facts.slice(0, 8)" :key="idx">
              <strong>{{ fact.field }}</strong>：{{ fact.value }}
              <span class="muted" v-if="fact.source_snippet">（{{ fact.source_snippet }}）</span>
            </li>
          </ul>
          <p class="muted warn-text">提交前请核对预填内容，尤其是数字与地点。</p>
        </div>
      </div>

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

      <div class="form-section" v-if="catalog">
        <h2>协查范围</h2>
        <p class="muted">
          本次提交将覆盖当前行业专包下的<strong>全部 {{ catalog.dimensions.length }} 个合规维度</strong>，无需业务侧勾选。
          维度定义与核查项由<strong>法务在规则库</strong>中维护。
        </p>
        <div class="dimension-grid dimension-grid-readonly">
          <div v-for="dim in catalog.dimensions" :key="dim.id" class="dimension-card readonly">
            <span class="dimension-check" aria-hidden="true">✓</span>
            <div class="dimension-body">
              <strong>{{ dim.name }}</strong>
              <span class="dim-pt">{{ dim.name_pt }}</span>
              <p>{{ dim.description }}</p>
            </div>
          </div>
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
          {{
            submitting
              ? '处理中…'
              : editMode
                ? '保存并重新提交法务'
                : auth.isBusiness
                  ? '生成并提交法务'
                  : '生成专项核查清单'
          }}
        </button>
      </div>
    </form>
  </div>
</template>
