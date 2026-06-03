<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
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
const inlineSnippets = ref<Record<string, { item: BriefItem; legalHits: LegalHit[] }>>({})
const snippetLoading = ref<Record<string, boolean>>({})
const snippetErrors = ref<Record<string, string>>({})

const reviewFilter = ref<'all' | 'pending' | 'gate' | 'external'>('all')
const GATE_THRESHOLD = 70

type ReviewSectionGroup = {
  dimension_id: string
  dimension_name: string
  dimension_name_pt: string
  description: string
  items: ReviewItem[]
}

const sectionOpen = ref<Record<string, boolean>>({})
const itemOpen = ref<Record<string, boolean>>({})

function initReviewCollapseState(sections: ReviewSectionGroup[]) {
  if (!sections.length) return
  const nextSection: Record<string, boolean> = { ...sectionOpen.value }
  const nextItem: Record<string, boolean> = { ...itemOpen.value }
  for (const section of sections) {
    if (!(section.dimension_id in nextSection)) {
      nextSection[section.dimension_id] = false
    }
    for (const item of section.items) {
      if (!(item.code in nextItem)) {
        nextItem[item.code] = false
      }
    }
  }
  sectionOpen.value = nextSection
  itemOpen.value = nextItem
}

function isSectionOpen(id: string) {
  return sectionOpen.value[id] ?? false
}

function isItemOpen(code: string) {
  return itemOpen.value[code] ?? false
}

function toggleSection(id: string) {
  sectionOpen.value = { ...sectionOpen.value, [id]: !isSectionOpen(id) }
}

function toggleItem(code: string) {
  const willOpen = !isItemOpen(code)
  itemOpen.value = { ...itemOpen.value, [code]: willOpen }
  if (willOpen) void ensureInlineSnippet(code)
}

function setAllSections(open: boolean) {
  const next: Record<string, boolean> = { ...sectionOpen.value }
  for (const section of reviewSections.value) {
    next[section.dimension_id] = open
  }
  sectionOpen.value = next
}

function setAllReviewItems(open: boolean) {
  const next: Record<string, boolean> = { ...itemOpen.value }
  for (const section of reviewSections.value) {
    for (const item of section.items) {
      next[item.code] = open
      if (open) void ensureInlineSnippet(item.code)
    }
  }
  itemOpen.value = next
}

const openSectionCount = computed(
  () => reviewSections.value.filter((s) => isSectionOpen(s.dimension_id)).length,
)

const openReviewItemCount = computed(() =>
  reviewSections.value.reduce(
    (n, section) => n + section.items.filter((item) => isItemOpen(item.code)).length,
    0,
  ),
)

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

const reviewSections = computed((): ReviewSectionGroup[] => {
  const items = filteredItems.value
  if (!items.length) return []

  const checklistSections = scenario.value?.checklist?.sections || []
  if (!checklistSections.length) {
    const byDim = new Map<string, ReviewItem[]>()
    for (const item of items) {
      const key = item.dimension_name || '其他'
      if (!byDim.has(key)) byDim.set(key, [])
      byDim.get(key)!.push(item)
    }
    return Array.from(byDim.entries()).map(([name, sectionItems], idx) => ({
      dimension_id: `dim-${idx}`,
      dimension_name: name,
      dimension_name_pt: '',
      description: '',
      items: sectionItems,
    }))
  }

  const groups: ReviewSectionGroup[] = []
  const used = new Set<string>()
  for (const section of checklistSections) {
    const sectionItems = section.items
      .map((ci) => items.find((i) => i.code === ci.code))
      .filter((i): i is ReviewItem => !!i)
    for (const item of sectionItems) used.add(item.code)
    if (sectionItems.length) {
      groups.push({
        dimension_id: section.dimension_id,
        dimension_name: section.dimension_name,
        dimension_name_pt: section.dimension_name_pt,
        description: section.description,
        items: sectionItems,
      })
    }
  }
  const orphans = items.filter((i) => !used.has(i.code))
  if (orphans.length) {
    groups.push({
      dimension_id: '_other',
      dimension_name: '其他',
      dimension_name_pt: '',
      description: '',
      items: orphans,
    })
  }
  return groups
})

