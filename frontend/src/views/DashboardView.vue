<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  createFullSample,
  fetchLegalMonitor,
  fetchLegalStatus,
  fetchRulesCatalog,
  fetchScenarios,
  fetchSystemStatus,
  generateAndSubmitDemo,
  scanLegalMonitor,
} from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { ScenarioSummary, RulesCatalog } from '@/types/scenario'
import type { SystemStatus } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const status = ref<SystemStatus | null>(null)
const legalStatus = ref<{ document_count?: number; mode?: string; sources_breakdown?: Record<string, number> } | null>(null)
const legalMonitor = ref<{ alerts?: Array<{ title: string; message: string; level: string }>; last_scan_at?: string | null } | null>(null)
const scanningLegal = ref(false)
const scenarios = ref<ScenarioSummary[]>([])
const rulesCatalog = ref<RulesCatalog | null>(null)
const loading = ref(true)
const creatingSample = ref(false)
const submittingDemo = ref(false)
const sampleError = ref<string | null>(null)

onMounted(async () => {
  try {
    const tasks: Promise<unknown>[] = [fetchSystemStatus(), fetchScenarios()]
    if (auth.isLegal) {
      tasks.push(fetchLegalStatus().catch(() => null), fetchLegalMonitor().catch(() => null), fetchRulesCatalog().catch(() => null))
    }
    const results = await Promise.all(tasks)
    status.value = results[0] as SystemStatus
    scenarios.value = results[1] as ScenarioSummary[]
    if (auth.isLegal) {
      legalStatus.value = (results[2] as typeof legalStatus.value) ?? null
      legalMonitor.value = (results[3] as typeof legalMonitor.value) ?? null
      rulesCatalog.value = (results[4] as RulesCatalog | null) ?? null
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
    await router.push({ name: 'review', params: { id: scenario.id } })
  } catch {
    sampleError.value = '生成样本失败，请确认后端已启动'
  } finally {
    creatingSample.value = false
  }
}

async function runBusinessDemoSubmit() {
  submittingDemo.value = true
  sampleError.value = null
  try {
    const scenario = await generateAndSubmitDemo(false)
    await router.push({ name: 'scenario-progress', params: { id: scenario.id } })
  } catch {
    sampleError.value = '提交失败，请确认后端已启动'
  } finally {
    submittingDemo.value = false
  }
}

async function runLegalScan() {
  scanningLegal.value = true
  try {
    legalMonitor.value = await scanLegalMonitor(false)
    legalStatus.value = await fetchLegalStatus()
  } finally {
    scanningLegal.value = false
  }
}

const pendingForLegal = computed(() =>
  scenarios.value.filter((s) => s.status === 'pending_legal_review' || s.status === 'review_in_progress'),
)

const progressLabel: Record<string, string> = {
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
    progress: `/scenarios/${s.id}/progress`,
    edit: `/scenarios/${s.id}/edit`,
    checklist: `/scenarios/${s.id}/checklist`,
    brief: `/scenarios/${s.id}/brief`,
    review: `/scenarios/${s.id}/review`,
  }
}
</script>

<template>
  <div class="dashboard">
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
        <div class="stat">
          <span class="stat-label">法域</span>
          <span class="stat-value">巴西</span>
        </div>
        <div class="stat">
          <span class="stat-label">角色</span>
          <span class="stat-value">{{ auth.roleLabel }}</span>
        </div>
      </div>
    </section>

    <div class="grid-2">
      <!-- 业务：提交入口（与提交页、客户手册步骤 2 对齐） -->
      <section class="panel workbench-panel" v-if="auth.isBusiness">
        <h2>提交新协查</h2>
        <p class="muted">
          填写项目信息后，系统将自动生成<strong>专项核查清单</strong>、检索法条、汇编<strong>双语简报</strong>，并<strong>直接提交法务复核</strong>。
        </p>
        <ul class="panel-hints">
          <li>提交页可上传 <strong>.txt / .md / .docx</strong> 方案预填表单</li>
          <li>提交后在下方「我的协查进度」跟踪状态；法务驳回可在<strong>同一项目</strong>补充后重提</li>
        </ul>
        <p class="error" v-if="sampleError">{{ sampleError }}</p>
        <div class="action-row stack-actions">
          <RouterLink to="/scenarios/new" class="btn-primary link-btn full">填写项目并提交法务</RouterLink>
          <button type="button" class="btn-secondary full" :disabled="submittingDemo" @click="runBusinessDemoSubmit">
            {{ submittingDemo ? '提交中…' : '演示项目一键提交法务' }}
          </button>
        </div>
        <p class="muted panel-footnote">演示按钮使用 BYD 坎皮纳斯预设场景，仅供学习流程；正式项目请填写真实信息。</p>
      </section>

      <!-- 法务：待办队列 -->
      <section class="panel workbench-panel" v-if="auth.isLegal">
        <h2>待办队列</h2>
        <p class="muted">
          按<strong>复核优先级</strong>处理业务提交的协查；含「待法务复核」与「复核中」任务，门控未过线条目会排在前面。
        </p>
        <ul class="panel-hints">
          <li>进入复核后对照侧栏执行<strong>协查三问</strong>，逐条确认 / 驳回 / 批注</li>
          <li>全部条目处理完毕 → 提交定稿 → 导出 Word / PDF 协查底稿</li>
        </ul>
        <ul v-if="pendingForLegal.length" class="scenario-list compact panel-queue">
          <li v-for="s in pendingForLegal" :key="s.id">
            <div>
              <strong>{{ s.project_name }}</strong>
              <span class="muted">{{ s.submitter_name }} · {{ s.submitter_organization }}</span>
              <span class="badge" :class="'pri-' + (s.review_priority || 'low')">
                {{ priorityLabel[s.review_priority || 'low'] }}
              </span>
              <span class="muted" v-if="s.blocked_count">· {{ s.blocked_count }} 条需关注</span>
            </div>
            <RouterLink :to="scenarioLinks(s).review" class="btn-primary link-btn sm">进入复核</RouterLink>
          </li>
        </ul>
        <p class="muted" v-else>暂无待办；可在下方「全部协查场景」查看历史项目。</p>
        <div v-if="pendingForLegal.length" class="action-row stack-actions">
          <RouterLink
            :to="scenarioLinks(pendingForLegal[0]).review"
            class="btn-primary link-btn full"
          >
            处理优先级最高任务
          </RouterLink>
        </div>
        <p class="muted panel-footnote">驳回后可通过「退回业务补充」让业务在同一项目修改后重提，无需新建场景。</p>
      </section>

      <!-- 法务：法源语料维护 -->
      <section class="panel workbench-panel" v-if="auth.isLegal">
        <h2>法源语料维护</h2>
        <p class="muted">
          补充或更新平台<strong>法条检索语料</strong>，供后续协查绑定 Top-3 法条；保存后须<strong>重建索引</strong>，新协查才会引用最新内容。
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
        <p class="error" v-if="sampleError">{{ sampleError }}</p>
        <div class="action-row stack-actions">
          <RouterLink to="/legal/corpus" class="btn-primary link-btn full">进入法源语料维护</RouterLink>
          <button type="button" class="btn-secondary full" :disabled="scanningLegal" @click="runLegalScan">
            {{ scanningLegal ? '扫描中…' : '手动扫描法规更新' }}
          </button>
        </div>
        <p class="muted panel-footnote">
          监测为 MVP 能力，主要检测本地语料变更，不能替代 LexML 持续跟踪；已定稿底稿不会自动变更。
        </p>
      </section>

      <section class="panel workbench-panel workbench-panel-compact" v-if="auth.isLegal">
        <h2>法务演示（可选）</h2>
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
      </section>

      <section class="panel workbench-panel workbench-panel-compact" v-if="auth.isLegal && rulesCatalog">
        <h2>合规审查维度</h2>
        <p class="muted">
          当前行业专包 <strong>{{ rulesCatalog.pack?.name }}</strong> 下的
          <strong>{{ rulesCatalog.dimensions.length }} 个协查维度</strong>；业务提交时默认全覆盖，此处供法务对照规则库与法源语料。
        </p>
        <div class="dimension-grid dimension-grid-readonly">
          <div
            v-for="dim in rulesCatalog.dimensions"
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
      </section>

      <section class="panel workbench-panel workbench-panel-compact" v-if="auth.isLegal">
        <h2>系统状态</h2>
        <p class="muted">规则库、法源索引等后台能力；确认服务就绪后再处理待办或维护语料。</p>
        <div v-if="loading" class="muted">检测中…</div>
        <ul v-else-if="status" class="status-list panel-status">
          <li><span>数据库</span><span :class="status.database === 'ok' ? 'badge ok' : 'badge err'">{{ status.database }}</span></li>
          <li><span>规则库</span><span class="badge ok">新能源专包 v2 · 4 维度</span></li>
          <li>
            <span>法源索引</span>
            <span class="badge ok">{{ legalStatus?.document_count ?? '—' }} 条 · {{ legalStatus?.mode ?? 'keyword' }}</span>
          </li>
        </ul>
        <p class="muted panel-footnote">业务账号不展示此信息；索引异常时请在法源维护页重建索引或联系管理员。</p>
      </section>
    </div>

    <section class="panel" v-if="scenarios.length">
      <h2>{{ auth.isLegal ? '全部协查场景' : '我的协查进度' }}</h2>
      <ul class="scenario-list">
        <li v-for="s in scenarios" :key="s.id">
          <div>
            <strong>{{ s.project_name }}</strong>
            <span class="muted">
              <template v-if="auth.isLegal && s.submitter_name">{{ s.submitter_name }} · </template>
              <span class="badge ok" v-if="auth.isBusiness">{{ businessProgressText(s) }}</span>
              <template v-else>
                <span class="badge" :class="'pri-' + (s.review_priority || 'low')">{{ priorityLabel[s.review_priority || 'low'] }}</span>
                · {{ s.total_items }} 条
              </template>
              · {{ new Date(s.created_at).toLocaleDateString('zh-CN') }}
            </span>
          </div>
          <div class="scenario-actions">
            <RouterLink v-if="auth.isBusiness" :to="scenarioLinks(s).progress" class="btn-secondary link-btn sm">查看进度</RouterLink>
            <RouterLink
              v-if="auth.isBusiness && s.needs_revision"
              :to="scenarioLinks(s).edit"
              class="btn-primary link-btn sm"
            >
              补充材料
            </RouterLink>
            <template v-else>
              <RouterLink :to="scenarioLinks(s).checklist" class="btn-secondary link-btn sm">清单</RouterLink>
              <RouterLink :to="scenarioLinks(s).brief" class="btn-secondary link-btn sm">简报</RouterLink>
              <RouterLink
                v-if="s.status === 'pending_legal_review' || s.status.startsWith('review_')"
                :to="scenarioLinks(s).review"
                class="btn-secondary link-btn sm"
              >
                复核
              </RouterLink>
            </template>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>
