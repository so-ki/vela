<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  archiveScenario,
  createFullSample,
  deleteScenario,
  fetchLegalMonitor,
  fetchLegalStatus,
  fetchCorpusAgentStatus,
  fetchOnboardingStatus,
  fetchPlaybookDeviations,
  fetchRulesCatalog,
  fetchScenarios,
  fetchSystemStatus,
  restoreDeletedScenario,
  scanLegalMonitor,
  runCorpusMaintenanceAgent,
  ackCorpusAgentNotification,
  unarchiveScenario,
} from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import LlmSettingsPanel from '@/components/LlmSettingsPanel.vue'
import type { ScenarioSummary, RulesCatalog } from '@/types/scenario'
import type { SystemStatus } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const status = ref<SystemStatus | null>(null)
const legalStatus = ref<{ document_count?: number; mode?: string; sources_breakdown?: Record<string, number> } | null>(null)
const legalMonitor = ref<{
  alerts?: Array<{ title: string; message: string; level: string; affected_checklist_codes?: string[] }>
  last_scan_at?: string | null
  subscription_count?: number
  subscriptions?: Array<{ scenario_id: number; project_name: string; checklist_codes: string[] }>
  last_diff?: {
    has_changes?: boolean
    affected_checklist_codes?: string[]
    changed_documents?: Array<{ id: string; title_pt: string; change_type: string }>
  } | null
} | null>(null)
const playbookDeviations = ref<{
  stats?: { total?: number; top_rejected_codes?: Array<{ code: string; count: number }> }
  deviations?: Array<{ code: string; title: string; project_name: string; comment?: string }>
  rules_pack_loop?: {
    pack_id?: string
    pack_version?: string
    pack_name?: string
    workflow?: string
    suggestion_count?: number
    suggestions?: Array<{
      id: string
      code: string
      title: string
      suggestion_type: string
      priority: string
      rationale: string
      proposed_changes?: Array<Record<string, unknown>>
      sample_comments?: string[]
    }>
    export_hint?: string
  }
} | null>(null)
const rulesPackLoopOpen = ref(false)
const scanningLegal = ref(false)
const runningCorpusAgent = ref(false)
const corpusAgent = ref<{
  unread_count?: number
  last_run_at?: string | null
  interval_hours?: number
  notifications?: Array<{
    id: string
    title: string
    summary: string
    level: string
    acknowledged?: boolean
    affected_checklist_codes?: string[]
    impacted_projects?: Array<{
      scenario_id: number
      project_name: string
      material_files?: string[]
      artifacts?: Array<{ type: string; label: string; path: string }>
      suggested_actions?: string[]
    }>
  }>
} | null>(null)
const scenarios = ref<ScenarioSummary[]>([])
const rulesCatalog = ref<RulesCatalog | null>(null)
const onboardingComplete = ref(true)
const onboardingChecked = ref(false)
const loading = ref(true)
const creatingSample = ref(false)
const sampleError = ref<string | null>(null)
const archivingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const restoringId = ref<number | null>(null)
const submitPanelOpen = ref(true)
const corpusPanelOpen = ref(false)
const demoPanelOpen = ref(false)
const dimensionsPanelOpen = ref(false)
const systemPanelOpen = ref(false)
const aiSettingsPanelOpen = ref(false)
const allScenariosPanelOpen = ref(true)
const recycleBinPanelOpen = ref(false)
const scenarioGroupOpen = ref<Record<string, boolean>>({
  submitted: true,
  in_review: false,
  needs_revision: false,
  completed: false,
})
const businessScenarioGroupOpen = ref<Record<string, boolean>>({
  needs_revision: true,
  in_progress: false,
  completed: false,
})

function isLegalScenarioCompleted(s: ScenarioSummary) {
  return s.progress_status === 'finalized'
}

/** 法务需跟进的进行中项目（不含历史「处理中」半成品） */
function isLegalActiveScenario(s: ScenarioSummary) {
  return ['pending_scope', 'submitted', 'in_review', 'needs_revision'].includes(s.progress_status || '')
}

const displayedScenarios = computed(() => {
  if (auth.isLegal) return scenarios.value.filter((s) => !s.legal_deleted)
  return [...scenarios.value]
    .filter((s) => !s.business_archived)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
})

const businessRecycleBin = computed(() =>
  [...scenarios.value]
    .filter((s) => s.business_archived)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
)

const legalRecycleBin = computed(() =>
  [...scenarios.value]
    .filter((s) => s.legal_deleted)
    .sort((a, b) => {
      const ad = a.legal_deleted_at ? new Date(a.legal_deleted_at).getTime() : 0
      const bd = b.legal_deleted_at ? new Date(b.legal_deleted_at).getTime() : 0
      return bd - ad
    }),
)

const recycleBinItems = computed(() => (auth.isLegal ? legalRecycleBin.value : businessRecycleBin.value))

const priorityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 }