watch(
  reviewSections,
  (sections) => {
    if (sections.length) initReviewCollapseState(sections)
  },
  { immediate: true },
)

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
  router.push({ name: 'brief', params: { id: route.params.id }, query: { from: 'review' } })
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

async function ensureInlineSnippet(code: string) {
  if (inlineSnippets.value[code] || snippetLoading.value[code] || !scenario.value) return
  snippetLoading.value = { ...snippetLoading.value, [code]: true }
  snippetErrors.value = { ...snippetErrors.value, [code]: '' }
  try {
    if (!briefCache.value) {
      briefCache.value = await fetchBrief(scenario.value.id)
    }
    const match = findBriefItem(briefCache.value, code)
    if (!match) {
      snippetErrors.value = {
        ...snippetErrors.value,
        [code]: `简报中未找到条目 ${code}`,
      }
      return
    }
    const reviewItem = review.value?.items.find((i) => i.code === code)
    inlineSnippets.value = {
      ...inlineSnippets.value,
      [code]: { item: match.item, legalHits: reviewItem?.legal_hits || [] },
    }
  } catch {
    snippetErrors.value = {
      ...snippetErrors.value,
      [code]: '无法加载简报片段，请确认已生成双语简报',
    }
  } finally {
    snippetLoading.value = { ...snippetLoading.value, [code]: false }
  }
}

function inlineSnippet(code: string) {
  return inlineSnippets.value[code]
}

