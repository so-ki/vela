<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  analyzeProjectContract,
  analyzeProjectDiligence,
  fetchDiligenceReport,
  fetchIntelligenceReport,
  fetchProjectHub,
  fetchProjectContractAnalysis,
  reviewContractFinding,
  runProjectIntelligence,
  uploadDiligenceDocument,
  uploadProjectContract,
} from '@/api/client'

const route = useRoute()
const projectId = computed(() => Number(route.params.id))
const tab = ref('investigation')

const hub = ref<Record<string, unknown> | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const busy = ref(false)

const contractFile = ref<File | null>(null)
const diligenceFile = ref<File | null>(null)
const contractResult = ref<Record<string, unknown> | null>(null)
const contractDocId = ref<string | null>(null)
const diligenceResult = ref<Record<string, unknown> | null>(null)
const intelligenceResult = ref<Record<string, unknown> | null>(null)

const validTabs = ['investigation', 'contracts', 'diligence', 'intelligence'] as const

watch(
  () => route.query.tab,
  (t) => {
    if (t && validTabs.includes(t as typeof validTabs[number])) tab.value = t as string
  },
  { immediate: true },
)

async function loadHub() {
  loading.value = true
  error.value = null
  try {
    hub.value = await fetchProjectHub(projectId.value)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载项目失败'
  } finally {
    loading.value = false
  }
}

async function loadCachedReports() {
  try {
    diligenceResult.value = await fetchDiligenceReport(projectId.value)
  } catch {
    /* optional */
  }
  try {
    intelligenceResult.value = await fetchIntelligenceReport(projectId.value)
  } catch {
    /* optional */
  }
}

onMounted(async () => {
  await loadHub()
  await loadCachedReports()
})

const modules = computed(() => (hub.value?.modules as Record<string, Record<string, unknown>>) || {})
const contextPreview = computed(() => (hub.value?.context_preview as Record<string, unknown>) || {})

const unifiedIssues = computed(() => (intelligenceResult.value?.unified_issues as Array<Record<string, unknown>>) || [])
const debate = computed(() => intelligenceResult.value?.debate as Record<string, Record<string, unknown>> | undefined)

const contractFindings = computed(
  () => (contractResult.value?.findings as Array<Record<string, unknown>>) || [],
)
const contractRedTeam = computed(
  () => (contractResult.value?.red_team_challenges as Array<Record<string, unknown>>) || [],
)

async function uploadContract() {
  if (!contractFile.value) return
  busy.value = true
  error.value = null
  try {
    const doc = await uploadProjectContract(projectId.value, contractFile.value)
    contractDocId.value = doc.id as string
    contractResult.value = await analyzeProjectContract(projectId.value, doc.id)
    await loadHub()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '合同分析失败'
  } finally {
    busy.value = false
  }
}

async function submitFindingReview(
  clauseIndex: number,
  decision: 'confirmed' | 'false_positive',
) {
  if (!contractDocId.value) return
  busy.value = true
  try {
    await reviewContractFinding(projectId.value, contractDocId.value, {
      clause_index: clauseIndex,
      decision,
    })
    contractResult.value = await fetchProjectContractAnalysis(projectId.value, contractDocId.value)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '确认失败'
  } finally {
    busy.value = false
  }
}

function riskClass(risk: unknown) {
  if (risk === 'RED') return 'risk-red'
  if (risk === 'YELLOW') return 'risk-yellow'
  return 'risk-green'
}

async function runDiligence() {
  busy.value = true
  error.value = null
  try {
    if (diligenceFile.value) {
      await uploadDiligenceDocument(projectId.value, diligenceFile.value)
    }
    diligenceResult.value = await analyzeProjectDiligence(projectId.value)
    await loadHub()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '尽调分析失败'
  } finally {
    busy.value = false
  }
}

async function runIntelligence() {
  busy.value = true
  error.value = null
  try {
    intelligenceResult.value = await runProjectIntelligence(projectId.value)
    await loadHub()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '项目统摄失败'
  } finally {
    busy.value = false
  }
}

function severityClass(s: unknown) {
  if (s === 'high') return 'sev-high'
  if (s === 'medium') return 'sev-medium'
  return 'sev-low'
}
</script>

