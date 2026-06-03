<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  approveAllReview,
  downloadDocxExport,
  downloadPdfExport,
  fetchReview,
  fetchScenario,
  finalizeReview,
  initReview,
  updateReviewItem,
} from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { ReviewState, Scenario } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const scenario = ref<Scenario | null>(null)
const review = ref<ReviewState | null>(null)
const loading = ref(true)
const saving = ref<string | null>(null)
const finalizing = ref(false)
const exporting = ref(false)
const exportingPdf = ref(false)
const error = ref<string | null>(null)
const comments = ref<Record<string, string>>({})

const statusLabel: Record<string, string> = {
  in_progress: '复核中',
  approved: '已全部确认',
  partial: '部分确认',
  rejected: '已驳回',
}

const isLocked = computed(() =>
  review.value ? !['in_progress'].includes(review.value.status) || !auth.isLegal : true,
)

onMounted(async () => {
  const id = Number(route.params.id)
  try {
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

async function runExportPdf() {
  if (!scenario.value || !review.value?.can_export) return
  exportingPdf.value = true
  error.value = null
  try {
    const blob = await downloadPdfExport(scenario.value.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${scenario.value.project_name}_协查底稿.pdf`
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
    const blob = await downloadDocxExport(scenario.value.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${scenario.value.project_name}_协查底稿.docx`
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
            {{ exporting ? '导出中…' : '导出 Word' }}
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
          请对每条核查项作出确认或驳回，并可在批注栏补充意见。全部处理完成后方可定稿并导出协查底稿。
        </template>
        <template v-else>
          本页仅供查看复核进度。确认、定稿与导出须由法务角色操作。
        </template>
      </div>

      <p class="error banner-error" v-if="error">{{ error }}</p>

      <section class="review-items panel">
        <article v-for="item in review.items" :key="item.code" class="review-item" :class="item.decision">
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
          <div class="review-actions" v-if="!isLocked">
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
        </article>
      </section>

      <div class="next-step panel" v-if="review.can_export">
        <h2>样本已完成</h2>
        <p class="muted">协查底稿已定稿，可导出 Word 文件作为完整样本交付物。</p>
        <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
      </div>
    </template>
  </div>
</template>
