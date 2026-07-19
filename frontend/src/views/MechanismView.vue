<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import {
  compileMechanismClaims,
  confirmFactRecord,
  confirmMechanismClaim,
  createCoverageProof,
  createFactRecord,
  fetchFactRecords,
  fetchDeliveryGateStatus,
  fetchLatestClaimCompilation,
  fetchLatestCoverageProof,
  fetchMaterialLedger,
  fetchMechanismCoverageTasks,
  fetchScenario,
} from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type {
  ClaimCompilation,
  ClaimDraft,
  ClaimRecord,
  CoverageProof,
  CoverageTask,
  DeliveryGateStatus,
  FactRecord,
  FactRecordCreatePayload,
  MaterialLedgerEntry,
} from '@/types/mechanism'
import type { ChecklistItem, LegalHit, Scenario } from '@/types/scenario'

type ClaimDraftEditor = {
  statement: string
  factRefs: string[]
  evidenceRefs: string[]
  open: boolean
}

const route = useRoute()
const auth = useAuthStore()
const scenarioId = computed(() => Number(route.params.id))

const scenario = ref<Scenario | null>(null)
const ledger = ref<MaterialLedgerEntry[]>([])
const coverageTasks = ref<CoverageTask[]>([])
const facts = ref<FactRecord[]>([])
const compilation = ref<ClaimCompilation | null>(null)
const proof = ref<CoverageProof | null>(null)
const deliveryStatus = ref<DeliveryGateStatus | null>(null)
const loading = ref(true)
const busy = ref<string | null>(null)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)

const factForm = reactive<FactRecordCreatePayload>({
  subject: '',
  attribute: '',
  value: '',
  fact_time: '',
  block_id: '',
  fact_pack_version: '',
  source_document: '',
  assertion_polarity: 'unspecified',
})
const factConfirmationNotes = reactive<Record<string, string>>({})
const claimDecisionNotes = reactive<Record<string, string>>({})
const draftEditors = reactive<Record<string, ClaimDraftEditor>>({})

const materialStateLabels: Record<string, string> = {
  missing: '缺失',
  received: '已收到',
  unreadable: '不可读取',
  ambiguous: '存在歧义',
  verified: '法务已核验',
  not_applicable: '法务确认不适用',
}

const claimStatusLabels: Record<string, string> = {
  refused: '不可回答 / 已拒绝',
  awaiting_human_confirmation: '待法务人工确认',
  supported: '法务已确认支持',
}

const reasonLabels: Record<string, string> = {
  fact_reference_required: '缺少业务事实引用',
  evidence_reference_required: '缺少法源证据引用',
  human_rejected: '法务人工驳回',
}

const checklistItems = computed(() =>
  (scenario.value?.checklist?.sections || []).flatMap((section) => section.items),
)

const checklistItemByCode = computed(() =>
  new Map(checklistItems.value.map((item) => [item.code, item])),
)

const confirmedFacts = computed(() => facts.value.filter((fact) => fact.status === 'business_confirmed'))
const submittedFacts = computed(() => facts.value.filter((fact) => fact.status === 'submitted'))
const supportedClaims = computed(
  () => compilation.value?.claims.filter((claim) => claim.status === 'supported') || [],
)
const awaitingClaims = computed(
  () => compilation.value?.claims.filter((claim) => claim.status === 'awaiting_human_confirmation') || [],
)
const researchItems = computed(() => compilation.value?.research_items || [])
const inScopeResearchItems = computed(() =>
  researchItems.value.filter((item) => item.scope_status === 'in_scope'),
)
const outOfScopeResearchItems = computed(() =>
  researchItems.value.filter((item) => item.scope_status === 'out_of_scope_by_scope'),
)

const proofMatchesLatestCompilation = computed(
  () => !!proof.value && !!compilation.value && proof.value.compilation_id === compilation.value.id,
)

const mechanismGatePassed = computed(
  () => {
    if (!proof.value || !proofMatchesLatestCompilation.value) return false
    if (proof.value.proof.schema_version === '0.2') {
      const body = proof.value.proof
      return (
        body.pack_total === 30 &&
        body.pack_total === (body.scope_total || 0) + (body.out_of_scope_by_scope_count || 0) &&
        body.scope_total ===
          (body.supported_count || 0) +
            (body.not_applicable_count || 0) +
            (body.rejected_count || 0) +
            (body.unanswerable_count || 0) +
            (body.uncovered_count || 0)
      )
    }
    return (
      proof.value.denominator_count > 0 &&
      proof.value.covered_count + proof.value.unanswerable_count === proof.value.denominator_count &&
      proof.value.uncovered_count === proof.value.unanswerable_count
    )
  },
)

const deliveryAllowed = computed(() => deliveryStatus.value?.delivery_allowed === true)
const deliveryBlockLabel = computed(() => {
  if (!deliveryStatus.value) return '交付门状态尚不可用'
  if (deliveryStatus.value.delivery_allowed) return '全部外部证据当前有效，已获限时客户交付许可'
  return deliveryStatus.value.blocking_reasons.length
    ? `阻断：${deliveryStatus.value.blocking_reasons.join('；')}`
    : '缺少 active customer delivery release'
})

