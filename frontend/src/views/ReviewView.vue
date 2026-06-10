<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  approveAllReview,
  downloadDocxExport,
  downloadPdfExport,
  downloadAuditBundle,
  fetchBrief,
  fetchExportConfig,
  fetchReview,
  fetchRulesCatalog,
  fetchScenario,
  finalizeReview,
  initReview,
  returnScenarioToBusiness,
  updateReviewItem,
} from '@/api/client'
import LegalMaterialGatePanel from '@/components/LegalMaterialGatePanel.vue'
import InvestigationAdequacyPanel from '@/components/InvestigationAdequacyPanel.vue'
import { useAuthStore } from '@/stores/auth'
import type { BriefItem, LegalHit, ReviewItem, ReviewState, RiskBrief, RulesCatalog, Scenario } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const scenario = ref<Scenario | null>(null)
const catalog = ref<RulesCatalog | null>(null)
const review = ref<ReviewState | null>(null)
const loading = ref(true)
const saving = ref<string | null>(null)
const finalizing = ref(false)
const returning = ref(false)
const exporting = ref(false)
const exportingPdf = ref(false)
const exportingAudit = ref(false)
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
  let openedSection = false
  for (const section of sections) {
    if (!(section.dimension_id in nextSection)) {
      const hasPending = section.items.some((item) => item.decision === 'pending')
      nextSection[section.dimension_id] = hasPending && !openedSection
      if (hasPending && !openedSection) openedSection = true
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

const showScopePanel = computed(
  () => auth.isLegal && scenario.value?.status === 'pending_scope',
)

const showInvestigationAdequacy = computed(
  () =>
    !!catalog.value &&
    !!scenario.value?.investigation_adequacy &&
    scenario.value.status !== 'pending_scope',
)

const gateAAllowsReview = computed(
  () => scenario.value?.gate_a_allows_review !== false,
)

const showChecklistReview = computed(() => !showScopePanel.value && gateAAllowsReview.value)

const showGateABlock = computed(
  () => !showScopePanel.value && showInvestigationAdequacy.value && !gateAAllowsReview.value,
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

async function loadReviewData(id: number) {
  if (scenario.value?.status === 'pending_scope') {
    review.value = null
    return
  }
  if (!gateAAllowsReview.value) {
    review.value = null
    return
  }
  try {
    review.value = await fetchReview(id)
  } catch {
    if (auth.isLegal) {
      review.value = await initReview(id)
    } else {
      throw new Error('法务尚未开始复核，请在工作台等待处理结果')
    }
  }
  comments.value = {}
  for (const item of review.value?.items || []) {
    if (item.comment) comments.value[item.code] = item.comment
  }
}

async function loadPage() {
  const id = Number(route.params.id)
  error.value = null
  const exportCfg = await fetchExportConfig()
  exportDocxLabel.value = exportCfg.docx_label
  if (auth.isLegal) {
    catalog.value = await fetchRulesCatalog()
  }
  scenario.value = await fetchScenario(id)
  await loadReviewData(id)
}

onMounted(async () => {
  loading.value = true
  try {
    await loadPage()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '无法加载复核工作台，请稍后重试'
  } finally {
    loading.value = false
  }
})

async function onInvestigationGenerated(updated: Scenario) {
  scenario.value = updated
  loading.value = true
  error.value = null
  try {
    await loadReviewData(updated.id)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '协查包已生成，但复核工作台加载失败'
  } finally {
    loading.value = false
  }
}

async function onMaterialsReturned() {
  await router.push({ name: 'dashboard' })
}

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

async function runExportAudit() {
  if (!scenario.value || !review.value?.can_export) return
  exportingAudit.value = true
  error.value = null
  try {
    const { blob, filename } = await downloadAuditBundle(scenario.value.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: unknown) {
    error.value = extractError(e)
  } finally {
    exportingAudit.value = false
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
  <div class="review-page page-stack">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error && !scenario" class="error banner-error">{{ error }}</div>
    <template v-else-if="scenario">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">法务复核工作台</p>
          <h1>{{ scenario.project_name }}</h1>
          <p class="meta" v-if="showScopePanel">
            确认或调整协查维度后，系统将<strong>自动生成协查包</strong>，随后在本页统一复核。
          </p>
          <template v-else-if="review">
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
              <span v-if="review.version_label" class="badge ok">定稿 {{ review.version_label }}</span>
            </p>
          </template>
        </div>
        <div class="header-actions" v-if="auth.isLegal">
          <div class="header-actions-primary">
            <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
            <template v-if="showChecklistReview && review">
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
            </template>
          </div>
          <div v-if="showChecklistReview && review?.can_export" class="header-actions-secondary">
            <button
              type="button"
              class="btn-secondary sm"
              :disabled="exporting"
              @click="runExport"
            >
              {{ exporting ? '导出中…' : `导出 Word · ${exportDocxLabel}` }}
            </button>
            <button
              type="button"
              class="btn-secondary sm"
              :disabled="exportingPdf"
              @click="runExportPdf"
            >
              {{ exportingPdf ? '导出中…' : '导出 PDF' }}
            </button>
            <button
              type="button"
              class="btn-secondary sm"
              :disabled="exportingAudit"
              @click="runExportAudit"
            >
              {{ exportingAudit ? '导出中…' : '导出审计包 JSON' }}
            </button>
          </div>
        </div>
      </header>

      <LegalMaterialGatePanel
        v-if="showScopePanel && catalog"
        :scenario="scenario"
        :catalog="catalog"
        @investigation-generated="onInvestigationGenerated"
      />

      <InvestigationAdequacyPanel
        v-if="showInvestigationAdequacy && catalog && scenario.investigation_adequacy"
        :scenario="scenario"
        :catalog="catalog"
        :adequacy="scenario.investigation_adequacy"
        :can-return="!!scenario.can_return_materials && auth.isLegal"
        :blocks-review="showGateABlock"
        :incremental-regen="scenario.incremental_regen"
        @materials-returned="onMaterialsReturned"
      />

      <section
        v-if="showInvestigationAdequacy && (scenario.grounding_report || scenario.verification_report)"
        class="panel quality-reports-section"
      >
        <h2>引证校验与三 Pass 验证</h2>
        <p class="muted">借鉴 Lavern 引证 grounding + 简化 verification；定稿后可导出完整 audit bundle。</p>
        <div v-if="scenario.grounding_report" class="quality-report-block">
          <strong>引证 Grounding</strong>
          <span class="badge" :class="scenario.grounding_report.requires_legal_check ? 'warn' : 'ok'">
            命中率 {{ Math.round((scenario.grounding_report.grounding_rate ?? 1) * 100) }}%
          </span>
          <p v-if="scenario.grounding_report.ungrounded_codes?.length" class="muted">
            待核条目：{{ scenario.grounding_report.ungrounded_codes.join('、') }}
          </p>
        </div>
        <ul v-if="scenario.verification_report?.passes?.length" class="verification-pass-list">
          <li v-for="pass in scenario.verification_report.passes" :key="pass.id">
            <span class="badge" :class="pass.passed ? 'ok' : 'rejected'">{{ pass.passed ? '通过' : '待确认' }}</span>
            <strong>{{ pass.label }}</strong>
            <span class="muted">{{ pass.detail }}</span>
          </li>
        </ul>
      </section>

      <section v-if="showGateABlock" class="panel review-section-pending gate-a-block-panel">
        <h2>② 清单条目复核（已锁定）</h2>
        <p class="muted">
          构成要件尚未完备，请先在上方的 Gate A 视图中<strong>打回业务补充材料</strong>。材料补齐并重新生成协查包通过后，方可进入清单复核。
        </p>
      </section>

      <template v-else-if="showChecklistReview">
        <section v-if="review" class="review-checklist-section">
          <div class="review-section-head panel">
            <h2>② 清单条目复核</h2>
            <p class="muted">对核查清单逐条确认或驳回；全部处理完成后方可定稿并导出。</p>
            <p v-if="scenario.incremental_regen?.mode === 'incremental'" class="incremental-regen-banner">
              补材料后增量生成：{{ scenario.incremental_regen.review_stats?.items_carried ?? 0 }} 条沿用上一轮结论，
              {{ scenario.incremental_regen.target_codes.length }} 条需重新审核
              <template v-if="(scenario.incremental_regen.review_stats?.items_invalidated ?? 0) > 0">
                （其中 {{ scenario.incremental_regen.review_stats?.items_invalidated }} 条原已确认，因材料变更已重置）
              </template>。
            </p>
          </div>

          <div class="disclaimer-banner">
            <template v-if="auth.isLegal">
              请对每条核查项作出确认或驳回，并可在批注栏补充意见。全部处理完成后方可定稿并导出{{ exportDocxLabel }}。
            </template>
            <template v-else>
              本页仅供查看复核进度。确认、定稿与导出须由法务角色操作。
            </template>
          </div>

      <p class="error banner-error" v-if="error">{{ error }}</p>

      <div class="review-toolbar panel" v-if="reviewSections.length">
        <div class="review-toolbar-filters">
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
        <span class="review-toolbar-meta">
          共 {{ reviewSections.length }} 个合规维度 · 已展开 {{ openSectionCount }} 个 ·
          {{ filteredItems.length }} 条核查项 · 已展开 {{ openReviewItemCount }} 条
        </span>
        <div class="review-toolbar-actions">
          <button type="button" class="toolbar-btn" @click="setAllSections(true)">展开全部维度</button>
          <button type="button" class="toolbar-btn" @click="setAllSections(false)">折叠全部维度</button>
          <button type="button" class="toolbar-btn" @click="setAllReviewItems(true)">展开全部条目</button>
          <button type="button" class="toolbar-btn" @click="setAllReviewItems(false)">折叠全部条目</button>
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
                    <span v-if="item.carry_forward && item.decision === 'approved'" class="badge ok sm">沿用</span>
                    <span v-if="item.invalidated" class="badge warn sm">材料变更</span>
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
                        <span
                          v-if="cite.citation_status"
                          class="badge"
                          :class="cite.citation_status === 'corpus_verified' ? 'ok' : 'warn'"
                        >
                          {{ cite.citation_status === 'corpus_verified' ? '已验' : cite.citation_status === 'weak_grounding' ? '弱引证' : '待核对' }}
                          <template v-if="cite.grounding_score"> · {{ Math.round(cite.grounding_score * 100) }}%</template>
                        </span>
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
                          <span
                            v-if="hit.citation_status"
                            class="badge"
                            :class="hit.citation_status === 'corpus_verified' ? 'ok' : 'warn'"
                          >
                            {{ hit.citation_status === 'corpus_verified' ? 'grounding 已验' : '待核对' }}
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

      <p class="muted panel" v-if="review && !reviewSections.length">当前筛选下暂无条目。</p>
        </section>
        <section v-else class="panel review-section-pending">
          <p class="muted">协查包已生成，正在加载复核条目…</p>
        </section>
      </template>

      <section v-if="showScopePanel" class="panel review-section-pending">
        <h2>② 统一复核</h2>
        <p class="muted">协查包生成完成后，Gate A 与清单条目复核将自动出现在下方。</p>
      </section>

      <p class="error banner-error" v-if="error && scenario">{{ error }}</p>
    </template>
  </div>
</template>
