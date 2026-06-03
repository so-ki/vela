<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  approveAllReview,
  downloadDocxExport,
  downloadPdfExport,
  fetchBrief,
  fetchExportConfig,
  fetchReview,
  fetchScenario,
  finalizeReview,
  initReview,
  returnScenarioToBusiness,
  updateReviewItem,
} from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { BriefItem, LegalHit, ReviewItem, ReviewState, RiskBrief, Scenario } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const scenario = ref<Scenario | null>(null)
const review = ref<ReviewState | null>(null)
const loading = ref(true)
const saving = ref<string | null>(null)
const finalizing = ref(false)
const returning = ref(false)
const exporting = ref(false)
const exportingPdf = ref(false)
const exportDocxLabel = ref('法律研究意见书')
const error = ref<string | null>(null)
const comments = ref<Record<string, string>>({})
const briefCache = ref<RiskBrief | null>(null)
const loadingSnippetCode = ref<string | null>(null)
const snippetPanel = ref<{
  open: boolean
  code: string | null
  item: BriefItem | null
  dimensionName: string | null
  legalHits: LegalHit[]
}>({
  open: false,
  code: null,
  item: null,
  dimensionName: null,
  legalHits: [],
})

const reviewFilter = ref<'all' | 'pending' | 'gate' | 'external'>('all')
const GATE_THRESHOLD = 70

const priorityLabel: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

const statusLabel: Record<string, string> = {
  in_progress: '复核中',
  approved: '已全部确认',
  partial: '部分确认',
  rejected: '已驳回',
  returned: '已退回业务',
}

const isLocked = computed(() =>
  review.value ? !['in_progress'].includes(review.value.status) || !auth.isLegal : true,
)

const filteredItems = computed(() => {
  const items = review.value?.items || []
  switch (reviewFilter.value) {
    case 'pending':
      return items.filter((i) => i.decision === 'pending')
    case 'gate':
      return items.filter((i) => i.gate_status !== 'passed' || i.match_score < GATE_THRESHOLD)
    case 'external':
      return items.filter((i) => i.external_counsel_required)
    default:
      return items
  }
})

onMounted(async () => {
  const id = Number(route.params.id)
  try {
    const exportCfg = await fetchExportConfig()
    exportDocxLabel.value = exportCfg.docx_label
    scenario.value = await fetchScenario(id)
    try {
      review.value = await fetchReview(id)
    } catch {
      if (auth.isLegal) {
        review.value = await initReview(id)
      } else {
        error.value = '法务尚未开始复核，请在工作台等待处理结果'
      }
    }
    for (const item of review.value?.items || []) {
      if (item.comment) comments.value[item.code] = item.comment
    }
  } catch {
    error.value = '无法加载复核工作台，请先生成双语简报'
  } finally {
    loading.value = false
  }
  window.addEventListener('keydown', onSnippetKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onSnippetKeydown)
  unlockBodyScroll()
})

async function setDecision(code: string, decision: 'approved' | 'rejected') {
  if (!scenario.value || isLocked.value) return
  saving.value = code
  error.value = null
  try {
    review.value = await updateReviewItem(scenario.value.id, code, {
      decision,
      comment: comments.value[code] || undefined,
      external_counsel_required: review.value?.items.find((i) => i.code === code)?.external_counsel_required,
    })
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    saving.value = null
  }
}

async function saveComment(code: string) {
  if (!scenario.value || isLocked.value || !review.value) return
  const item = review.value.items.find((i) => i.code === code)
  if (!item || item.decision === 'pending') return
  saving.value = code
  try {
    review.value = await updateReviewItem(scenario.value.id, code, {
      decision: item.decision,
      comment: comments.value[code] || undefined,
      external_counsel_required: item.external_counsel_required,
    })
  } finally {
    saving.value = null
  }
}

async function toggleExternalCounsel(item: ReviewItem, value: boolean) {
  if (!scenario.value || isLocked.value) return
  saving.value = item.code
  try {
    review.value = await updateReviewItem(scenario.value.id, item.code, {
      decision: item.decision,
      comment: comments.value[item.code] || undefined,
      external_counsel_required: value,
    })
  } finally {
    saving.value = null
  }
}

async function runApproveAll() {
  if (!scenario.value || isLocked.value) return
  saving.value = 'all'
  error.value = null
  try {
    review.value = await approveAllReview(scenario.value.id)
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    saving.value = null
  }
}

async function runFinalize() {
  if (!scenario.value || !review.value?.can_finalize) return
  finalizing.value = true
  error.value = null
  try {
    review.value = await finalizeReview(scenario.value.id)
    scenario.value.status = `review_${review.value.status}`
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    finalizing.value = false
  }
}