function sortByLegalPriority(items: ScenarioSummary[]) {
  return [...items].sort((a, b) => {
    const pa = priorityOrder[a.review_priority || 'low'] ?? 9
    const pb = priorityOrder[b.review_priority || 'low'] ?? 9
    if (pa !== pb) return pa - pb
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
}

const legalPendingReviewScenarios = computed(() => {
  const items = displayedScenarios.value.filter(
    (s) => s.progress_status === 'submitted' || s.progress_status === 'pending_scope',
  )
  return [...items].sort((a, b) => {
    const aScope = a.progress_status === 'pending_scope' ? 0 : 1
    const bScope = b.progress_status === 'pending_scope' ? 0 : 1
    if (aScope !== bScope) return aScope - bScope
    const pa = priorityOrder[a.review_priority || 'low'] ?? 9
    const pb = priorityOrder[b.review_priority || 'low'] ?? 9
    if (pa !== pb) return pa - pb
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

const legalInReviewScenarios = computed(() =>
  sortByLegalPriority(displayedScenarios.value.filter((s) => s.progress_status === 'in_review')),
)

function sortByCreatedDesc(items: ScenarioSummary[]) {
  return [...items].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
}

function isBusinessNeedsRevision(s: ScenarioSummary) {
  return !!s.needs_revision || s.progress_status === 'needs_revision'
}

function isBusinessCompleted(s: ScenarioSummary) {
  return s.progress_status === 'finalized'
}

function isBusinessInProgress(s: ScenarioSummary) {
  return !isBusinessNeedsRevision(s) && !isBusinessCompleted(s)
}

const businessNeedsRevisionScenarios = computed(() =>
  sortByCreatedDesc(displayedScenarios.value.filter(isBusinessNeedsRevision)),
)

const businessInProgressScenarios = computed(() =>
  sortByCreatedDesc(displayedScenarios.value.filter(isBusinessInProgress)),
)

const businessCompletedScenarios = computed(() =>
  sortByCreatedDesc(displayedScenarios.value.filter(isBusinessCompleted)),
)

const businessNeedsRevisionCount = computed(() => businessNeedsRevisionScenarios.value.length)

const businessInProgressCount = computed(() => businessInProgressScenarios.value.length)

const businessCompletedCount = computed(() => businessCompletedScenarios.value.length)

const businessScenarioGroups = computed(() => [
  {
    id: 'needs_revision',
    label: '待补充',
    hint: '法务已退回，请在同一项目补充材料后重新提交。',
    items: businessNeedsRevisionScenarios.value,
    badgeClass: 'err',
  },
  {
    id: 'in_progress',
    label: '进行中',
    hint: '材料已提交；待法务确认协查范围或正在复核，可查看进度与 AI 抽取结果。',
    items: businessInProgressScenarios.value,
    badgeClass: 'pri-medium',
  },
  {
    id: 'completed',
    label: '已完成',
    hint: '法务已定稿，可查看清单与简报；不需要保留的可移入回收站。',
    items: businessCompletedScenarios.value,
    badgeClass: 'ok',
  },
])

watch(
  businessScenarioGroups,
  (groups) => {
    const next = { ...businessScenarioGroupOpen.value }
    for (const group of groups) {
      if (!(group.id in next)) next[group.id] = false
    }
    businessScenarioGroupOpen.value = next
  },
  { immediate: true },
)

const legalNeedsRevisionScenarios = computed(() =>
  displayedScenarios.value.filter((s) => s.progress_status === 'needs_revision'),
)

const legalCompletedScenarios = computed(() =>
  displayedScenarios.value.filter(isLegalScenarioCompleted),
)

const legalCatalogScenarios = computed(() =>
  displayedScenarios.value.filter((s) => isLegalActiveScenario(s) || isLegalScenarioCompleted(s)),
)

const legalScenarioGroups = computed(() => [
  {
    id: 'submitted',
    label: '待复核',
    hint: '含待确认协查范围与待开始清单复核；展开后点击「复核」进入，范围/材料确认与清单复核在同一页完成。',
    items: legalPendingReviewScenarios.value,
    badgeClass: 'pri-medium',
  },
  {
    id: 'in_review',
    label: '复核中',
    hint: '法务已开始复核，尚未提交定稿；按优先级排序。',
    items: legalInReviewScenarios.value,
    badgeClass: 'pri-medium',
  },
  {
    id: 'needs_revision',
    label: '待业务补充',
    hint: '已退回业务补充材料，等待同一项目修改后重提。',
    items: legalNeedsRevisionScenarios.value,
    badgeClass: 'err',
  },
  {
    id: 'completed',
    label: '已完成',
    hint: '法务已提交定稿，可查看清单、简报与复核记录；不需要保留的可移入回收站。',
    items: legalCompletedScenarios.value,
    badgeClass: 'ok',
  },
])

watch(
  legalScenarioGroups,
  (groups) => {
    const next = { ...scenarioGroupOpen.value }
    for (const group of groups) {
      if (!(group.id in next)) next[group.id] = false
    }
    scenarioGroupOpen.value = next
  },
  { immediate: true },
)

function toggleScenarioGroup(id: string) {
  scenarioGroupOpen.value = {
    ...scenarioGroupOpen.value,
    [id]: !scenarioGroupOpen.value[id],
  }
}

function toggleBusinessScenarioGroup(id: string) {
  businessScenarioGroupOpen.value = {
    ...businessScenarioGroupOpen.value,
    [id]: !businessScenarioGroupOpen.value[id],
  }
}

function isScenarioGroupOpen(id: string) {
  return scenarioGroupOpen.value[id] ?? false
}

function isBusinessScenarioGroupOpen(id: string) {
  return businessScenarioGroupOpen.value[id] ?? false
}

function businessProgressBadgeClass(s: ScenarioSummary, groupId: string) {
  if (groupId === 'needs_revision') return 'err'
  if (groupId === 'completed') return 'ok'
  if (s.progress_status === 'in_review') return 'pri-medium'
  return 'muted-badge'
}

const legalProgressLabel: Record<string, string> = {
  pending_scope: '待确认范围',
  submitted: '待法务复核',
  in_review: '复核中',
  needs_revision: '待业务补充',
  finalized: '已定稿',
  processing: '处理中',
}

function legalProgressBadgeClass(s: ScenarioSummary) {
  if (s.progress_status === 'finalized') return 'ok'
  if (s.needs_revision) return 'err'
  if (s.progress_status === 'in_review') return 'pri-medium'
  return 'muted-badge'
}

async function loadScenarios() {
  scenarios.value = await fetchScenarios(true, true)
}

onMounted(async () => {
  try {
    const tasks: Promise<unknown>[] = [fetchSystemStatus(), loadScenarios(), fetchOnboardingStatus().catch(() => ({ completed: true }))]
    if (auth.isLegal) {
      tasks.push(
        fetchLegalStatus().catch(() => null),
        fetchLegalMonitor().catch(() => null),
        fetchCorpusAgentStatus().catch(() => null),
        fetchRulesCatalog().catch(() => null),
        fetchPlaybookDeviations().catch(() => null),
      )
    }
    const results = await Promise.all(tasks)
    status.value = results[0] as SystemStatus
    const onboardingStatus = results[2] as { completed?: boolean }
    onboardingComplete.value = onboardingStatus?.completed !== false
    onboardingChecked.value = true
    if (!onboardingComplete.value) {
      await router.replace({ name: 'cold-start' })
      return
    }
    if (auth.isLegal) {
      legalStatus.value = (results[3] as typeof legalStatus.value) ?? null
      legalMonitor.value = (results[4] as typeof legalMonitor.value) ?? null
      corpusAgent.value = (results[5] as typeof corpusAgent.value) ?? null
      rulesCatalog.value = (results[6] as RulesCatalog | null) ?? null
      playbookDeviations.value = (results[7] as typeof playbookDeviations.value) ?? null
    }
  } finally {
    loading.value = false
  }
})

async function runCreateSample() {
  creatingSample.value = true
  sampleError.value = null
  try {
    const scenario = await createFullSample()
    await router.push({ name: 'project-hub', params: { id: scenario.id } })
  } catch {
    sampleError.value = '生成样本失败，请确认后端已启动'
  } finally {
    creatingSample.value = false
  }
}

async function runLegalScan() {
  scanningLegal.value = true
  try {
    legalMonitor.value = await scanLegalMonitor(false)
    legalStatus.value = await fetchLegalStatus()
    corpusAgent.value = await fetchCorpusAgentStatus()
  } finally {
    scanningLegal.value = false
  }
}

async function runCorpusAgent() {
  runningCorpusAgent.value = true
  try {
    await runCorpusMaintenanceAgent(true, true)
    corpusAgent.value = await fetchCorpusAgentStatus()
    legalMonitor.value = await fetchLegalMonitor()
    legalStatus.value = await fetchLegalStatus()
  } finally {
    runningCorpusAgent.value = false
  }
}

async function ackAgentNotification(id: string) {
  await ackCorpusAgentNotification(id)
  corpusAgent.value = await fetchCorpusAgentStatus()
}

const progressLabel: Record<string, string> = {
  pending_scope: '待确认范围',
  submitted: '已提交',
  in_review: '复核中',
  finalized: '已定稿',
  needs_revision: '待补充',
  processing: '处理中',
}

const priorityLabel: Record<string, string> = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
}

function businessProgressText(s: ScenarioSummary) {
  if (s.needs_revision) return progressLabel.needs_revision
  const base = progressLabel[s.progress_status || 'processing'] || s.status
  if (s.feedback_action_required) {
    const n = s.legal_rejected_count || 0
    return n > 0 ? `${base} · ${n} 条待跟进` : `${base} · 需跟进`
  }
  return base
}

function scenarioLinks(s: ScenarioSummary) {
  return {
    hub: `/projects/${s.id}`,
    progress: `/scenarios/${s.id}/progress`,
    extract: `/scenarios/${s.id}/extract`,
    edit: `/scenarios/${s.id}/edit`,
    checklist: `/scenarios/${s.id}/checklist`,
    brief: `/scenarios/${s.id}/brief`,
    review: `/scenarios/${s.id}/review`,
  }
}

async function closeScenario(s: ScenarioSummary) {
  if (s.needs_revision || s.business_archived) return
  archivingId.value = s.id
  sampleError.value = null
  try {
    await archiveScenario(s.id)
    await loadScenarios()
  } catch {
    sampleError.value = '关闭失败，请稍后重试'
  } finally {
    archivingId.value = null
  }
}

async function restoreScenario(s: ScenarioSummary) {
  restoringId.value = s.id
  sampleError.value = null
  try {
    await unarchiveScenario(s.id)
    await loadScenarios()
  } catch {
    sampleError.value = '恢复失败，请稍后重试'
  } finally {
    restoringId.value = null
  }
}

async function restoreLegalScenario(s: ScenarioSummary) {
  restoringId.value = s.id
  sampleError.value = null
  try {
    await restoreDeletedScenario(s.id)
    await loadScenarios()
  } catch {
    sampleError.value = '恢复失败，请稍后重试'
  } finally {
    restoringId.value = null
  }
}

async function removeLegalScenario(s: ScenarioSummary) {
  const statusText =
    legalProgressLabel[s.progress_status || 'processing'] || s.progress_status || '未知'
  if (
    !window.confirm(
      `确定删除「${s.project_name}」？\n\n当前状态：${statusText}\n删除后从列表隐藏，可在下方「回收站」恢复。`,
    )
  ) {
    return
  }
  deletingId.value = s.id
  sampleError.value = null
  try {
    await deleteScenario(s.id)
    await loadScenarios()
  } catch (e: unknown) {
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      if (typeof detail === 'string') {
        sampleError.value = detail
        return
      }
    }
    sampleError.value = '删除失败，请稍后重试'
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="dashboard page-stack" :class="{ 'legal-workbench-order': auth.isLegal, 'business-workbench': auth.isBusiness }">
    <div v-if="!onboardingChecked || !onboardingComplete" class="muted">加载中…</div>
    <template v-else>
    <section class="hero-card">
      <div>
        <p class="eyebrow">工作台</p>
        <h1>欢迎，{{ auth.user?.full_name }}</h1>
        <p class="lead" v-if="auth.isLegal">
          法务专业工作台：按优先级处理待办，对照简报与法条完成复核并导出底稿。
        </p>
        <p class="lead" v-else>
          填写项目 → 系统自动生成清单、法条与简报 → <strong>提交法务复核</strong> → 在此查看进度（已提交 / 复核中 / 已定稿 / 待补充）。
        </p>
      </div>
      <div class="hero-stats">
        <div v-if="auth.isLegal" class="stat">
          <span class="stat-label">法域</span>
          <span class="stat-value">巴西</span>
        </div>
        <div class="stat">
          <span class="stat-label">角色</span>
          <span class="stat-value">{{ auth.roleLabel }}</span>
        </div>
      </div>
    </section>

    <section
      class="panel workbench-panel collapsible-workbench business-submit-panel"
      :class="{ 'is-open': submitPanelOpen }"
      v-if="auth.isBusiness"
    >
      <button
        type="button"
        class="workbench-panel-toggle"
        :aria-expanded="submitPanelOpen"
        @click="submitPanelOpen = !submitPanelOpen"
      >
        <span class="collapse-chevron sm" aria-hidden="true" />
        <div class="workbench-panel-toggle-main">
          <h2>提交新协查</h2>
          <span class="muted workbench-panel-summary">上传方案 · 核对抽取结果 · 提交法务</span>
        </div>
      </button>
      <div v-show="submitPanelOpen" class="workbench-panel-body">
        <p class="muted">
          <strong>只需上传</strong>投资方案（Word、PDF 等）；系统自动抽取并打开核对表，无需事先准备字段清单。提交后由<strong>法务确认协查法域与范围</strong>。
        </p>
        <ul class="panel-hints">
          <li>支持 <strong>.txt / .md / .docx / .pdf</strong>，可多个文件；原文件将归档供法务回看</li>
          <li>提交后在下方「我的协查进度」跟踪状态；法务驳回可在<strong>同一项目</strong>补充后重提</li>
        </ul>
        <p class="error" v-if="sampleError">{{ sampleError }}</p>
        <div class="action-row stack-actions">
          <RouterLink to="/scenarios/new" class="btn-primary link-btn full">上传方案并提交协查</RouterLink>
        </div>
      </div>
    </section>

    <div class="legal-workbench-grid" v-if="auth.isLegal">
      <!-- 法务：法源语料维护 -->
      <section
        class="panel workbench-panel collapsible-workbench"
        :class="{ 'is-open': corpusPanelOpen }"
        v-if="auth.isLegal"
      >
        <button
          type="button"
          class="workbench-panel-toggle"
          :aria-expanded="corpusPanelOpen"
          @click="corpusPanelOpen = !corpusPanelOpen"
        >
          <span class="collapse-chevron sm" aria-hidden="true" />
          <div class="workbench-panel-toggle-main">
            <h2>法源语料维护</h2>
            <span class="muted workbench-panel-summary">
              {{ legalStatus?.document_count ?? '—' }} 条 · {{ legalStatus?.mode ?? '—' }}
            </span>
          </div>
        </button>
        <div v-show="corpusPanelOpen" class="workbench-panel-body">
        <p class="muted">
          补充或更新平台<strong>法条检索语料</strong>，供后续协查绑定法条（默认 Top-3，可在生成协查包时调整）；保存后须<strong>重建索引</strong>，新协查才会引用最新内容。
        </p>
        <ul class="panel-hints">
          <li>
            当前语料
            <strong>{{ legalStatus?.document_count ?? '—' }} 条</strong>
            · 检索模式 {{ legalStatus?.mode ?? '—' }}
          </li>
          <li>维护页可新增 / 编辑 / 删除法条片段，并绑定核查项编号（如 LAB-001）</li>
        </ul>
        <ul v-if="legalMonitor?.alerts?.length" class="panel-alerts">
          <li v-for="alert in legalMonitor.alerts.slice(0, 3)" :key="alert.title">
            <span>{{ alert.title }}</span>
            <span class="badge pri-medium">{{ alert.level }}</span>
          </li>
        </ul>
        <p class="muted" v-else>暂无法规监测提醒。</p>
        <p v-if="legalMonitor?.subscription_count" class="muted">
          已订阅 <strong>{{ legalMonitor.subscription_count }}</strong> 个协查场景；
          <template v-if="legalMonitor.last_diff?.has_changes">
            最近 Diff 影响核查项：
            <strong>{{ (legalMonitor.last_diff.affected_checklist_codes || []).slice(0, 6).join('、') }}</strong>
          </template>
          <template v-else>语料库自上次扫描以来无条目级变更。</template>
        </p>
        <p class="error" v-if="sampleError">{{ sampleError }}</p>
        <div class="action-row stack-actions">
          <RouterLink to="/legal/corpus" class="btn-primary link-btn full">进入法源语料维护</RouterLink>
          <button type="button" class="btn-secondary full" :disabled="scanningLegal" @click="runLegalScan">
            {{ scanningLegal ? '扫描中…' : '手动扫描法规更新' }}
          </button>
          <button type="button" class="btn-secondary full" :disabled="runningCorpusAgent" @click="runCorpusAgent">
            {{ runningCorpusAgent ? 'Agent 运行中…' : '运行语料维护 Agent' }}
          </button>
        </div>
        <div v-if="corpusAgent" class="corpus-agent-panel panel">
          <div class="corpus-agent-head">
            <strong>语料维护 Agent</strong>
            <span v-if="corpusAgent.unread_count" class="badge err">{{ corpusAgent.unread_count }} 条未读</span>
            <span class="muted sm">每 {{ corpusAgent.interval_hours ?? 6 }} 小时自动扫描 · 上次 {{ corpusAgent.last_run_at ? new Date(corpusAgent.last_run_at).toLocaleString() : '—' }}</span>
          </div>
          <p class="muted sm">
            自动：Reg Feed 扫描 → LexML 回溯更新语料 → 分析协查/合同/尽调受影响项目 → 推送法务通知（不自动改已定稿）。
          </p>
          <ul v-if="corpusAgent.notifications?.length" class="agent-notifications">
            <li v-for="n in corpusAgent.notifications.slice(0, 5)" :key="n.id" :class="{ unread: !n.acknowledged }">
              <div class="agent-notif-head">
                <span>{{ n.title }}</span>
                <span class="badge pri-medium">{{ n.level }}</span>
              </div>
              <p class="muted sm">{{ n.summary }}</p>
              <ul v-if="n.impacted_projects?.length" class="panel-hints">
                <li v-for="p in n.impacted_projects.slice(0, 3)" :key="p.scenario_id">
                  <RouterLink :to="`/projects/${p.scenario_id}`">{{ p.project_name }}</RouterLink>
                  <span class="muted sm" v-if="p.material_files?.length"> · 材料：{{ p.material_files.slice(0, 2).join('、') }}</span>
                  <ul v-if="p.artifacts?.length" class="panel-hints nested">
                    <li v-for="a in p.artifacts.slice(0, 3)" :key="a.path">
                      {{ a.type === 'contract' ? '合同' : a.type === 'diligence' ? '尽调' : '协查' }}：{{ a.label }}
                    </li>
                  </ul>
                </li>
              </ul>
              <button
                v-if="!n.acknowledged"
                type="button"
                class="btn-link sm"
                @click="ackAgentNotification(n.id)"
              >
                标记已读
              </button>
            </li>
          </ul>
          <p v-else class="muted sm">暂无 Agent 通知；点击上方按钮可立即运行一次。</p>
        </div>
        <p class="muted panel-footnote">
          监测为 MVP 能力，主要检测本地语料变更 + LexML 回溯；已定稿底稿不会自动变更。
        </p>
        <div v-if="playbookDeviations?.stats?.total" class="playbook-deviation-summary">
          <strong>Playbook 偏差监测</strong>
          <span class="muted">累计驳回 {{ playbookDeviations.stats.total }} 条</span>
          <ul v-if="playbookDeviations.stats.top_rejected_codes?.length" class="panel-hints">
            <li v-for="row in playbookDeviations.stats.top_rejected_codes.slice(0, 5)" :key="row.code">
              {{ row.code }} · {{ row.count }} 次
            </li>
          </ul>
        </div>
        </div>
      </section>

      <section
        class="panel workbench-panel collapsible-workbench rules-pack-loop-panel"
        :class="{ 'is-open': rulesPackLoopOpen }"
        v-if="auth.isLegal"
      >
        <button
          type="button"
          class="workbench-panel-toggle"
          :aria-expanded="rulesPackLoopOpen"
          @click="rulesPackLoopOpen = !rulesPackLoopOpen"
        >
          <span class="collapse-chevron sm" aria-hidden="true" />
          <div class="workbench-panel-toggle-main">
            <h2>规则包闭环</h2>
            <span class="badge pri-medium">
              {{ playbookDeviations?.rules_pack_loop?.suggestion_count ?? 0 }} 条建议
            </span>
            <span class="muted workbench-panel-summary">
              {{ playbookDeviations?.rules_pack_loop?.pack_name ?? rulesCatalog?.pack?.name ?? '规则包' }}
              v{{ playbookDeviations?.rules_pack_loop?.pack_version ?? rulesCatalog?.pack?.version ?? '—' }}
            </span>
          </div>
        </button>
        <div v-show="rulesPackLoopOpen" class="workbench-panel-body">
          <p class="muted">
            聚合法务复核<strong>驳回/偏差</strong>，生成规则包变更<strong>建议草案</strong>（只读，不会自动改 JSON）。
            组织法务负责人审批后，手动更新
            <code>{{ playbookDeviations?.rules_pack_loop?.export_hint ?? 'backend/app/rules/*.json' }}</code> 并 bump 版本号。
          </p>
          <p class="muted sm" v-if="playbookDeviations?.rules_pack_loop?.workflow">
            {{ playbookDeviations.rules_pack_loop.workflow }}
          </p>
          <p class="muted" v-if="!playbookDeviations?.rules_pack_loop?.suggestion_count">
            暂无足够偏差数据（需同一 checklist 累计驳回 ≥2 次）。多跑几次复核驳回后会在此出现建议。
          </p>
          <ul v-else class="rules-suggestion-list">
            <li
              v-for="s in playbookDeviations?.rules_pack_loop?.suggestions ?? []"
              :key="s.id"
              class="rules-suggestion-card"
              :class="'prio-' + s.priority"
            >
              <div class="rules-suggestion-head">
                <strong>{{ s.code }}</strong>
                <span class="badge pri-medium">{{ s.suggestion_type }}</span>
              </div>
              <p class="rules-suggestion-title">{{ s.title }}</p>
              <p class="muted sm">{{ s.rationale }}</p>
              <ul v-if="s.proposed_changes?.length" class="panel-hints nested">
                <li v-for="(ch, idx) in s.proposed_changes" :key="idx">
                  {{ ch.field }} · {{ ch.action }}
                  <span v-if="ch.hint" class="muted"> — {{ ch.hint }}</span>
                </li>
              </ul>
              <ul v-if="s.sample_comments?.length" class="panel-hints nested">
                <li v-for="(c, i) in s.sample_comments" :key="i">评论：{{ c }}</li>
              </ul>
            </li>
          </ul>
        </div>
      </section>

      <section
        class="panel workbench-panel collapsible-workbench"
        :class="{ 'is-open': demoPanelOpen }"
        v-if="auth.isLegal"
      >
        <button
          type="button"
          class="workbench-panel-toggle"
          :aria-expanded="demoPanelOpen"
          @click="demoPanelOpen = !demoPanelOpen"
        >
          <span class="collapse-chevron sm" aria-hidden="true" />
          <div class="workbench-panel-toggle-main">
            <h2>法务演示</h2>
            <span class="muted workbench-panel-summary">BYD 预设 · 约 24 条</span>
          </div>
        </button>
        <div v-show="demoPanelOpen" class="workbench-panel-body">
        <p class="muted">内部演示用一键样本，跳过业务提交环节，直接进入复核页。</p>
        <ul class="panel-hints">
          <li>基于 BYD 坎皮纳斯预设场景，约 24 条核查项</li>
          <li>适合首次了解交付物结构与复核流程</li>
        </ul>
        <p class="error" v-if="sampleError">{{ sampleError }}</p>
        <div class="action-row stack-actions">
          <button type="button" class="btn-secondary full" :disabled="creatingSample" @click="runCreateSample">
            {{ creatingSample ? '生成中…' : '一键生成完整样本' }}
          </button>
        </div>
        <p class="muted panel-footnote">演示样本不代表贵司真实项目；正式协查请等待业务提交。</p>
        </div>
      </section>

      <section
        class="panel workbench-panel collapsible-workbench"
        :class="{ 'is-open': dimensionsPanelOpen }"
        v-if="auth.isLegal && rulesCatalog"
      >
        <button
          type="button"
          class="workbench-panel-toggle"
          :aria-expanded="dimensionsPanelOpen"
          @click="dimensionsPanelOpen = !dimensionsPanelOpen"
        >
          <span class="collapse-chevron sm" aria-hidden="true" />
          <div class="workbench-panel-toggle-main">
            <h2>合规审查维度</h2>
            <span class="badge ok">{{ rulesCatalog?.dimensions?.length ?? 0 }} 个维度</span>
          </div>
        </button>
        <div v-show="dimensionsPanelOpen" class="workbench-panel-body">
        <p class="muted">
          协查法域 <strong>{{ rulesCatalog?.pack?.name }}</strong>（巴西 · 拉美首发）下的
          <strong>{{ rulesCatalog?.dimensions?.length ?? 0 }} 个协查维度</strong>；业务提交材料后，由法务在<strong>复核页</strong>筛选必要维度、确认材料并生成清单。
        </p>
        <div class="dimension-grid dimension-grid-readonly">
          <div
            v-for="dim in rulesCatalog?.dimensions ?? []"
            :key="dim.id"
            class="dimension-card readonly"
          >
            <span class="dimension-check" aria-hidden="true">✓</span>
            <div class="dimension-body">
              <strong>{{ dim.name }}</strong>
              <span class="dim-pt">{{ dim.name_pt }}</span>
              <p>{{ dim.description }}</p>
            </div>
          </div>
        </div>
        <div class="action-row stack-actions">
          <RouterLink to="/legal/corpus" class="btn-secondary link-btn full">按维度维护法源语料</RouterLink>
        </div>
        <p class="muted panel-footnote">调整核查项定义须更新规则库 JSON；语料维护页可按维度筛选并绑定 checklist 编号。</p>
        </div>
      </section>

      <section
        class="panel workbench-panel collapsible-workbench"
        :class="{ 'is-open': aiSettingsPanelOpen }"
        v-if="auth.user"
      >
        <button
          type="button"
          class="workbench-panel-toggle"
          :aria-expanded="aiSettingsPanelOpen"
          @click="aiSettingsPanelOpen = !aiSettingsPanelOpen"
        >
          <span class="collapse-chevron sm" aria-hidden="true" />
          <div class="workbench-panel-toggle-main">
            <h2>AI 设置</h2>
            <span class="badge pri-medium">模型与 API</span>
          </div>
        </button>
        <div v-show="aiSettingsPanelOpen" class="workbench-panel-body">
          <LlmSettingsPanel />
        </div>
      </section>

      <section
        class="panel workbench-panel collapsible-workbench"
        :class="{ 'is-open': systemPanelOpen }"
        v-if="auth.isLegal"
      >
        <button
          type="button"
          class="workbench-panel-toggle"
          :aria-expanded="systemPanelOpen"
          @click="systemPanelOpen = !systemPanelOpen"
        >
          <span class="collapse-chevron sm" aria-hidden="true" />
          <div class="workbench-panel-toggle-main">
            <h2>系统状态</h2>
            <span
              v-if="status"
              class="badge"
              :class="status.database === 'ok' ? 'ok' : 'err'"
            >
              {{ status.database === 'ok' ? '服务正常' : '异常' }}
            </span>
          </div>
        </button>
        <div v-show="systemPanelOpen" class="workbench-panel-body">
        <p class="muted">规则库、法源索引等后台能力；确认服务就绪后再处理待办或维护语料。</p>
        <div v-if="loading" class="muted">检测中…</div>
        <ul v-else-if="status" class="status-list panel-status">
          <li><span>数据库</span><span :class="status.database === 'ok' ? 'badge ok' : 'badge err'">{{ status.database }}</span></li>
          <li><span>规则库</span><span class="badge ok">{{ rulesCatalog?.pack?.name ?? '巴西 · 投资协查' }} · {{ rulesCatalog?.dimensions?.length ?? 4 }} 维度</span></li>
          <li>
            <span>法源索引</span>
            <span class="badge ok">{{ legalStatus?.document_count ?? '—' }} 条 · {{ legalStatus?.mode ?? 'keyword' }}</span>
          </li>
        </ul>
        <p class="muted panel-footnote">业务账号不展示此信息；索引异常时请在法源维护页重建索引或联系管理员。</p>
        </div>
      </section>
    </div>

    <section
      class="panel workbench-panel collapsible-workbench scenario-catalog-panel"
      :class="{ 'is-open': allScenariosPanelOpen }"
      v-if="auth.isLegal ? legalCatalogScenarios.length : true"
    >
      <button
        type="button"
        class="workbench-panel-toggle scenario-catalog-toggle"
        :aria-expanded="allScenariosPanelOpen"
        @click="allScenariosPanelOpen = !allScenariosPanelOpen"
      >
        <span class="collapse-chevron sm" aria-hidden="true" />
        <div class="workbench-panel-toggle-main">
          <h2>{{ auth.isLegal ? '全部协查场景' : '我的协查进度' }}</h2>
          <span
            v-if="auth.isLegal ? legalCatalogScenarios.length : displayedScenarios.length"
            class="badge pri-medium"
          >
            {{ auth.isLegal ? legalCatalogScenarios.length : displayedScenarios.length }} 项
          </span>
          <span v-if="auth.isLegal" class="muted scenario-catalog-meta">
            待复核 {{ legalPendingReviewScenarios.length }} · 复核中 {{ legalInReviewScenarios.length }} ·
            待业务补充 {{ legalNeedsRevisionScenarios.length }} · 已完成 {{ legalCompletedScenarios.length }}
          </span>
          <span v-else-if="displayedScenarios.length" class="muted scenario-catalog-meta">
            待补充 {{ businessNeedsRevisionCount }} · 进行中 {{ businessInProgressCount }} · 已完成
            {{ businessCompletedCount }}
          </span>
        </div>
      </button>

      <div
        v-show="allScenariosPanelOpen"
        class="scenario-catalog-body workbench-panel-body"
      >
        <div v-if="auth.isLegal" class="scenario-group-list">
          <p class="muted scenario-catalog-intro">
            展开对应分组，点击项目旁的「复核」即可处理；Gate A（范围与材料）与清单复核在同一复核页上下分区完成。
          </p>
          <section
            v-for="group in legalScenarioGroups"
            :key="group.id"
            class="scenario-group collapsible-workbench nested"
            :class="{ 'is-open': isScenarioGroupOpen(group.id) }"
          >
            <button
              type="button"
              class="workbench-panel-toggle scenario-group-toggle"
              :aria-expanded="isScenarioGroupOpen(group.id)"
              @click="toggleScenarioGroup(group.id)"
            >
              <span class="collapse-chevron sm" aria-hidden="true" />
              <div class="workbench-panel-toggle-main">
                <h3>{{ group.label }}</h3>
                <span class="badge" :class="group.badgeClass || 'pri-medium'">
                  {{ group.items.length }} 项
                </span>
              </div>
            </button>
            <div v-show="isScenarioGroupOpen(group.id)" class="workbench-panel-body scenario-group-body">
              <p class="muted scenario-group-hint">{{ group.hint }}</p>
              <p class="muted" v-if="!group.items.length">暂无{{ group.label }}项目。</p>
              <ul v-else class="scenario-list">
                <li v-for="s in group.items" :key="s.id">
                  <div>
                    <strong>{{ s.project_name }}</strong>
                    <div class="scenario-row-meta muted">
                      <template v-if="s.submitter_name">{{ s.submitter_name }}</template>
                      <span class="badge" :class="legalProgressBadgeClass(s)">
                        {{ legalProgressLabel[s.progress_status || 'processing'] || s.progress_status }}
                      </span>
                      <span class="badge" :class="'pri-' + (s.review_priority || 'low')">
                        {{ priorityLabel[s.review_priority || 'low'] }}
                      </span>
                      <span v-if="s.blocked_count && (group.id === 'submitted' || group.id === 'in_review')">
                        {{ s.blocked_count }} 条需关注
                      </span>
                      <span>{{ s.total_items }} 条 · {{ new Date(s.created_at).toLocaleDateString('zh-CN') }}</span>
                    </div>
                  </div>
                  <div class="scenario-actions">
                    <RouterLink :to="scenarioLinks(s).hub" class="btn-primary link-btn sm">项目中心</RouterLink>
                    <RouterLink
                      v-if="s.progress_status !== 'pending_scope'"
                      :to="scenarioLinks(s).checklist"
                      class="btn-secondary link-btn sm"
                    >
                      清单
                    </RouterLink>
                    <RouterLink
                      v-if="s.progress_status !== 'pending_scope'"
                      :to="scenarioLinks(s).brief"
                      class="btn-secondary link-btn sm"
                    >
                      简报
                    </RouterLink>
                    <RouterLink :to="scenarioLinks(s).extract" class="btn-secondary link-btn sm">材料</RouterLink>
                    <RouterLink
                      v-if="group.id === 'submitted' || group.id === 'in_review'"
                      :to="scenarioLinks(s).review"
                      class="btn-primary link-btn sm"
                    >
                      复核
                    </RouterLink>
                    <button
                      type="button"
                      class="btn-secondary sm btn-danger-text"
                      :disabled="deletingId === s.id"
                      title="从列表删除，可在回收站恢复"
                      @click="removeLegalScenario(s)"
                    >
                      {{ deletingId === s.id ? '删除中…' : '删除' }}
                    </button>
                  </div>
                </li>
              </ul>
            </div>
          </section>
        </div>

        <div v-else class="scenario-group-list">
          <p class="muted scenario-catalog-intro">
            按状态分组查看协查进度；待补充项请优先处理法务反馈，已完成项可移入回收站。
          </p>
          <p class="muted list-empty-hint" v-if="!displayedScenarios.length && !loading">
            暂无协查项目。点击上方「提交新协查」上传方案并提交材料。
          </p>
          <section
            v-for="group in businessScenarioGroups"
            :key="group.id"
            class="scenario-group collapsible-workbench nested"
            :class="{ 'is-open': isBusinessScenarioGroupOpen(group.id) }"
          >
            <button
              type="button"
              class="workbench-panel-toggle scenario-group-toggle"
              :aria-expanded="isBusinessScenarioGroupOpen(group.id)"
              @click="toggleBusinessScenarioGroup(group.id)"
            >
              <span class="collapse-chevron sm" aria-hidden="true" />
              <div class="workbench-panel-toggle-main">
                <h3>{{ group.label }}</h3>
                <span class="badge" :class="group.badgeClass || 'pri-medium'">
                  {{ group.items.length }} 项
                </span>
              </div>
            </button>
            <div v-show="isBusinessScenarioGroupOpen(group.id)" class="workbench-panel-body scenario-group-body">
              <p class="muted scenario-group-hint">{{ group.hint }}</p>
              <p class="muted" v-if="!group.items.length">暂无{{ group.label }}项目。</p>
              <ul v-else class="scenario-list">
                <li v-for="s in group.items" :key="s.id">
                  <div>
                    <strong>{{ s.project_name }}</strong>
                    <div class="scenario-row-meta muted">
                      <span class="badge" :class="businessProgressBadgeClass(s, group.id)">
                        {{ businessProgressText(s) }}
                      </span>
                      <span>{{ new Date(s.created_at).toLocaleDateString('zh-CN') }}</span>
                    </div>
                  </div>
                  <div class="scenario-actions">
                    <RouterLink :to="scenarioLinks(s).hub" class="btn-primary link-btn sm">项目中心</RouterLink>
                    <RouterLink :to="scenarioLinks(s).progress" class="btn-secondary link-btn sm">查看进度</RouterLink>
                    <RouterLink
                      v-if="group.id === 'needs_revision'"
                      :to="scenarioLinks(s).edit"
                      class="btn-primary link-btn sm"
                    >
                      补充材料
                    </RouterLink>
                    <template v-else>
                      <RouterLink :to="scenarioLinks(s).extract" class="btn-primary link-btn sm">查看AI抽取</RouterLink>
                      <button
                        type="button"
                        class="btn-secondary sm dismiss-btn"
                        :disabled="archivingId === s.id"
                        title="从列表隐藏，可在回收站恢复"
                        @click="closeScenario(s)"
                      >
                        {{ archivingId === s.id ? '处理中…' : '移入回收站' }}
                      </button>
                    </template>
                  </div>
                </li>
              </ul>
            </div>
          </section>
        </div>
      </div>
    </section>

    <section
      class="panel workbench-panel collapsible-workbench recycle-bin-panel"
      :class="{ 'is-open': recycleBinPanelOpen }"
    >
      <button
        type="button"
        class="workbench-panel-toggle scenario-catalog-toggle"
        :aria-expanded="recycleBinPanelOpen"
        @click="recycleBinPanelOpen = !recycleBinPanelOpen"
      >
        <span class="collapse-chevron sm" aria-hidden="true" />
        <div class="workbench-panel-toggle-main">
          <h2>回收站</h2>
          <span class="badge muted-badge">{{ recycleBinItems.length }} 项</span>
          <span class="muted scenario-catalog-meta">
            {{ auth.isLegal ? '已移入回收站的已定稿协查，可随时恢复至列表' : '已隐藏的项目，可随时恢复至协查进度' }}
          </span>
        </div>
      </button>
      <div v-show="recycleBinPanelOpen" class="workbench-panel-body scenario-catalog-body">
        <p class="muted" v-if="!recycleBinItems.length">回收站为空。</p>
        <ul v-else class="scenario-list">
          <li v-for="s in recycleBinItems" :key="s.id">
            <div>
              <strong>{{ s.project_name }}</strong>
              <span class="muted">
                <template v-if="auth.isLegal && s.submitter_name">{{ s.submitter_name }} · </template>
                <span v-if="auth.isLegal" class="badge ok">
                  {{ legalProgressLabel[s.progress_status || 'processing'] || s.progress_status }}
                </span>
                <template v-if="auth.isLegal && s.legal_deleted_at">
                  · 移入于 {{ new Date(s.legal_deleted_at).toLocaleDateString('zh-CN') }}
                </template>
                <template v-else>
                  · {{ new Date(s.created_at).toLocaleDateString('zh-CN') }}
                </template>
              </span>
            </div>
            <div class="scenario-actions">
              <RouterLink
                v-if="auth.isBusiness"
                :to="scenarioLinks(s).progress"
                class="btn-secondary link-btn sm"
              >
                查看进度
              </RouterLink>
              <button
                type="button"
                class="btn-primary sm"
                :disabled="restoringId === s.id"
                @click="auth.isLegal ? restoreLegalScenario(s) : restoreScenario(s)"
              >
                {{ restoringId === s.id ? '恢复中…' : '恢复' }}
              </button>
            </div>
          </li>
        </ul>
      </div>
    </section>
    </template>
  </div>
</template>
