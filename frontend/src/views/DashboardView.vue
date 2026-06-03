<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { createFullSample, fetchLegalMonitor, fetchLegalStatus, fetchScenarios, fetchSystemStatus, scanLegalMonitor } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { ScenarioSummary } from '@/types/scenario'
import type { SystemStatus } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const status = ref<SystemStatus | null>(null)
const legalStatus = ref<{ document_count?: number; mode?: string; sources_breakdown?: Record<string, number> } | null>(null)
const legalMonitor = ref<{ alerts?: Array<{ title: string; message: string; level: string }>; last_scan_at?: string | null } | null>(null)
const scanningLegal = ref(false)
const scenarios = ref<ScenarioSummary[]>([])
const loading = ref(true)
const creatingSample = ref(false)
const sampleError = ref<string | null>(null)

onMounted(async () => {
  try {
    const [sys, list, legal, monitor] = await Promise.all([
      fetchSystemStatus(),
      fetchScenarios(),
      fetchLegalStatus().catch(() => null),
      fetchLegalMonitor().catch(() => null),
    ])
    status.value = sys
    scenarios.value = list
    legalStatus.value = legal
    legalMonitor.value = monitor
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

async function runLegalScan() {
  scanningLegal.value = true
  try {
    legalMonitor.value = await scanLegalMonitor(false)
    legalStatus.value = await fetchLegalStatus()
  } finally {
    scanningLegal.value = false
  }
}

function scenarioLinks(s: ScenarioSummary) {
  return {
    checklist: `/scenarios/${s.id}/checklist`,
    brief: `/scenarios/${s.id}/brief`,
    review: `/scenarios/${s.id}/review`,
  }
}

const pendingForLegal = computed(() =>
  scenarios.value.filter((s) => s.status === 'pending_legal_review'),
)

const statusLabel: Record<string, string> = {
  checklist_generated: '清单已生成',
  brief_generated: '简报已生成',
  brief_blocked: '简报需关注',
  pending_legal_review: '待法务复核',
  review_in_progress: '复核中',
  review_approved: '已定稿',
  review_partial: '部分确认',
  review_rejected: '已驳回',
}

const roadmap = [
  { step: 1, title: '项目骨架', done: true, desc: '认证、免责、基础架构' },
  { step: 2, title: '规则库', done: true, desc: '场景 → 法律审查维度映射' },
  { step: 3, title: '法源 RAG', done: true, desc: 'LexML / STF / STJ 检索索引' },
  { step: 4, title: '清单生成', done: true, desc: '中文意图解析 → 核查清单' },
  { step: 5, title: '双语简报', done: true, desc: '匹配度门控 + 中葡风险简报' },
  { step: 6, title: '法务复核', done: true, desc: '确认 / 驳回 / 批注工作台' },
  { step: 7, title: '导出底稿', done: true, desc: 'Word + PDF 协查底稿' },
  { step: 8, title: 'LLM 增强', done: true, desc: '意图解析 + 简报润色' },
]
</script>

<template>
  <div class="dashboard">
    <section class="hero-card">
      <div>
        <p class="eyebrow">工作台 · 完整样本流程已就绪</p>
        <h1>欢迎，{{ auth.user?.full_name }}</h1>
        <p class="lead" v-if="auth.isLegal">
          法务工作台：处理业务提交的协查场景，完成复核并导出底稿；也可一键生成演示样本。
        </p>
        <p class="lead" v-else>
          提交投资场景 → 生成核查清单与双语简报 → <strong>提交法务复核</strong>，由法务同事定稿导出。
        </p>
      </div>
      <div class="hero-stats">
        <div class="stat">
          <span class="stat-label">法域</span>
          <span class="stat-value">巴西</span>
        </div>
        <div class="stat">
          <span class="stat-label">行业包</span>
          <span class="stat-value">新能源</span>
        </div>
      </div>
    </section>

    <div class="grid-2">
      <section class="panel sample-panel" v-if="auth.isLegal">
        <h2>生成完整样本（法务演示）</h2>
        <p class="muted">自动完成 BYD 演示场景、法条绑定、双语简报，并进入法务复核工作台。</p>
        <p class="error" v-if="sampleError">{{ sampleError }}</p>
        <button type="button" class="btn-primary" :disabled="creatingSample" @click="runCreateSample">
          {{ creatingSample ? '生成中…' : '一键生成完整样本' }}
        </button>
      </section>

      <section class="panel sample-panel" v-else>
        <h2>开始协查</h2>
        <p class="muted">填写投资项目，生成清单与双语简报后，提交法务同事复核。</p>
        <RouterLink to="/scenarios/new" class="btn-primary link-btn">提交协查场景</RouterLink>
      </section>

      <section class="panel" v-if="auth.isLegal">
        <h2>待处理任务</h2>
        <p class="muted">业务已提交、等待法务复核的场景。</p>
        <ul v-if="pendingForLegal.length" class="scenario-list compact">
          <li v-for="s in pendingForLegal" :key="s.id">
            <div>
              <strong>{{ s.project_name }}</strong>
              <span class="muted">{{ s.submitter_name }} · {{ s.submitter_organization }}</span>
            </div>
            <RouterLink :to="scenarioLinks(s).review" class="btn-secondary link-btn sm">开始复核</RouterLink>
          </li>
        </ul>
        <p class="muted" v-else>暂无待复核任务。</p>
      </section>

      <section class="panel" v-if="auth.isBusiness">
        <h2>分步操作</h2>
        <p class="muted">提交场景后，依次完成清单、简报，再提交法务复核。</p>
        <div class="action-row">
          <RouterLink to="/scenarios/new" class="btn-secondary link-btn">提交协查场景</RouterLink>
        </div>
      </section>

      <section class="panel" v-else-if="auth.isLegal">
        <h2>分步操作</h2>
        <p class="muted">也可手动逐步提交场景、查看清单与简报。</p>
        <div class="action-row">
          <RouterLink to="/scenarios/new" class="btn-secondary link-btn">提交协查场景</RouterLink>
          <RouterLink to="/scenarios/new" class="btn-secondary link-btn">使用演示模板</RouterLink>
        </div>
      </section>

      <section class="panel">
        <h2>法规动态监测（辅线）</h2>
        <p class="muted">MVP：本地语料变更检测 + 手动扫描；生产可对接 LexML 更新源。</p>
        <ul v-if="legalMonitor?.alerts?.length" class="status-list monitor-list">
          <li v-for="alert in legalMonitor.alerts.slice(0, 3)" :key="alert.title">
            <span>{{ alert.title }}</span>
            <span class="badge pri-medium">{{ alert.level }}</span>
          </li>
        </ul>
        <p class="muted" v-else>暂无监测提醒，点击下方扫描。</p>
        <div class="action-row">
          <button type="button" class="btn-secondary" :disabled="scanningLegal" @click="runLegalScan">
            {{ scanningLegal ? '扫描中…' : '手动扫描法规更新' }}
          </button>
          <a class="btn-secondary link-btn" href="http://127.0.0.1:8000/docs" target="_blank" rel="noopener">API 文档 /docs</a>
          <a class="btn-secondary link-btn" href="https://github.com/so-ki/vela" target="_blank" rel="noopener">GitHub 仓库</a>
        </div>
      </section>

      <section class="panel">
        <h2>系统状态</h2>
        <div v-if="loading" class="muted">检测中…</div>
        <ul v-else-if="status" class="status-list">
          <li>
            <span>数据库</span>
            <span :class="status.database === 'ok' ? 'badge ok' : 'badge err'">{{ status.database }}</span>
          </li>
          <li>
            <span>规则库</span>
            <span class="badge ok">新能源 · 4 维度</span>
          </li>
          <li>
            <span>法源索引</span>
            <span class="badge ok">
              {{ legalStatus?.document_count ?? '—' }} 条 · {{ legalStatus?.mode ?? 'keyword' }}
              <template v-if="legalStatus?.sources_breakdown">
                · LexML {{ legalStatus.sources_breakdown.lexml ?? 0 }}
              </template>
            </span>
          </li>
        </ul>
      </section>
    </div>

    <section class="panel" v-if="scenarios.length">
      <h2>{{ auth.isLegal ? '全部协查场景' : '我的协查场景' }}</h2>
      <ul class="scenario-list">
        <li v-for="s in scenarios" :key="s.id">
          <div>
            <strong>{{ s.project_name }}</strong>
            <span class="muted">
              <template v-if="auth.isLegal && s.submitter_name">{{ s.submitter_name }} · </template>
              {{ s.total_items }} 条清单 · {{ statusLabel[s.status] || s.status }} ·
              {{ new Date(s.created_at).toLocaleDateString('zh-CN') }}
            </span>
          </div>
          <div class="scenario-actions">
            <RouterLink :to="scenarioLinks(s).checklist" class="btn-secondary link-btn sm">清单</RouterLink>
            <RouterLink
              v-if="s.status.startsWith('brief_') || s.status === 'pending_legal_review' || s.status.startsWith('review_')"
              :to="scenarioLinks(s).brief"
              class="btn-secondary link-btn sm"
            >
              简报
            </RouterLink>
            <RouterLink
              v-if="auth.isLegal && (s.status === 'pending_legal_review' || s.status.startsWith('review_'))"
              :to="scenarioLinks(s).review"
              class="btn-secondary link-btn sm"
            >
              复核
            </RouterLink>
          </div>
        </li>
      </ul>
    </section>

    <section class="panel">
      <h2>实施路线图</h2>
      <div class="roadmap">
        <div
          v-for="item in roadmap"
          :key="item.step"
          class="roadmap-item"
          :class="{ done: item.done, current: item.step === 8 }"
        >
          <div class="step-num">{{ item.step }}</div>
          <div>
            <strong>{{ item.title }}</strong>
            <p>{{ item.desc }}</p>
          </div>
          <span class="roadmap-badge" v-if="item.done">已完成</span>
          <span class="roadmap-badge next" v-else-if="item.step === 8">可选</span>
        </div>
      </div>
    </section>
  </div>
</template>