const finalReviewApproved = computed(() => scenario.value?.status === 'review_approved')

const evidenceByRef = computed(() => {
  const values = new Map<string, LegalHit>()
  for (const item of checklistItems.value) {
    for (const hit of item.legal_hits || []) {
      const hitId = String(hit.id || hit.urn || '').trim()
      if (hitId) values.set(`${item.code}:${hitId}`, hit)
    }
  }
  return values
})

const supportedEvidenceIsExpertVerified = computed(() => {
  if (!supportedClaims.value.length) return false
  return supportedClaims.value.every(
    (claim) =>
      claim.evidence_refs.length > 0 &&
      claim.evidence_refs.every(
        (reference) => evidenceByRef.value.get(reference)?.review_status === 'expert_verified',
      ),
  )
})

const sourceVerificationLabel = computed(() => {
  if (!supportedClaims.value.length) return '尚无 supported Claim'
  return supportedEvidenceIsExpertVerified.value
    ? '当前 supported Claim 的法源均标记为 expert_verified'
    : '仍含 provisional、pending 或无法核对的法源'
})

const factPackVersion = computed(() =>
  scenario.value?.scenario_scope?.snapshot?.capability_pack_version ||
  scenario.value?.checklist?.version ||
  '',
)

const canSubmitFact = computed(
  () =>
    auth.isBusiness &&
    factForm.subject.trim().length > 0 &&
    factForm.attribute.trim().length > 0 &&
    factForm.value.trim().length > 0 &&
    factForm.fact_time.trim().length > 0 &&
    factForm.block_id.trim().length > 0 &&
    factForm.fact_pack_version.trim().length > 0,
)

function evidenceRef(item: ChecklistItem, hit: LegalHit): string {
  return `${item.code}:${String(hit.id || hit.urn || '').trim()}`
}

function evidenceEligible(hit: LegalHit): boolean {
  return hit.grounded === true
}

function sourceReviewLabel(hit: LegalHit): string {
  const labels: Record<string, string> = {
    expert_verified: '专家已核验法源',
    provisional: '临时法源',
    pending: '待审核法源',
    quarantined: '隔离法源',
  }
  return labels[hit.review_status || 'pending'] || '待审核法源'
}

function sourceReviewClass(hit: LegalHit): string {
  return hit.review_status === 'expert_verified' ? 'expert' : 'provisional'
}

function reasonLabel(reason: string): string {
  if (reasonLabels[reason]) return reasonLabels[reason]
  if (reason.startsWith('fact_not_verified:')) return `业务事实尚未确认：${reason.split(':')[1]}`
  if (reason.startsWith('fact_reference_not_found:')) return `事实引用不存在：${reason.split(':')[1]}`
  if (reason.startsWith('evidence_reference_not_found:')) return `证据引用不存在：${reason.split(':')[1]}`
  if (reason.startsWith('evidence_wrong_checklist_item:')) return `证据不属于该清单项：${reason.split(':')[1]}`
  if (reason.startsWith('evidence_not_grounded:')) return `证据未通过 grounding：${reason.split(':')[1]}`
  return reason
}

function initDraftEditors() {
  for (const item of checklistItems.value) {
    if (!draftEditors[item.code]) {
      draftEditors[item.code] = {
        statement: '',
        factRefs: [],
        evidenceRefs: [],
        open: false,
      }
    }
  }
}

async function loadPage() {
  loading.value = true
  error.value = null
  try {
    const [loadedScenario, loadedLedger, loadedTasks, loadedFacts, loadedCompilation, loadedProof, loadedDeliveryStatus] =
      await Promise.all([
        fetchScenario(scenarioId.value),
        fetchMaterialLedger(scenarioId.value),
        fetchMechanismCoverageTasks(scenarioId.value),
        fetchFactRecords(scenarioId.value),
        fetchLatestClaimCompilation(scenarioId.value),
        fetchLatestCoverageProof(scenarioId.value),
        fetchDeliveryGateStatus(scenarioId.value),
      ])
    scenario.value = loadedScenario
    ledger.value = loadedLedger
    coverageTasks.value = loadedTasks
    facts.value = loadedFacts
    compilation.value = loadedCompilation
    proof.value = loadedProof
    deliveryStatus.value = loadedDeliveryStatus
    factForm.fact_pack_version = factPackVersion.value
    initDraftEditors()
  } catch (cause: unknown) {
    error.value = extractError(cause, '无法加载保证机制工作台')
  } finally {
    loading.value = false
  }
}

onMounted(loadPage)

