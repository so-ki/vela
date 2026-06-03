<script setup lang="ts">
import { ref, onMounted, computed, nextTick, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { fetchBrief, fetchLlmStatus, fetchScenario, generateBrief, submitScenarioForReview } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { RiskBrief, Scenario } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const scenario = ref<Scenario | null>(null)
const brief = ref<RiskBrief | null>(null)
const llmStatus = ref<{ available: boolean; message: string; provider?: string | null } | null>(null)
const loading = ref(true)
const generating = ref(false)
const submitting = ref(false)
const submitted = ref(false)
const error = ref<string | null>(null)

const statusLabel: Record<string, string> = {
  ready: '可提交法务复核',
  partial: '部分条目需复核',
  blocked: '暂不可自动定稿',
}

const riskLevelLabel: Record<string, string> = {
  high: '较高',
  medium: '中等',
  low: '可控',
}

const priorityLabel: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

onMounted(async () => {
  const id = Number(route.params.id)
  try {
    llmStatus.value = await fetchLlmStatus().catch(() => null)
    scenario.value = await fetchScenario(id)
    if (scenario.value.status === 'pending_legal_review') {
      submitted.value = true
    }
    try {
      brief.value = await fetchBrief(id)
    } catch {
      if (auth.isLegal) {
        await runGenerate(id, true)
      } else {
        error.value = '简报尚未生成或仍在处理中，请稍后刷新；系统提交法务时会自动生成简报。'
      }
    }
  } catch {
    error.value = '无法加载简报'
  } finally {
    loading.value = false
    scrollToBriefAnchor()
  }
})

function briefAnchorId(code: string) {
  return `brief-${code}`
}

function scrollToBriefAnchor() {
  const hash = route.hash
  if (!hash) return
  nextTick(() => {
    const el = document.querySelector(hash)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    el.classList.add('brief-item-focus')
    window.setTimeout(() => el.classList.remove('brief-item-focus'), 2800)
  })
}

watch(() => route.hash, () => scrollToBriefAnchor())

async function runGenerate(id: number, polish = true) {
  generating.value = true
  error.value = null
  try {
    brief.value = await generateBrief(id, polish)
    if (scenario.value) {
      scenario.value.status = brief.value.status === 'blocked' ? 'brief_blocked' : 'brief_generated'
    }
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    generating.value = false
  }
}

function extractError(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const resp = (e as { response?: { status?: number; data?: { detail?: string } } }).response
    if (resp?.status === 404) return '接口未找到，请重启后端（./scripts/start.sh）'
    if (typeof resp?.data?.detail === 'string') return resp.data.detail
  }
  return '生成简报失败，请确认已完成法源检索'
}

async function runSubmit() {
  if (!scenario.value) return
  submitting.value = true
  error.value = null
  try {
    scenario.value = await submitScenarioForReview(scenario.value.id)
    submitted.value = true
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    submitting.value = false
  }
}

const passedItems = computed(() =>
  (brief.value?.sections || []).flatMap((s) => s.items.filter((i) => i.gate_status === 'passed')),
)
</script>