<template>
  <div class="project-hub page-stack">
    <header class="hub-header page-header">
      <div>
        <RouterLink to="/" class="back-link">← 工作台</RouterLink>
        <h1>{{ hub?.project_name || '项目' }}</h1>
        <p v-if="hub?.location" class="meta">
          {{ (hub.location as Record<string, string>).country }} /
          {{ (hub.location as Record<string, string>).state }} /
          {{ (hub.location as Record<string, string>).city }}
        </p>
      </div>
    </header>

    <nav class="hub-tabs">
      <button type="button" :class="{ active: tab === 'investigation' }" @click="tab = 'investigation'">
        投资协查 <span class="badge muted-badge">{{ modules.investigation?.status }}</span>
      </button>
      <button type="button" :class="{ active: tab === 'contracts' }" @click="tab = 'contracts'">
        合同审查 <span class="badge muted-badge">{{ modules.contracts?.status }}</span>
      </button>
      <button type="button" :class="{ active: tab === 'diligence' }" @click="tab = 'diligence'">
        尽职调查 <span class="badge muted-badge">{{ modules.diligence?.status }}</span>
      </button>
      <button type="button" :class="{ active: tab === 'intelligence' }" @click="tab = 'intelligence'">
        项目统摄 <span class="badge muted-badge">{{ modules.intelligence?.status || 'idle' }}</span>
      </button>
    </nav>

    <div v-if="loading" class="muted">加载中…</div>
    <p v-if="error" class="error banner-error">{{ error }}</p>

    <section v-if="!loading && tab === 'investigation'" class="hub-panel panel">
      <p class="muted">{{ modules.investigation?.summary }}</p>
      <ul class="context-stats">
        <li>S3 阻断：{{ contextPreview.s3_count ?? 0 }}</li>
        <li>合同数：{{ contextPreview.contract_count ?? 0 }}</li>
        <li>统摄 issue：{{ modules.intelligence?.issue_count ?? 0 }}</li>
      </ul>
      <p class="muted excerpt">{{ contextPreview.description_excerpt }}</p>
      <div class="link-grid">
        <RouterLink :to="`/scenarios/${projectId}/checklist`" class="btn-secondary link-btn sm">核查清单</RouterLink>
        <RouterLink :to="`/scenarios/${projectId}/brief`" class="btn-secondary link-btn sm">双语简报</RouterLink>
        <RouterLink :to="`/scenarios/${projectId}/review`" class="btn-primary link-btn sm">法务复核</RouterLink>
        <RouterLink :to="`/scenarios/${projectId}/progress`" class="btn-secondary link-btn sm">业务进度</RouterLink>
      </div>
    </section>

    <section v-if="!loading && tab === 'contracts'" class="hub-panel panel">
      <p class="muted">
        结构化 Playbook（must_have / must_not）+ grounding 摘录 + Red Team 误报/漏报挑战；RED 无 grounding 自动降级。
      </p>
      <div class="hub-upload-row">
        <input type="file" accept=".pdf,.docx,.txt" @change="(e) => (contractFile = (e.target as HTMLInputElement).files?.[0] ?? null)" />
        <button type="button" class="btn-primary" :disabled="busy || !contractFile" @click="uploadContract">
          上传并分析
        </button>
      </div>
      <div v-if="contractResult?.summary" class="result-block muted">
        <p>
          RED {{ (contractResult.summary as Record<string, number>).red_count }} /
          YELLOW {{ (contractResult.summary as Record<string, number>).yellow_count }} /
          GREEN {{ (contractResult.summary as Record<string, number>).green_count }}
          · Red Team {{ (contractResult.summary as Record<string, number>).red_team_challenge_count ?? 0 }} 条
        </p>
      </div>
      <ul v-if="contractRedTeam.length" class="red-team-list">
        <li v-for="(c, i) in contractRedTeam" :key="i">{{ c.message }}</li>
      </ul>
      <div v-if="contractFindings.length" class="table-wrap">
        <table class="issue-table contract-findings">
          <thead>
            <tr>
              <th>#</th>
              <th>风险</th>
              <th>摘录 / grounding</th>
              <th>说明</th>
              <th>法务</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in contractFindings" :key="String(f.clause_index)">
              <td>{{ f.clause_index }}</td>
              <td><span class="risk-badge" :class="riskClass(f.risk)">{{ f.risk }}</span></td>
              <td>
                <small>{{ f.grounding_span || f.excerpt }}</small>
                <span v-if="!f.grounded" class="muted sm"> · 待 grounding</span>
              </td>
              <td>{{ f.risk_label }}</td>
              <td>
                <template v-if="f.legal_decision">{{ f.legal_decision }}</template>
                <template v-else-if="f.risk !== 'GREEN'">
                  <button type="button" class="btn-link sm" :disabled="busy" @click="submitFindingReview(Number(f.clause_index), 'confirmed')">确认</button>
                  <button type="button" class="btn-link sm" :disabled="busy" @click="submitFindingReview(Number(f.clause_index), 'false_positive')">误报</button>
                </template>
                <span v-else class="muted sm">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="!loading && tab === 'diligence'" class="hub-panel panel">
      <p class="muted">尽调关联协查、合同与材料缺口。</p>
      <div class="hub-upload-row">
        <input type="file" accept=".pdf,.docx,.txt" @change="(e) => (diligenceFile = (e.target as HTMLInputElement).files?.[0] ?? null)" />
        <button type="button" class="btn-primary" :disabled="busy" @click="runDiligence">
          {{ diligenceFile ? '上传并运行尽调' : '基于现有材料运行尽调' }}
        </button>
      </div>
      <p v-if="diligenceResult?.summary" class="muted">
        Issue {{ (diligenceResult.summary as Record<string, number>).issue_count }} 条
      </p>
    </section>

    <section v-if="!loading && tab === 'intelligence'" class="hub-panel panel">
      <p class="muted">
        <strong>Analyst</strong> 汇总全部材料与操作事实；
        <strong>Red Team</strong> 专挑矛盾与遗漏（轻量多 Agent 辩论）。
      </p>
      <button type="button" class="btn-primary" :disabled="busy" @click="runIntelligence">
        {{ busy ? '分析中…' : '运行项目统摄 + 冲突检测' }}
      </button>

      <div v-if="debate?.analyst" class="agent-box">
        <h3>Analyst · {{ debate.analyst.role }}</h3>
        <p>{{ debate.analyst.summary }}</p>
      </div>
      <div v-if="debate?.red_team" class="agent-box red">
        <h3>Red Team · {{ debate.red_team.role }}</h3>
        <p>{{ debate.red_team.summary }}</p>
      </div>

      <div v-if="unifiedIssues.length" class="table-wrap">
        <table class="issue-table">
          <thead>
            <tr><th>级别</th><th>问题</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="issue in unifiedIssues" :key="String(issue.id)">
              <td><span class="sev" :class="severityClass(issue.severity)">{{ issue.severity }}</span></td>
              <td>{{ issue.title }}</td>
              <td>{{ issue.detail }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="intelligenceResult" class="muted">未发现需关注的跨模块冲突。</p>
    </section>
  </div>
</template>

<style scoped>
.hub-upload-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: center;
}

.excerpt {
  margin: 0;
}

.result-block {
  margin-top: 0;
}

.table-wrap {
  overflow-x: auto;
}

.agent-box {
  margin-top: 0;
  padding: var(--space-3) var(--space-4);
  background: #f0f9ff;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
}

.agent-box.red {
  background: #fff7ed;
  border-color: #fed7aa;
}

.agent-box h3 {
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
  color: var(--primary);
}

.red-team-list {
  margin: 0;
  padding-left: 1.2rem;
  font-size: var(--text-xs);
  color: #9a3412;
}

.sev {
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.75rem;
  text-transform: uppercase;
}

.sev-high { background: #fee2e2; color: #991b1b; }
.sev-medium { background: #fef3c7; color: #92400e; }
.sev-low { background: #ecfdf5; color: #065f46; }

.risk-badge {
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
}

.risk-red { background: #fee2e2; color: #991b1b; }
.risk-yellow { background: #fef3c7; color: #92400e; }
.risk-green { background: #ecfdf5; color: #065f46; }

.contract-findings {
  font-size: var(--text-xs);
}
</style>