async function runReturnToBusiness() {
  if (!scenario.value || !review.value?.can_return_to_business) return
  const note = window.prompt('退回说明（可选，将展示给业务）：') ?? ''
  returning.value = true
  error.value = null
  try {
    scenario.value = await returnScenarioToBusiness(scenario.value.id, note || undefined)
    await router.push({ name: 'dashboard' })
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    returning.value = false
  }
}

async function runExportPdf() {
  if (!scenario.value || !review.value?.can_export) return
  exportingPdf.value = true
  error.value = null
  try {
    const { blob, filename } = await downloadPdfExport(scenario.value.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    exportingPdf.value = false
  }
}

async function runExport() {
  if (!scenario.value || !review.value?.can_export) return
  exporting.value = true
  error.value = null
  try {
    const { blob, filename } = await downloadDocxExport(scenario.value.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    exporting.value = false
  }
}

function extractError(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const resp = (e as { response?: { data?: { detail?: string } } }).response
    if (typeof resp?.data?.detail === 'string') return resp.data.detail
  }
  return '操作失败'
}

function goBrief() {
  router.push({ name: 'brief', params: { id: route.params.id } })
}

function findBriefItem(brief: RiskBrief, code: string): { item: BriefItem; dimensionName: string } | null {
  for (const section of brief.sections) {
    const found = section.items.find((i) => i.code === code)
    if (found) return { item: found, dimensionName: section.dimension_name }
  }
  const blocked = brief.blocked_items.find((i) => i.code === code)
  if (blocked) return { item: blocked, dimensionName: '需法务复核' }
  return null
}

async function openBriefSnippet(code: string) {
  if (!scenario.value) return
  const reviewItem = review.value?.items.find((i) => i.code === code)
  loadingSnippetCode.value = code
  error.value = null
  try {
    if (!briefCache.value) {
      briefCache.value = await fetchBrief(scenario.value.id)
    }
    const match = findBriefItem(briefCache.value, code)
    if (!match) {
      error.value = `简报中未找到条目 ${code}`
      return
    }
    snippetPanel.value = {
      open: true,
      code,
      item: match.item,
      dimensionName: match.dimensionName,
      legalHits: reviewItem?.legal_hits || [],
    }
  } catch {
    error.value = '无法加载简报片段，请确认已生成双语简报'
  } finally {
    loadingSnippetCode.value = null
  }
}

function closeSnippet() {
  snippetPanel.value = { open: false, code: null, item: null, dimensionName: null, legalHits: [] }
}

let bodyScrollLocked = false
let savedScrollY = 0

function lockBodyScroll() {
  if (bodyScrollLocked) return
  savedScrollY = window.scrollY
  document.body.style.overflow = 'hidden'
  document.body.style.position = 'fixed'
  document.body.style.top = `-${savedScrollY}px`
  document.body.style.left = '0'
  document.body.style.right = '0'
  document.body.style.width = '100%'
  bodyScrollLocked = true
}

function unlockBodyScroll() {
  if (!bodyScrollLocked) return
  document.body.style.overflow = ''
  document.body.style.position = ''
  document.body.style.top = ''
  document.body.style.left = ''
  document.body.style.right = ''
  document.body.style.width = ''
  window.scrollTo(0, savedScrollY)
  bodyScrollLocked = false
}

watch(
  () => snippetPanel.value.open,
  (open) => {
    if (open) lockBodyScroll()
    else unlockBodyScroll()
  },
)

async function decideFromSnippet(decision: 'approved' | 'rejected') {
  const code = snippetPanel.value.code
  if (!code) return
  await setDecision(code, decision)
  closeSnippet()
}

function openFullBrief(code: string) {
  closeSnippet()
  router.push({
    name: 'brief',
    params: { id: route.params.id },
    hash: `#brief-${code}`,
    query: { from: 'review' },
  })
}

function onSnippetKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closeSnippet()
}
</script>