function openFullBrief(code: string) {
  router.push({
    name: 'brief',
    params: { id: route.params.id },
    hash: `#brief-${code}`,
    query: { from: 'review' },
  })
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

      <div class="collapse-toolbar panel" v-if="reviewSections.length">
        <span class="muted">
          共 {{ reviewSections.length }} 个合规维度 · 已展开 {{ openSectionCount }} 个 ·
          {{ filteredItems.length }} 条核查项 · 已展开 {{ openReviewItemCount }} 条
        </span>
        <div class="collapse-toolbar-actions">
          <button type="button" class="btn-text" @click="setAllSections(true)">展开全部维度</button>
          <button type="button" class="btn-text" @click="setAllSections(false)">折叠全部维度</button>
          <button type="button" class="btn-text" @click="setAllReviewItems(true)">展开全部条目</button>
          <button type="button" class="btn-text" @click="setAllReviewItems(false)">折叠全部条目</button>
        </div>
      </div>

      <section
        v-for="section in reviewSections"
        :key="section.dimension_id"
        class="checklist-section panel collapsible-section"
        :class="{ 'is-open': isSectionOpen(section.dimension_id) }"
      >
        <button
          type="button"
          class="section-toggle"
          :aria-expanded="isSectionOpen(section.dimension_id)"
          @click="toggleSection(section.dimension_id)"
        >
          <span class="collapse-chevron" aria-hidden="true" />
          <div class="section-toggle-main">
            <h2>{{ section.dimension_name }}</h2>
            <span class="dim-pt">{{ section.dimension_name_pt }}</span>
          </div>
          <span class="badge ok">{{ section.items.length }} 条</span>
        </button>

        <div v-show="isSectionOpen(section.dimension_id)" class="section-body">
          <p v-if="section.description" class="section-desc">{{ section.description }}</p>

          <div class="checklist-items">
            <article
              v-for="item in section.items"
              :key="item.code"
              class="checklist-item review-item collapsible-item"
              :class="[item.decision, { 'is-open': isItemOpen(item.code) }]"
            >
              <button
                type="button"
                class="item-toggle"
                :aria-expanded="isItemOpen(item.code)"
                @click="toggleItem(item.code)"
              >
                <span class="collapse-chevron sm" aria-hidden="true" />
                <div class="item-toggle-main">
                  <div class="item-head">
                    <span class="item-code">{{ item.code }}</span>
                    <span class="badge" :class="item.gate_status === 'passed' ? 'ok' : 'pri-medium'">
                      门控 {{ item.gate_status === 'passed' ? '通过' : '需关注' }} · {{ item.match_score }}
                    </span>
                    <span class="badge decision-badge" :class="item.decision">
                      {{ item.decision === 'approved' ? '已确认' : item.decision === 'rejected' ? '已驳回' : '待复核' }}
                    </span>
                  </div>
                  <h3>{{ item.title }}</h3>
                </div>
              </button>

              <div v-show="isItemOpen(item.code)" class="item-body review-item-body">
                <p v-if="snippetLoading[item.code]" class="muted">加载简报片段…</p>
                <p v-else-if="snippetErrors[item.code]" class="error">{{ snippetErrors[item.code] }}</p>
                <template v-else-if="inlineSnippet(item.code)">
                  <div class="review-item-inline-snippet">
                    <div class="item-head">
                      <span
                        class="badge"
                        :class="inlineSnippet(item.code)!.item.gate_status === 'passed' ? 'ok' : 'pri-medium'"
                      >
                        {{
                          inlineSnippet(item.code)!.item.gate_status === 'passed' ? '已通过门控' : '需法务复核'
                        }}
                      </span>
                      <span class="badge" :class="'pri-' + inlineSnippet(item.code)!.item.priority">
                        {{
                          priorityLabel[inlineSnippet(item.code)!.item.priority] ||
                          inlineSnippet(item.code)!.item.priority
                        }}优先级
                      </span>
                      <span class="score">匹配度 {{ inlineSnippet(item.code)!.item.match_score }}</span>
                    </div>
                    <p v-if="inlineSnippet(item.code)!.item.block_reason" class="block-reason">
                      门控原因：{{ inlineSnippet(item.code)!.item.block_reason }}
                    </p>
                    <p class="gate-line muted">
                      门控阈值 {{ GATE_THRESHOLD }} 分 · 当前匹配度 {{ inlineSnippet(item.code)!.item.match_score }}
                      <template v-if="inlineSnippet(item.code)!.item.match_score < GATE_THRESHOLD">
                        （未过线，须人工复核）
                      </template>
                    </p>
                    <div class="snippet-section-title">简报风险说明</div>
                    <div class="bilingual-grid">
                      <article>
                        <h4>中文</h4>
                        <p>{{ inlineSnippet(item.code)!.item.risk_zh }}</p>
                      </article>
                      <article>
                        <h4>Português</h4>
                        <p class="dim-pt">{{ inlineSnippet(item.code)!.item.risk_pt }}</p>
                      </article>
                    </div>
                    <div v-if="inlineSnippet(item.code)!.item.citations.length" class="brief-citations">
                      <h4>简报引用法条</h4>
                      <div
                        v-for="cite in inlineSnippet(item.code)!.item.citations"
                        :key="cite.id"
                        class="citation-row"
                      >
                        <span class="source-badge">{{ cite.source_label }}</span>
                        <span>{{ cite.title_zh || cite.title_pt }}</span>
                        <a :href="cite.url" target="_blank" rel="noopener" class="hit-link">溯源 ↗</a>
                      </div>
                    </div>
                    <div
                      v-if="inlineSnippet(item.code)!.legalHits.length"
                      class="brief-citations legal-hits-panel"
                    >
                      <h4>法源检索原文片段</h4>
                      <div
                        v-for="hit in inlineSnippet(item.code)!.legalHits"
                        :key="hit.id"
                        class="legal-hit compact"
                      >
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
                  <div class="review-item-inline-actions">
                    <template v-if="!isLocked">
                      <button
                        type="button"
                        class="btn-secondary sm"
                        :disabled="saving === item.code"
                        @click="setDecision(item.code, 'approved')"
                      >
                        确认本条
                      </button>
                      <button
                        type="button"
                        class="btn-secondary sm reject"
                        :disabled="saving === item.code"
                        @click="setDecision(item.code, 'rejected')"
                      >
                        驳回本条
                      </button>
                    </template>
                    <button type="button" class="btn-text" @click="openFullBrief(item.code)">
                      在完整简报中打开
                    </button>
                  </div>
                </template>
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
              </div>
            </article>
          </div>
        </div>
      </section>

      <p class="muted panel" v-if="!reviewSections.length">当前筛选下暂无条目。</p>
    </template>
  </div>
</template>