async function submitFact() {
  if (!canSubmitFact.value) return
  busy.value = 'fact-create'
  error.value = null
  notice.value = null
  try {
    const created = await createFactRecord(scenarioId.value, {
      ...factForm,
      source_document: factForm.source_document?.trim() || null,
    })
    facts.value = [...facts.value, created]
    factForm.subject = ''
    factForm.attribute = ''
    factForm.value = ''
    factForm.fact_time = ''
    factForm.block_id = ''
    factForm.source_document = ''
    factForm.assertion_polarity = 'unspecified'
    notice.value = '事实已登记。只有业务登记人再次确认后，Claim Compiler 才会把它视为已确认事实。'
  } catch (cause: unknown) {
    error.value = extractError(cause, '事实登记失败')
  } finally {
    busy.value = null
  }
}

async function confirmFact(fact: FactRecord) {
  const note = (factConfirmationNotes[fact.id] || '').trim()
  if (note.length < 3) return
  busy.value = `fact-confirm-${fact.id}`
  error.value = null
  notice.value = null
  try {
    const updated = await confirmFactRecord(scenarioId.value, fact.id, note)
    facts.value = facts.value.map((entry) => (entry.id === fact.id ? updated : entry))
    factConfirmationNotes[fact.id] = ''
    notice.value = '业务事实已人工确认；此操作只确认事实陈述，不确认法律结论。'
  } catch (cause: unknown) {
    error.value = extractError(cause, '事实确认失败')
  } finally {
    busy.value = null
  }
}

function compilationDrafts(): ClaimDraft[] {
  return checklistItems.value.flatMap((item) => {
    const editor = draftEditors[item.code]
    if (!editor) return []
    const statement = editor.statement.trim()
    if (!statement) return []
    return [
      {
        checklist_code: item.code,
        statement,
        fact_refs: [...editor.factRefs],
        evidence_refs: [...editor.evidenceRefs],
      },
    ]
  })
}

async function compileClaims() {
  busy.value = 'claims-compile'
  error.value = null
  notice.value = null
  try {
    compilation.value = await compileMechanismClaims(scenarioId.value, compilationDrafts())
    proof.value = null
    notice.value = '已按固定 30 项 Pack 分母重新编译。无真实法务草稿的项目只创建 ResearchItem，不创建占位 Claim。'
  } catch (cause: unknown) {
    error.value = extractError(cause, 'Claim 编译失败')
  } finally {
    busy.value = null
  }
}

async function decideClaim(claim: ClaimRecord, decision: 'confirmed' | 'rejected') {
  const note = (claimDecisionNotes[claim.id] || '').trim()
  if (note.length < 3) return
  busy.value = `claim-${claim.id}`
  error.value = null
  notice.value = null
  try {
    const updated = await confirmMechanismClaim(
      scenarioId.value,
      claim.id,
      decision,
      note,
    )
    if (compilation.value) {
      compilation.value = {
        ...compilation.value,
        claims: compilation.value.claims.map((entry) => (entry.id === claim.id ? updated : entry)),
      }
    }
    proof.value = null
    claimDecisionNotes[claim.id] = ''
    notice.value =
      decision === 'confirmed'
        ? '该 Claim 已由法务人工确认支持；仍需生成新的 CoverageProof 才能更新覆盖状态。'
        : '该 Claim 已由法务人工驳回，将在 CoverageProof 中保持未覆盖。'
  } catch (cause: unknown) {
    error.value = extractError(cause, 'Claim 决策失败')
  } finally {
    busy.value = null
  }
}

async function generateProof() {
  if (!compilation.value) return
  busy.value = 'coverage-proof'
  error.value = null
  notice.value = null
  try {
    proof.value = await createCoverageProof(scenarioId.value, compilation.value.id)
    notice.value = 'CoverageProof 已生成。只有 supported Claim 被计入 covered。'
  } catch (cause: unknown) {
    error.value = extractError(cause, 'CoverageProof 生成失败')
  } finally {
    busy.value = null
  }
}