<template>
  <div class="brief-page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error && !brief" class="error banner-error">{{ error }}</div>
    <template v-else-if="brief && scenario">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">
            {{ auth.isBusiness ? '业务协查 · 双语简报（只读）' : 'Step 5 · 双语法律风险简报' }}
          </p>
          <h1>{{ brief.title_zh }}</h1>
          <p class="meta dim-pt">{{ brief.title_pt }}</p>
          <p class="meta">
            门控阈值 <strong>{{ brief.threshold }}</strong> 分 ·
            已通过 <strong>{{ brief.passed_count }}</strong> 条 ·
            需复核 <strong>{{ brief.blocked_count }}</strong> 条 ·
            模式 <strong>{{
              brief.mode === 'llm'
                ? `LLM 润色 (${brief.llm_provider || 'llm'})`
                : '规则汇编'
            }}</strong>
          </p>
          <p class="meta warn" v-if="brief.llm_polish_skipped">
            LLM 润色未生效：{{ brief.llm_polish_skipped }}
          </p>
          <p class="meta warn" v-if="brief.llm_error">
            LLM 润色失败，已回退模板：{{ brief.llm_error }}
          </p>
          <p class="meta" v-if="llmStatus">
            {{ llmStatus.available ? llmStatus.message : '未配置 API Key，当前为规则模板模式' }}
          </p>
          <p class="meta">
            <span class="badge" :class="brief.status === 'ready' ? 'ok' : brief.status === 'partial' ? 'pri-medium' : 'err'">
              {{ statusLabel[brief.status] || brief.status }}
            </span>
            <span class="muted">生成于 {{ new Date(brief.generated_at).toLocaleString('zh-CN') }}</span>
          </p>
        </div>
        <div class="header-actions">
          <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
          <RouterLink
            v-if="auth.isBusiness"
            :to="{ name: 'scenario-progress', params: { id: scenario.id } }"
            class="btn-secondary link-btn"
          >
            查看进度
          </RouterLink>
          <RouterLink
            v-if="auth.isBusiness"
            :to="{ name: 'checklist', params: { id: scenario.id } }"
            class="btn-secondary link-btn"
          >
            查看清单
          </RouterLink>
          <RouterLink v-if="auth.isLegal" :to="`/scenarios/${scenario.id}/checklist`" class="btn-secondary link-btn">返回清单</RouterLink>
          <RouterLink
            v-if="auth.isLegal"
            :to="{ name: 'review', params: { id: scenario.id } }"
            class="btn-secondary link-btn"
          >
            进入复核
          </RouterLink>
          <template v-if="auth.isLegal">
            <button type="button" class="btn-primary" :disabled="generating" @click="runGenerate(scenario.id, true)">
              {{ generating ? '生成中…' : 'LLM 润色生成' }}
            </button>
            <button type="button" class="btn-secondary" :disabled="generating" @click="runGenerate(scenario.id, false)">
              仅模板
            </button>
          </template>
        </div>
      </header>

      <div class="disclaimer-banner">
        <template v-if="auth.isBusiness">
          本页仅供业务侧<strong>查阅</strong>系统自动生成的双语简报，不构成正式法律意见；复核与定稿须由法务完成。
        </template>
        <template v-else>
          本简报由核查清单与法源检索结果自动汇编，匹配度低于 {{ brief.threshold }} 分的条目不得自动定稿，须标注「需法务复核」。
        </template>
      </div>

      <p class="error banner-error" v-if="error">{{ error }}</p>

      <div v-if="route.query.from === 'review'" class="from-review-banner panel">
        <span>已从法务复核跳转至对应简报片段</span>
        <RouterLink :to="{ name: 'review', params: { id: scenario.id } }" class="btn-secondary link-btn sm">
          返回复核
        </RouterLink>
      </div>

      <section class="brief-summary panel">
        <h2>执行摘要</h2>
        <div class="bilingual-grid">
          <article>
            <h3>中文</h3>
            <p>{{ brief.summary_zh }}</p>
          </article>
          <article>
            <h3>Português</h3>
            <p class="dim-pt">{{ brief.summary_pt }}</p>
          </article>
        </div>
      </section>

      <section
        v-for="section in brief.sections"
        :key="section.dimension_id"
        class="brief-section panel"
      >
        <div class="section-head">
          <div>
            <h2>{{ section.dimension_name }}</h2>
            <span class="dim-pt">{{ section.dimension_name_pt }}</span>
          </div>
          <span class="badge" :class="'risk-' + section.risk_level">
            综合风险 {{ riskLevelLabel[section.risk_level] || section.risk_level }}
          </span>
        </div>
        <div class="bilingual-grid compact">
          <p>{{ section.summary_zh }}</p>
          <p class="dim-pt">{{ section.summary_pt }}</p>
        </div>

        <div class="brief-items">
          <article
            v-for="item in section.items"
            :key="item.code"
            :id="briefAnchorId(item.code)"
            class="brief-item"
            :class="{ blocked: item.gate_status === 'blocked' }"
          >
            <div class="item-head">
              <span class="item-code">{{ item.code }}</span>
              <span class="badge" :class="item.gate_status === 'passed' ? 'ok' : 'pri-medium'">
                {{ item.gate_status === 'passed' ? '已通过门控' : '需法务复核' }}
              </span>
              <span class="badge" :class="'pri-' + item.priority">
                {{ priorityLabel[item.priority] || item.priority }}优先级
              </span>
              <span class="score">匹配度 {{ item.match_score }}</span>
            </div>
            <h3>{{ item.title }}</h3>
            <p v-if="item.block_reason" class="block-reason">门控原因：{{ item.block_reason }}</p>
            <div class="bilingual-grid">
              <p>{{ item.risk_zh }}</p>
              <p class="dim-pt">{{ item.risk_pt }}</p>
            </div>
            <div v-if="item.citations.length" class="brief-citations">
              <h4>法条依据</h4>
              <div v-for="cite in item.citations" :key="cite.id" class="citation-row">
                <span class="source-badge">{{ cite.source_label }}</span>
                <span>{{ cite.title_zh || cite.title_pt }}</span>
                <span class="muted">（{{ cite.match_score }}）</span>
                <a :href="cite.url" target="_blank" rel="noopener" class="hit-link">溯源 ↗</a>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section v-if="brief.blocked_items.length" class="brief-blocked panel">
        <h2>需法务复核清单（{{ brief.blocked_items.length }} 条）</h2>
        <p class="muted">以下条目未通过匹配度门控，不得纳入自动定稿版本，须人工确认后补充。</p>
        <ul class="blocked-list">
          <li v-for="item in brief.blocked_items" :key="item.code">
            <strong>{{ item.code }}</strong> — {{ item.title }}
            <span class="muted">（{{ item.block_reason }}）</span>
          </li>
        </ul>
      </section>

      <section class="brief-disclaimer panel muted">
        <h2>免责声明</h2>
        <pre class="disclaimer-text">{{ brief.disclaimer }}</pre>
      </section>

      <div class="next-step panel">
        <h2>{{ auth.isBusiness ? '说明' : '下一步（Step 6）' }}</h2>
        <template v-if="auth.isBusiness">
          <p class="muted">
            本项目已通过「生成并提交法务」进入复核流程。您可在此查阅简报与法条依据；法务反馈请见
            <RouterLink :to="{ name: 'scenario-progress', params: { id: scenario.id } }">进度页</RouterLink>。
          </p>
          <div class="action-row stack-actions">
            <RouterLink
              :to="{ name: 'scenario-progress', params: { id: scenario.id } }"
              class="btn-primary link-btn full"
            >
              返回进度跟踪
            </RouterLink>
            <RouterLink to="/" class="btn-secondary link-btn full">返回工作台</RouterLink>
          </div>
        </template>
        <template v-else>
          <p class="muted">对每条核查项进行确认 / 驳回 / 批注，定稿后可导出 Word / PDF 协查底稿。</p>
          <div class="action-row stack-actions">
            <RouterLink
              :to="{ name: 'review', params: { id: scenario.id } }"
              class="btn-primary link-btn full"
            >
              进入法务复核
            </RouterLink>
            <RouterLink to="/" class="btn-secondary link-btn full">返回工作台</RouterLink>
          </div>
        </template>
      </div>

      <div v-if="route.query.from === 'review'" class="review-return-bar">
        <RouterLink
          :to="{ name: 'review', params: { id: scenario.id } }"
          class="btn-primary link-btn review-return-btn"
        >
          ← 返回继续复核
        </RouterLink>
      </div>
    </template>
  </div>
</template>
