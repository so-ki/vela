<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { createDemoScenario, createScenario, extractDocumentFromFile, fetchDemoTemplate, fetchRulesCatalog, fetchScenario, generateAndSubmitDemo, reviseAndResubmitScenario, submitMaterialsDemo, submitMaterialsScenario } from '@/api/client'
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
const extractPreviewEl = ref<HTMLElement | null>(null)
const showFormDetails = ref(false)

const FIELD_LABELS: Record<string, string> = {
  project_name: '项目名称',
  description: '业务描述',
  investment_structure: '投资结构',
  employee_count: '雇员规模',
  capacity_notes: '产能说明',
  facility_notes: '厂房说明',
  remarks: '备注',
}

const validationIssues = computed(() => collectValidationIssues())

const canConfirmSubmit = computed(() => validationIssues.value.length === 0 && !submitting.value)

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
        compliance_dimensions: [],
        board_date: scenario.board_date || '',
        start_date: scenario.start_date || '',
        production_date: scenario.production_date || '',
        remarks: scenario.remarks || '',
      }
      return
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
    investment_structure: form.value.investment_structure?.trim() || null,
    capacity_notes: form.value.capacity_notes?.trim() || null,
    facility_notes: form.value.facility_notes?.trim() || null,
    remarks: form.value.remarks?.trim() || null,
    employee_count: form.value.employee_count || null,
    board_date: form.value.board_date || null,
    start_date: form.value.start_date || null,
    production_date: form.value.production_date || null,
  }
  if (auth.isBusiness) {
    const { compliance_dimensions: _dims, ...businessBase } = base as typeof base & { compliance_dimensions?: string[] }
    if (extractResult.value) {
      return {
        ...businessBase,
        document_extract: {
          filename: extractResult.value.filename,
          mode: extractResult.value.mode,
          source: 'upload',
          project_name: extractResult.value.project_name ?? businessBase.project_name,
          investment_structure: extractResult.value.investment_structure ?? businessBase.investment_structure,
          description: extractResult.value.description ?? businessBase.description,
          employee_count: extractResult.value.employee_count ?? businessBase.employee_count,
          capacity_notes: extractResult.value.capacity_notes ?? businessBase.capacity_notes,
          facility_notes: extractResult.value.facility_notes ?? businessBase.facility_notes,
          remarks: extractResult.value.remarks ?? businessBase.remarks,
          compliance_dimensions: extractResult.value.compliance_dimensions || [],
          facts: extractResult.value.facts,
          disclaimer: extractResult.value.disclaimer,
          llm_skipped: extractResult.value.llm_skipped ?? null,
        },
      }
    }
    return {
      ...businessBase,
      document_extract: {
        filename: '（手动填写）',
        mode: 'manual',
        source: 'manual',
        project_name: businessBase.project_name,
        investment_structure: businessBase.investment_structure,
        description: businessBase.description,
        employee_count: businessBase.employee_count,
        capacity_notes: businessBase.capacity_notes,
        facility_notes: businessBase.facility_notes,
        remarks: businessBase.remarks,
        compliance_dimensions: [],
        facts: [
          { field: 'project_name', value: businessBase.project_name, source_snippet: null },
          { field: 'description', value: businessBase.description, source_snippet: null },
        ],
        disclaimer: '业务侧手动填写提交，未上传方案文件；协查范围由法务确认。',
      },
    }
  }
  ensureAllDimensions()
  if (extractResult.value) {
    return {
      ...base,
      compliance_dimensions: form.value.compliance_dimensions,
      document_extract: {
        filename: extractResult.value.filename,
        mode: extractResult.value.mode,
        source: 'upload',
        project_name: extractResult.value.project_name ?? base.project_name,
        investment_structure: extractResult.value.investment_structure ?? base.investment_structure,
        description: extractResult.value.description ?? base.description,
        employee_count: extractResult.value.employee_count ?? base.employee_count,
        capacity_notes: extractResult.value.capacity_notes ?? base.capacity_notes,
        facility_notes: extractResult.value.facility_notes ?? base.facility_notes,
        remarks: extractResult.value.remarks ?? base.remarks,
        compliance_dimensions: extractResult.value.compliance_dimensions?.length
          ? extractResult.value.compliance_dimensions
          : base.compliance_dimensions,
        facts: extractResult.value.facts,
        disclaimer: extractResult.value.disclaimer,
        llm_skipped: extractResult.value.llm_skipped ?? null,
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
  if (!form.value.project_name.trim()) {
    issues.push(FIELD_LABELS.project_name)
  }
  const desc = form.value.description.trim()
  if (!desc) {
    issues.push(FIELD_LABELS.description)
  } else if (desc.length < 10) {
    issues.push(`${FIELD_LABELS.description}（至少 10 个字，当前 ${desc.length} 字）`)
  }
  ensureAllDimensions()
  if (!auth.isBusiness && form.value.compliance_dimensions.length === 0) {
    issues.push('协查范围（至少选择一个合规维度）')
  }
  return issues
}

function validateForm(): boolean {
  const issues = collectValidationIssues()
  if (issues.length) {
    error.value = `请补充以下信息后再提交：${issues.join('、')}`
    return false
  }
  error.value = null
  return true
}

async function submit() {
  if (!validateForm()) return
  submitting.value = true
  error.value = null
  try {
    const payload = await buildPayload()
    if (editMode.value && editScenarioId.value) {
      const scenario = await reviseAndResubmitScenario(editScenarioId.value, payload)
      await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
      return
    }
    if (auth.isBusiness) {
      const scenario = await submitMaterialsScenario(payload)
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
      const scenario = await submitMaterialsDemo()
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

function factLabel(field: string): string {
  return FIELD_LABELS[field] || field
}

function applyExtractResult(result: DocumentExtractResult) {
  if (result.project_name) form.value.project_name = result.project_name
  if (result.investment_structure) form.value.investment_structure = result.investment_structure
  if (result.description) form.value.description = result.description
  if (result.employee_count) form.value.employee_count = result.employee_count
  if (result.capacity_notes) form.value.capacity_notes = result.capacity_notes
  if (result.facility_notes) form.value.facility_notes = result.facility_notes
  if (result.remarks) form.value.remarks = result.remarks
  if (!auth.isBusiness && result.compliance_dimensions?.length) {
    form.value.compliance_dimensions = result.compliance_dimensions
  }
  if (!auth.isBusiness) ensureAllDimensions()
  showFormDetails.value = collectValidationIssues().length > 0
}

async function scrollToExtractPreview() {
  await nextTick()
  extractPreviewEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
    await scrollToExtractPreview()
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
          法务已退回本项目。请根据下方批注意见修改描述或补充说明，保存后将<strong>重新提交材料</strong>（仍是同一项目，法务将再次确认协查范围）。
        </p>
        <p class="muted" v-else-if="auth.isBusiness">
          请<strong>上传投资方案</strong>（推荐）或填写项目信息；核对后提交材料即可，<strong>协查范围由法务确认</strong>后再生成清单。
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
          {{ submitting ? '提交中…' : '演示项目一键提交材料' }}
        </button>
        <button v-else type="button" class="btn-secondary" @click="submitDemoQuick" :disabled="submitting">
          一键生成演示清单
        </button>
      </div>
    </header>

    <form class="scenario-form panel" @submit.prevent="submit">
      <p class="error banner-error" v-if="error && !catalog">{{ error }}</p>

      <div class="form-section doc-upload-section" :class="{ 'has-extract': !!extractResult }">
        <h2>{{ auth.isBusiness && !editMode ? '上传投资方案（推荐）' : '上传投资方案（可选）' }}</h2>
        <p class="muted" v-if="auth.isBusiness && !editMode">
          支持 <strong>.txt / .md / .docx / .pdf</strong>（≤2MB）。上传后 AI 抽取事实并<strong>自动展开预填预览</strong>；确认无误即可提交材料。
        </p>
        <p class="muted" v-else>
          支持 <strong>.txt / .md / .docx / .pdf</strong>（≤2MB）。系统将抽取项目名称、用工、产能等事实预填表单；<strong>不会</strong>自动生成法律结论。
        </p>
        <div class="doc-upload-row">
          <label class="btn-secondary file-upload-btn">
            {{ extracting ? '抽取中…' : '选择方案文件' }}
            <input
              type="file"
              accept=".txt,.md,.docx,.pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf"
              :disabled="extracting"
              hidden
              @change="onDocumentSelected"
            />
          </label>
          <span class="muted" v-if="extractResult">
            已解析 {{ extractResult.filename }} · {{ extractResult.mode === 'llm' ? 'AI 抽取' : '规则抽取' }}
          </span>
        </div>
        <div
          ref="extractPreviewEl"
          class="extract-preview extract-preview-expanded"
          v-if="extractResult"
        >
          <div class="extract-preview-head">
            <h3>AI 预填预览</h3>
            <span class="badge ok">{{ extractResult.mode === 'llm' ? 'AI 抽取' : '规则抽取' }}</span>
          </div>
          <p class="muted">{{ extractResult.disclaimer }}</p>

          <dl class="extract-summary">
            <div v-if="form.project_name">
              <dt>项目名称</dt>
              <dd>{{ form.project_name }}</dd>
            </div>
            <div v-if="form.investment_structure">
              <dt>投资结构</dt>
              <dd>{{ form.investment_structure }}</dd>
            </div>
            <div v-if="form.employee_count">
              <dt>雇员规模</dt>
              <dd>{{ form.employee_count }} 人</dd>
            </div>
            <div v-if="form.description">
              <dt>业务描述</dt>
              <dd>{{ form.description.length > 120 ? form.description.slice(0, 120) + '…' : form.description }}</dd>
            </div>
          </dl>

          <ul class="extract-facts" v-if="extractResult.facts.length">
            <li v-for="(fact, idx) in extractResult.facts.slice(0, 8)" :key="idx">
              <strong>{{ factLabel(fact.field) }}</strong>：{{ fact.value }}
              <span class="muted" v-if="fact.source_snippet">（{{ fact.source_snippet }}）</span>
            </li>
          </ul>

          <div v-if="validationIssues.length" class="validation-missing panel-inner">
            <strong>尚无法提交，请补充：</strong>
            <ul>
              <li v-for="issue in validationIssues" :key="issue">{{ issue }}</li>
            </ul>
            <button type="button" class="btn-secondary sm" @click="showFormDetails = true">
              展开表单补全
            </button>
          </div>

          <div class="extract-confirm-actions" v-if="auth.isBusiness || editMode">
            <button
              type="button"
              class="btn-primary"
              :disabled="!canConfirmSubmit"
              @click="submit"
            >
              {{
                submitting
                  ? '提交中…'
                    : editMode
                    ? '确认并重新提交材料'
                    : '确认无误并提交材料'
              }}
            </button>
            <button
              v-if="!showFormDetails"
              type="button"
              class="btn-secondary"
              @click="showFormDetails = true"
            >
              展开表单核对
            </button>
          </div>
          <p class="muted warn-text" v-else>提交前请核对预填内容，尤其是数字与地点。</p>
        </div>
      </div>

      <div
        class="form-section form-details-section"
        v-show="!auth.isBusiness || editMode || showFormDetails || !extractResult"
      >
        <h2>基本信息</h2>
        <div class="form-grid">
          <label :class="{ 'field-missing': validationIssues.some((i) => i.startsWith('项目名称')) }">
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
        <label :class="{ 'field-missing': validationIssues.some((i) => i.startsWith('业务描述')) }">
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
        <button
          v-if="auth.isBusiness && extractResult && !showFormDetails"
          type="button"
          class="btn-secondary"
          @click="showFormDetails = true"
        >
          展开完整表单
        </button>
        <button type="submit" class="btn-primary" :disabled="submitting || (auth.isBusiness && !!extractResult && validationIssues.length > 0)">
          {{
            submitting
              ? '处理中…'
              : editMode
                ? '保存并重新提交材料'
                : auth.isBusiness
                  ? '提交项目材料'
                  : '生成专项核查清单'
          }}
        </button>
      </div>
    </form>
  </div>
</template>