function extractError(cause: unknown, fallback: string): string {
  if (typeof cause === 'object' && cause !== null && 'response' in cause) {
    const response = (cause as { response?: { data?: { detail?: string } } }).response
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return fallback
}
</script>

<template>
  <div class="mechanism-page page-stack">
    <div v-if="loading" class="muted">加载保证机制工作台…</div>
    <div v-else-if="!scenario" class="error banner-error">
      {{ error || '无法加载协查场景' }}
    </div>

    <template v-else>
      <header class="page-header">
        <div>
          <p class="eyebrow dark">保证机制工作台 · 事实 → Claim → CoverageProof</p>
          <h1>{{ scenario.project_name }}</h1>
          <p class="meta">
            {{ auth.isBusiness ? '业务事实确认视图' : '法务 Claim 与覆盖视图' }} ·
            清单分母 {{ checklistItems.length }} 项
          </p>
        </div>
        <div class="header-actions">
          <RouterLink
            v-if="auth.isLegal"
            :to="{ name: 'review', params: { id: scenario.id } }"
            class="btn-secondary link-btn"
          >返回法务复核</RouterLink>
          <RouterLink
            v-else
            :to="{ name: 'scenario-progress', params: { id: scenario.id } }"
            class="btn-secondary link-btn"
          >返回协查进度</RouterLink>
          <RouterLink
            :to="{ name: 'checklist', params: { id: scenario.id } }"
            class="btn-secondary link-btn"
          >查看冻结清单</RouterLink>
          <RouterLink
            :to="{ name: 'delivery-assurance', params: { id: scenario.id } }"
            class="btn-primary link-btn"
          >客户交付证据台</RouterLink>
          <RouterLink
            :to="{ name: 'competition-workspace', params: { id: scenario.id, section: 'overview' } }"
            class="btn-primary link-btn"
          >比赛正式场景</RouterLink>
        </div>
      </header>

      <div class="mechanism-disclaimer" role="note">
        <strong>不是正式法律意见。</strong>
        provisional 只表示法源尚待专家核验；supported 只表示某条 Claim 已由平台内法务人工确认。
        两者都不自动等于外部执业律师认证或客户交付许可。
      </div>

      <p v-if="error" class="error banner-error">{{ error }}</p>
      <p v-if="notice" class="mechanism-notice">{{ notice }}</p>

      <section class="panel readiness-panel" aria-labelledby="readiness-title">
        <div class="section-heading">
          <div>
            <h2 id="readiness-title">客户交付就绪度</h2>
            <p class="muted">本页只显示可由当前系统证实的门槛，不代替执业资格、委托范围与最终签发。</p>
          </div>
          <span class="readiness-status" :class="deliveryAllowed ? 'passed' : 'blocked'">
            {{ deliveryAllowed ? '已获限时客户交付许可' : '未获客户交付许可' }}
          </span>
        </div>
        <div class="readiness-grid">
          <div class="gate-card" :class="confirmedFacts.length ? 'passed' : 'blocked'">
            <strong>业务事实</strong>
            <span>{{ confirmedFacts.length }} 条已由业务登记人确认</span>
          </div>
          <div class="gate-card" :class="mechanismGatePassed ? 'passed' : 'blocked'">
            <strong>机制覆盖门</strong>
            <span v-if="proof && proofMatchesLatestCompilation">
              supported {{ proof.covered_count }}/{{ proof.denominator_count }}，未覆盖 {{ proof.uncovered_count }}
            </span>
            <span v-else>缺少与最新编译匹配的 CoverageProof</span>
          </div>
          <div class="gate-card" :class="supportedEvidenceIsExpertVerified ? 'passed' : 'blocked'">
            <strong>法源内容核验</strong>
            <span>{{ sourceVerificationLabel }}</span>
          </div>
          <div class="gate-card" :class="finalReviewApproved ? 'passed' : 'blocked'">
            <strong>平台法务定稿</strong>
            <span>{{ finalReviewApproved ? '复核流程已定稿' : '复核流程尚未定稿' }}</span>
          </div>
          <div class="gate-card external" :class="deliveryAllowed ? 'passed' : 'blocked'">
            <strong>客户交付发布链</strong>
            <span>{{ deliveryBlockLabel }}</span>
          </div>
        </div>
        <p v-if="mechanismGatePassed" class="gate-caution">
          机制层不存在待决 Claim；是否可交付仍以 OAB/双律师内容认证、ITI 签名、客户 UAT、gold 与 production evidence 的统一服务端状态为准。
        </p>
      </section>

      <section class="panel" aria-labelledby="ledger-title">
        <div class="section-heading">
          <div>
            <h2 id="ledger-title">材料账本</h2>
            <p class="muted">六状态记录材料块的真实处理状态；“已收到”不等于“已核验”。</p>
          </div>
          <span class="badge">{{ ledger.length }} 个材料块</span>
        </div>
        <div v-if="ledger.length" class="mechanism-table-wrap">
          <table class="mechanism-table">
            <thead>
              <tr><th>材料块</th><th>来源文件</th><th>状态</th><th>说明</th><th>版本</th></tr>
            </thead>
            <tbody>
              <tr v-for="entry in ledger" :key="entry.id">
                <td><code>{{ entry.block_id }}</code></td>
                <td>{{ entry.source_document }}</td>
                <td>
                  <span class="state-pill" :class="entry.state">{{ materialStateLabels[entry.state] }}</span>
                </td>
                <td>{{ entry.confirmation_note || entry.note || '—' }}</td>
                <td>r{{ entry.revision }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty-state">尚无材料账本条目。该空状态不代表材料齐全。</p>
      </section>

      <section class="panel" aria-labelledby="facts-title">
        <div class="section-heading">
          <div>
            <h2 id="facts-title">业务事实记录</h2>
            <p class="muted">事实由场景业务提交人登记并二次确认；法务只能查看，不能替业务确认事实。</p>
          </div>
          <span class="badge">已确认 {{ confirmedFacts.length }} · 待确认 {{ submittedFacts.length }}</span>
        </div>

        <form v-if="auth.isBusiness" class="fact-form" @submit.prevent="submitFact">
          <label>
            <span>主体</span>
            <input v-model="factForm.subject" data-testid="fact-subject" type="text" maxlength="512" placeholder="例如：项目公司" />
          </label>
          <label>
            <span>属性</span>
            <input v-model="factForm.attribute" data-testid="fact-attribute" type="text" maxlength="512" placeholder="例如：预计用地面积" />
          </label>
          <label class="wide">
            <span>事实值</span>
            <textarea v-model="factForm.value" data-testid="fact-value" rows="2" maxlength="10000" placeholder="只填写可由材料或业务确认的事实，不填写法律结论" />
          </label>
          <label>
            <span>事实时点</span>
            <input v-model="factForm.fact_time" data-testid="fact-time" type="text" maxlength="128" placeholder="例如：2026-07-18 / 截至提交日" />
          </label>
          <label>
            <span>材料块 ID</span>
            <input v-model="factForm.block_id" data-testid="fact-block" type="text" maxlength="255" placeholder="例如：site-area" />
          </label>
          <label>
            <span>事实包版本</span>
            <input v-model="factForm.fact_pack_version" data-testid="fact-version" type="text" maxlength="64" />
          </label>
          <label>
            <span>来源文件（可选）</span>
            <input v-model="factForm.source_document" data-testid="fact-source" type="text" maxlength="512" placeholder="文件名或业务系统记录" />
          </label>
          <label>
            <span>事实极性</span>
            <select v-model="factForm.assertion_polarity" data-testid="fact-polarity">
              <option value="unspecified">未指定</option>
              <option value="affirmative">肯定事实</option>
              <option value="negative">否定事实（可供 not_applicable 审核）</option>
            </select>
          </label>
          <div class="wide form-action-row">
            <button class="btn-primary" data-testid="create-fact" type="submit" :disabled="!canSubmitFact || busy === 'fact-create'">
              {{ busy === 'fact-create' ? '登记中…' : '登记待确认事实' }}
            </button>
          </div>
        </form>

        <div v-if="facts.length" class="fact-list">
          <article v-for="fact in facts" :key="fact.id" class="fact-card">
            <div class="fact-card-head">
              <strong>{{ fact.subject }} · {{ fact.attribute }}</strong>
              <span class="state-pill" :class="fact.status">
                {{ fact.status === 'business_confirmed' ? '业务已确认' : '待业务确认' }}
              </span>
            </div>
            <p class="fact-value">{{ fact.value }}</p>
            <p class="muted">
              时点 {{ fact.fact_time }} · block <code>{{ fact.block_id }}</code> · pack {{ fact.fact_pack_version }}
              <template v-if="fact.source_document"> · 来源 {{ fact.source_document }}</template>
            </p>
            <p v-if="fact.confirmation_note" class="confirmation-note">确认说明：{{ fact.confirmation_note }}</p>
            <div v-if="auth.isBusiness && fact.status === 'submitted'" class="inline-decision">
              <label>
                <span>确认说明（至少 3 字）</span>
                <input
                  v-model="factConfirmationNotes[fact.id]"
                  :data-testid="`fact-note-${fact.id}`"
                  type="text"
                  maxlength="5000"
                  placeholder="说明核对材料或业务系统的依据"
                />
              </label>
              <button
                type="button"
                class="btn-secondary"
                :data-testid="`confirm-fact-${fact.id}`"
                :disabled="(factConfirmationNotes[fact.id] || '').trim().length < 3 || busy === `fact-confirm-${fact.id}`"
                @click="confirmFact(fact)"
              >确认该业务事实</button>
            </div>
          </article>
        </div>
        <p v-else class="empty-state">尚无业务事实。没有事实时，Claim Compiler 会拒绝形成支持性结论。</p>
      </section>

      <section v-if="auth.isLegal" class="panel" aria-labelledby="compiler-title">
        <div class="section-heading">
          <div>
            <h2 id="compiler-title">Claim Compiler</h2>
            <p class="muted">
              逐项绑定已确认事实与同一清单项的 grounded 法源。未形成真实法务草稿的 Pack 项仍进入 30 项分母，但只生成 ResearchItem。
            </p>
          </div>
          <button
            type="button"
            class="btn-primary"
            data-testid="compile-claims"
            :disabled="busy === 'claims-compile' || !checklistItems.length"
            @click="compileClaims"
          >{{ busy === 'claims-compile' ? '编译中…' : '按完整清单编译 Claims' }}</button>
        </div>

        <div class="source-legend">
          <span class="source-status expert">expert_verified：内容已通过专家核验</span>
          <span class="source-status provisional">provisional/pending：仅可供法务评估，不能自动成为 supported</span>
          <span class="source-status ungrounded">未 grounded：不可选择</span>
        </div>

        <div class="draft-list">
          <article v-for="item in checklistItems" :key="item.code" class="draft-card">
            <button
              type="button"
              class="draft-toggle"
              :aria-expanded="draftEditors[item.code]?.open"
              @click="draftEditors[item.code].open = !draftEditors[item.code].open"
            >
              <span><code>{{ item.code }}</code> {{ item.title }}</span>
              <span>{{ draftEditors[item.code]?.open ? '收起' : '配置 Claim' }}</span>
            </button>
            <div v-if="draftEditors[item.code]?.open" class="draft-body">
              <label class="wide">
                <span>拟形成的陈述</span>
                <textarea v-model="draftEditors[item.code].statement" rows="2" maxlength="10000" placeholder="写明有限、可核验的法律陈述；不要写绝对保证" />
              </label>

              <fieldset>
                <legend>业务事实引用</legend>
                <p v-if="!facts.length" class="muted">尚无事实可引用。</p>
                <label v-for="fact in facts" :key="fact.id" class="choice-row" :class="{ disabled: fact.status !== 'business_confirmed' }">
                  <input
                    v-model="draftEditors[item.code].factRefs"
                    type="checkbox"
                    :value="fact.id"
                    :disabled="fact.status !== 'business_confirmed'"
                  />
                  <span>{{ fact.subject }} · {{ fact.attribute }}：{{ fact.value }}</span>
                  <small>{{ fact.status === 'business_confirmed' ? '业务已确认' : '待业务确认，不可引用' }}</small>
                </label>
              </fieldset>

              <fieldset>
                <legend>法源证据引用</legend>
                <p v-if="!item.legal_hits?.length" class="muted">该清单项没有法源命中；系统将拒答。</p>
                <label
                  v-for="hit in item.legal_hits || []"
                  :key="evidenceRef(item, hit)"
                  class="choice-row"
                  :class="{ disabled: !evidenceEligible(hit) }"
                >
                  <input
                    v-model="draftEditors[item.code].evidenceRefs"
                    type="checkbox"
                    :value="evidenceRef(item, hit)"
                    :disabled="!evidenceEligible(hit)"
                  />
                  <span>{{ hit.title_zh || hit.title_pt || hit.urn }}</span>
                  <small class="source-status" :class="sourceReviewClass(hit)">
                    {{ sourceReviewLabel(hit) }} · {{ hit.grounded ? 'grounded' : '未 grounded' }}
                  </small>
                </label>
              </fieldset>
            </div>
          </article>
        </div>
      </section>

      <section v-if="compilation" class="panel" aria-labelledby="research-denominator-title">
        <div class="section-heading">
          <div>
            <h2 id="research-denominator-title">固定 Pack 分母与 ResearchItem</h2>
            <p class="muted">Scope 和 screening 只标记状态，不会从 30 项分母删除条目。</p>
          </div>
          <span class="badge">Pack {{ researchItems.length }} · in-scope {{ inScopeResearchItems.length }} · out-of-scope {{ outOfScopeResearchItems.length }}</span>
        </div>
        <div class="fact-list">
          <article v-for="item in researchItems" :key="item.id" class="fact-card">
            <div class="fact-card-head">
              <strong><code>{{ item.checklist_code }}</code> {{ item.title }}</strong>
              <span class="state-pill" :class="item.scope_status === 'in_scope' ? 'business_confirmed' : 'submitted'">
                {{ item.scope_status }}
              </span>
            </div>
            <p class="muted">
              {{ item.dimension }} · {{ item.screening_status }} · disposition {{ item.disposition || '—' }}
            </p>
            <p v-if="item.reason_codes.length" class="confirmation-note">{{ item.reason_codes.join('；') }}</p>
          </article>
        </div>
      </section>

      <section class="panel" aria-labelledby="claims-title">
        <div class="section-heading">
          <div>
            <h2 id="claims-title">最新 Claim 编译结果</h2>
            <p class="muted">
              supported 只能来自法务逐条人工确认；awaiting 和 refused 均不计入覆盖。
            </p>
          </div>
          <span v-if="compilation" class="badge">
            supported {{ supportedClaims.length }} · 待确认 {{ awaitingClaims.length }} · 分母 {{ compilation.denominator_count }}
          </span>
        </div>

        <div v-if="compilation" class="claim-list">
          <article v-for="claim in compilation.claims" :key="claim.id" class="claim-card" :class="claim.status">
            <div class="claim-card-head">
              <strong><code>{{ claim.checklist_code }}</code> {{ checklistItemByCode.get(claim.checklist_code)?.title }}</strong>
              <span class="claim-status" :class="claim.status">{{ claimStatusLabels[claim.status] }}</span>
            </div>
            <p>{{ claim.statement }}</p>
            <p class="muted">事实引用 {{ claim.fact_refs.length }} · 证据引用 {{ claim.evidence_refs.length }}</p>
            <ul v-if="claim.reason_codes.length" class="reason-list">
              <li v-for="reason in claim.reason_codes" :key="reason">{{ reasonLabel(reason) }}</li>
            </ul>
            <p v-if="claim.confirmation_note" class="confirmation-note">人工决策说明：{{ claim.confirmation_note }}</p>

            <div v-if="auth.isLegal && claim.status === 'awaiting_human_confirmation'" class="claim-decision">
              <label>
                <span>人工决策依据（至少 3 字）</span>
                <textarea
                  v-model="claimDecisionNotes[claim.id]"
                  :data-testid="`claim-note-${claim.id}`"
                  rows="2"
                  maxlength="5000"
                  placeholder="说明事实、法源定位、限制条件与仍需外部核验的事项"
                />
              </label>
              <div class="decision-actions">
                <button
                  type="button"
                  class="btn-primary"
                  :data-testid="`support-claim-${claim.id}`"
                  :disabled="(claimDecisionNotes[claim.id] || '').trim().length < 3 || busy === `claim-${claim.id}`"
                  @click="decideClaim(claim, 'confirmed')"
                >人工确认支持</button>
                <button
                  type="button"
                  class="btn-secondary reject"
                  :disabled="(claimDecisionNotes[claim.id] || '').trim().length < 3 || busy === `claim-${claim.id}`"
                  @click="decideClaim(claim, 'rejected')"
                >驳回 / 保持不可回答</button>
              </div>
            </div>
          </article>
        </div>
        <p v-else class="empty-state">
          尚未编译 Claim。此状态不得解释为“没有风险”或“清单已覆盖”。
        </p>
      </section>

      <section class="panel" aria-labelledby="coverage-title">
        <div class="section-heading">
          <div>
            <h2 id="coverage-title">CoverageProof</h2>
            <p class="muted">覆盖分子只统计 supported Claim；哈希用于固定本次分母与证明内容。</p>
          </div>
          <button
            v-if="auth.isLegal"
            type="button"
            class="btn-primary"
            data-testid="generate-proof"
            :disabled="!compilation || busy === 'coverage-proof'"
            @click="generateProof"
          >{{ busy === 'coverage-proof' ? '生成中…' : '基于最新编译生成证明' }}</button>
        </div>

        <div v-if="proof" class="proof-summary" :class="{ stale: !proofMatchesLatestCompilation }">
          <div><span>分母</span><strong>{{ proof.denominator_count }}</strong></div>
          <div><span>已覆盖</span><strong>{{ proof.covered_count }}</strong></div>
          <div><span>未覆盖</span><strong>{{ proof.uncovered_count }}</strong></div>
          <div><span>不可回答</span><strong>{{ proof.unanswerable_count }}</strong></div>
          <p v-if="!proofMatchesLatestCompilation" class="proof-warning">
            该证明不对应最新 Claim 编译，必须重新生成。
          </p>
          <p class="proof-hash"><span>Proof SHA-256</span><code>{{ proof.proof_hash }}</code></p>
          <div v-if="proof.proof.uncovered?.length" class="proof-detail">
            <strong>未覆盖 / 不可回答条目</strong>
            <ul>
              <li v-for="item in proof.proof.uncovered" :key="item.checklist_code">
                <code>{{ item.checklist_code }}</code> · {{ claimStatusLabels[item.status] || item.status }}
                <span v-if="item.unanswerable_reasons.length">
                  — {{ item.unanswerable_reasons.map(reasonLabel).join('；') }}
                </span>
              </li>
            </ul>
          </div>
          <p v-if="proof.proof.answerability_rule" class="proof-rule">
            <strong>计入规则：</strong>{{ proof.proof.answerability_rule }}
          </p>
        </div>
        <p v-else class="empty-state">尚无 CoverageProof；不得宣称已完成清单覆盖。</p>

        <details v-if="coverageTasks.length" class="coverage-tasks">
          <summary>查看 {{ coverageTasks.length }} 个外部分母 CoverageTask</summary>
          <ul>
            <li v-for="task in coverageTasks" :key="task.id">
              <strong>{{ task.source }}</strong>：{{ task.covered_count }}/{{ task.denominator_count }}，缺失 {{ task.missing_count }}
              <small>{{ task.denominator_ref }}</small>
            </li>
          </ul>
        </details>
      </section>
    </template>
  </div>
</template>

<style scoped>
.mechanism-page {
  padding-bottom: 2rem;
}

.mechanism-disclaimer,
.mechanism-notice,
.gate-caution {
  border-radius: 10px;
  padding: 0.9rem 1rem;
  line-height: 1.6;
  font-size: 0.88rem;
}

.mechanism-disclaimer {
  border: 1px solid #f59e0b;
  color: #7c2d12;
  background: #fffbeb;
}

.mechanism-notice {
  border: 1px solid #86efac;
  color: #166534;
  background: #f0fdf4;
}

.section-heading,
.fact-card-head,
.claim-card-head,
.form-action-row,
.decision-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.section-heading h2 {
  margin-bottom: 0.25rem;
}

.readiness-status,
.state-pill,
.claim-status,
.source-status {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.2rem 0.55rem;
  font-size: 0.75rem;
  font-weight: 600;
}

.readiness-status.blocked,
.state-pill.missing,
.state-pill.unreadable,
.state-pill.ambiguous,
.claim-status.refused,
.source-status.ungrounded {
  color: #991b1b;
  background: #fee2e2;
}

.readiness-status.passed {
  color: #166534;
  background: #dcfce7;
}

.state-pill.received,
.state-pill.submitted,
.claim-status.awaiting_human_confirmation,
.source-status.provisional {
  color: #92400e;
  background: #fef3c7;
}

.state-pill.verified,
.state-pill.not_applicable,
.state-pill.business_confirmed,
.claim-status.supported,
.source-status.expert {
  color: #166534;
  background: #dcfce7;
}

.readiness-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}

.gate-card {
  border: 1px solid var(--border);
  border-left-width: 4px;
  border-radius: 8px;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.gate-card.passed { border-left-color: var(--ok); }
.gate-card.blocked { border-left-color: var(--err); }
.gate-card.external { grid-column: 1 / -1; }
.gate-card span { color: var(--muted); font-size: 0.82rem; line-height: 1.5; }

.gate-caution {
  margin-top: 0.8rem;
  color: #92400e;
  background: #fffbeb;
}

.mechanism-table-wrap { overflow-x: auto; margin-top: 0.75rem; }
.mechanism-table { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
.mechanism-table th,
.mechanism-table td { padding: 0.65rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
.mechanism-table th { color: var(--muted); font-size: 0.75rem; }

.fact-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 1rem 0;
  padding: 1rem;
  border-radius: 8px;
  background: var(--surface-alt);
}

.fact-form label,
.draft-body label,
.claim-decision label,
.inline-decision label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  color: var(--muted);
  font-size: 0.78rem;
}

.fact-form input,
.fact-form textarea,
.draft-body textarea,
.claim-decision textarea,
.inline-decision input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 0.6rem;
  color: var(--text);
  background: #fff;
  font: inherit;
}

.wide { grid-column: 1 / -1; }
.fact-list,
.claim-list,
.draft-list { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.75rem; }

.fact-card,
.claim-card,
.draft-card {
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 0.85rem;
}

.claim-card.supported { border-left: 4px solid var(--ok); }
.claim-card.refused { border-left: 4px solid var(--err); }
.claim-card.awaiting_human_confirmation { border-left: 4px solid #f59e0b; }

.fact-value { margin: 0.5rem 0; line-height: 1.55; }
.confirmation-note { margin-top: 0.5rem; color: #374151; font-size: 0.82rem; }
.inline-decision { display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 0.75rem; margin-top: 0.75rem; }

.draft-toggle {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  text-align: left;
  font-weight: 600;
}

.draft-toggle span:last-child { color: var(--primary-light); font-size: 0.78rem; white-space: nowrap; }
.draft-body { display: grid; gap: 0.9rem; margin-top: 0.8rem; padding-top: 0.8rem; border-top: 1px solid var(--border); }
.draft-body fieldset { border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; }
.draft-body legend { color: var(--primary); font-size: 0.8rem; font-weight: 600; padding: 0 0.3rem; }

.choice-row {
  display: grid !important;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.55rem !important;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text) !important;
  cursor: pointer;
}

.choice-row:last-child { border-bottom: 0; }
.choice-row.disabled { opacity: 0.6; cursor: not-allowed; }
.choice-row small { color: var(--muted); }
.source-legend { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }

.reason-list { margin: 0.5rem 0 0 1.25rem; color: #991b1b; font-size: 0.82rem; line-height: 1.55; }
.claim-decision { margin-top: 0.8rem; padding-top: 0.8rem; border-top: 1px dashed var(--border); }
.decision-actions { justify-content: flex-start; margin-top: 0.55rem; }

.proof-summary {
  margin-top: 0.8rem;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
}

.proof-summary > div { border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; }
.proof-summary > div span { display: block; color: var(--muted); font-size: 0.75rem; }
.proof-summary > div strong { font-size: 1.25rem; color: var(--primary); }
.proof-summary.stale { border: 1px solid #f59e0b; border-radius: 9px; padding: 0.75rem; }
.proof-warning { grid-column: 1 / -1; color: #92400e; }
.proof-hash { grid-column: 1 / -1; display: grid; gap: 0.25rem; font-size: 0.75rem; overflow-wrap: anywhere; }
.proof-hash span { color: var(--muted); }
.proof-detail,
.proof-rule { grid-column: 1 / -1; font-size: 0.8rem; line-height: 1.55; }
.proof-detail ul { margin: 0.4rem 0 0 1.25rem; color: #991b1b; }
.coverage-tasks { margin-top: 0.9rem; color: var(--muted); font-size: 0.82rem; }
.coverage-tasks li { display: grid; gap: 0.2rem; margin: 0.5rem 0 0 1.25rem; }
.empty-state { margin-top: 0.75rem; color: var(--muted); font-size: 0.84rem; font-style: italic; }

code { overflow-wrap: anywhere; }

@media (max-width: 760px) {
  .readiness-grid,
  .fact-form,
  .proof-summary { grid-template-columns: 1fr; }
  .gate-card.external,
  .wide,
  .proof-warning,
  .proof-hash,
  .proof-detail,
  .proof-rule { grid-column: auto; }
  .inline-decision { grid-template-columns: 1fr; }
  .choice-row { grid-template-columns: auto 1fr; }
  .choice-row small { grid-column: 2; }
}
</style>