<template>
  <div class="review-page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error && !review" class="error banner-error">{{ error }}</div>
    <template v-else-if="review && scenario">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">Step 6 · 法务复核工作台</p>
          <h1>{{ scenario.project_name }}</h1>
          <p class="meta">
            复核人 <strong>{{ review.reviewer_name }}</strong> ·
            已确认 <strong>{{ review.approved_count }}</strong> ·
            已驳回 <strong>{{ review.rejected_count }}</strong> ·
            待处理 <strong>{{ review.pending_count }}</strong>
          </p>
          <p class="meta">
            <span class="badge" :class="review.status === 'approved' ? 'ok' : review.status === 'in_progress' ? 'pri-medium' : 'err'">
              {{ statusLabel[review.status] || review.status }}
            </span>
          </p>
        </div>
        <div class="header-actions" v-if="auth.isLegal">
          <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
          <RouterLink :to="{ name: 'checklist', params: { id: scenario.id } }" class="btn-secondary link-btn">查看清单</RouterLink>
          <button type="button" class="btn-secondary" @click="goBrief">查看简报</button>
          <button
            v-if="!isLocked"
            type="button"
            class="btn-secondary"
            :disabled="saving === 'all'"
            @click="runApproveAll"
          >
            全部确认
          </button>
          <button
            v-if="!isLocked && review.can_return_to_business"
            type="button"
            class="btn-secondary reject"
            :disabled="returning"
            @click="runReturnToBusiness"
          >
            {{ returning ? '退回中…' : '退回业务补充' }}
          </button>
          <button
            type="button"
            class="btn-primary"
            :disabled="!review.can_finalize || finalizing || isLocked"
            @click="runFinalize"
          >
            {{ finalizing ? '定稿中…' : '提交复核定稿' }}
          </button>
          <button
            type="button"
            class="btn-secondary"
            :disabled="!review.can_export || exporting"
            @click="runExport"
          >
            {{ exporting ? '导出中…' : `导出 Word · ${exportDocxLabel}` }}
          </button>
          <button
            type="button"
            class="btn-secondary"
            :disabled="!review.can_export || exportingPdf"
            @click="runExportPdf"
          >
            {{ exportingPdf ? '导出中…' : '导出 PDF' }}
          </button>
        </div>
      </header>

      <div class="disclaimer-banner">
        <template v-if="auth.isLegal">
          请对每条核查项作出确认或驳回，并可在批注栏补充意见。全部处理完成后方可定稿并导出{{ exportDocxLabel }}。
        </template>
        <template v-else>
          本页仅供查看复核进度。确认、定稿与导出须由法务角色操作。
        </template>
      </div>

      <p class="error banner-error" v-if="error">{{ error }}</p>

      <div class="review-filters panel">
        <button
          v-for="f in [
            { id: 'all', label: '全部' },
            { id: 'pending', label: '待处理' },
            { id: 'gate', label: '门控未过线' },
            { id: 'external', label: '需外聘律所' },
          ]"
          :key="f.id"
          type="button"
          class="btn-secondary sm"
          :class="{ active: reviewFilter === f.id }"
          @click="reviewFilter = f.id as typeof reviewFilter"
        >
          {{ f.label }}
        </button>
      </div>

      <section class="review-items panel">
        <article v-for="item in filteredItems" :key="item.code" class="review-item" :class="item.decision">
          <div class="item-head">
            <span class="item-code">{{ item.code }}</span>
            <span class="muted">{{ item.dimension_name }}</span>
            <span class="badge" :class="item.gate_status === 'passed' ? 'ok' : 'pri-medium'">
              门控 {{ item.gate_status === 'passed' ? '通过' : '需关注' }} · {{ item.match_score }}
            </span>
            <span class="badge decision-badge" :class="item.decision">
              {{ item.decision === 'approved' ? '已确认' : item.decision === 'rejected' ? '已驳回' : '待复核' }}
            </span>
          </div>
          <h3>{{ item.title }}</h3>
          <div class="review-actions">
            <button
              type="button"
              class="btn-secondary sm link-brief-snippet"
              @click="openBriefSnippet(item.code)"
              :disabled="loadingSnippetCode === item.code"
            >
              {{ loadingSnippetCode === item.code ? '加载中…' : '查看简报片段' }}
            </button>
            <template v-if="!isLocked">
              <button
                type="button"
                class="btn-secondary sm"
                :disabled="saving === item.code"
                @click="setDecision(item.code, 'approved')"
              >
                确认
              </button>
              <button
                type="button"
                class="btn-secondary sm reject"
                :disabled="saving === item.code"
                @click="setDecision(item.code, 'rejected')"
              >
                驳回
              </button>
            </template>
          </div>
          <label class="comment-field">
            <span>批注</span>
            <input
              v-model="comments[item.code]"
              :disabled="isLocked"
              placeholder="可选：补充复核意见"
              @blur="saveComment(item.code)"
            />
          </label>
          <label class="external-counsel-field" v-if="!isLocked">
            <input
              type="checkbox"
              :checked="!!item.external_counsel_required"
              @change="toggleExternalCounsel(item, ($event.target as HTMLInputElement).checked)"
            />
            <span>需外聘当地律所补充意见</span>
          </label>
          <p class="muted external-flag" v-else-if="item.external_counsel_required">已标记：需外聘律所</p>
        </article>
        <p class="muted" v-if="!filteredItems.length">当前筛选下暂无条目。</p>
      </section>

      <!-- 简报片段侧栏：不离开复核页 -->
      <Teleport to="body">
        <div
          v-if="snippetPanel.open && snippetPanel.item"
          class="snippet-overlay"
          @click.self="closeSnippet"
          @wheel.self.prevent
          @touchmove.self.prevent
        >
          <aside class="snippet-drawer" role="dialog" aria-label="简报片段" @click.stop>
            <header class="snippet-drawer-head">
              <div>
                <span class="item-code">{{ snippetPanel.code }}</span>
                <span class="muted">{{ snippetPanel.dimensionName }}</span>
              </div>
              <button type="button" class="btn-text" @click="closeSnippet">✕</button>
            </header>

            <div class="snippet-drawer-body">
              <div class="item-head">
                <span class="badge" :class="snippetPanel.item.gate_status === 'passed' ? 'ok' : 'pri-medium'">
                  {{ snippetPanel.item.gate_status === 'passed' ? '已通过门控' : '需法务复核' }}
                </span>
                <span class="badge" :class="'pri-' + snippetPanel.item.priority">
                  {{ priorityLabel[snippetPanel.item.priority] || snippetPanel.item.priority }}优先级
                </span>
                <span class="score">匹配度 {{ snippetPanel.item.match_score }}</span>
              </div>
              <h3>{{ snippetPanel.item.title }}</h3>
              <p v-if="snippetPanel.item.block_reason" class="block-reason">
                门控原因：{{ snippetPanel.item.block_reason }}
              </p>
              <p class="gate-line muted">
                门控阈值 {{ GATE_THRESHOLD }} 分 · 当前匹配度 {{ snippetPanel.item.match_score }}
                <template v-if="snippetPanel.item.match_score < GATE_THRESHOLD">（未过线，须人工复核）</template>
              </p>
              <div class="snippet-section-title">简报风险说明</div>
              <div class="bilingual-grid">
                <article>
                  <h4>中文</h4>
                  <p>{{ snippetPanel.item.risk_zh }}</p>
                </article>
                <article>
                  <h4>Português</h4>
                  <p class="dim-pt">{{ snippetPanel.item.risk_pt }}</p>
                </article>
              </div>
              <div v-if="snippetPanel.item.citations.length" class="brief-citations">
                <h4>简报引用法条</h4>
                <div v-for="cite in snippetPanel.item.citations" :key="cite.id" class="citation-row">
                  <span class="source-badge">{{ cite.source_label }}</span>
                  <span>{{ cite.title_zh || cite.title_pt }}</span>
                  <a :href="cite.url" target="_blank" rel="noopener" class="hit-link">溯源 ↗</a>
                </div>
              </div>

              <div v-if="snippetPanel.legalHits.length" class="brief-citations legal-hits-panel">
                <h4>法源检索原文片段</h4>
                <div v-for="hit in snippetPanel.legalHits" :key="hit.id" class="legal-hit compact">
                  <div class="hit-head">
                    <span class="source-badge">{{ hit.source_label }}</span>
                    <span class="badge" :class="hit.requires_review ? 'pri-medium' : 'ok'">
                      匹配度 {{ hit.match_score }}
                    </span>
                  </div>
                  <strong>{{ hit.title_zh || hit.title_pt }}</strong>
                  <p class="hit-excerpt">{{ hit.excerpt_pt }}</p>
                  <p class="hit-excerpt zh" v-if="hit.excerpt_zh">{{ hit.excerpt_zh }}</p>
                  <a :href="hit.url" target="_blank" rel="noopener" class="hit-link">LexML / 法院门户 ↗</a>
                </div>
              </div>
            </div>

            <footer class="snippet-drawer-foot">
              <button type="button" class="btn-primary" @click="closeSnippet">关闭，继续复核</button>
              <template v-if="!isLocked">
                <button
                  type="button"
                  class="btn-secondary"
                  :disabled="saving === snippetPanel.code"
                  @click="decideFromSnippet('approved')"
                >
                  确认本条
                </button>
                <button
                  type="button"
                  class="btn-secondary reject"
                  :disabled="saving === snippetPanel.code"
                  @click="decideFromSnippet('rejected')"
                >
                  驳回本条
                </button>
              </template>
              <button
                type="button"
                class="btn-text"
                @click="openFullBrief(snippetPanel.code!)"
              >
                在完整简报中打开
              </button>
            </footer>
          </aside>
        </div>
      </Teleport>
    </template>
  </div>
</template>
