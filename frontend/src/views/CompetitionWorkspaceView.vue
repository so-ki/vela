<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import {
  fetchDeliveryGateStatus,
  fetchFactRecords,
  fetchLatestClaimCompilation,
  fetchLatestCoverageProof,
  fetchLatestResearchItems,
  fetchMaterialLedger,
  fetchMechanismAuditEvents,
  fetchScenario,
} from '@/api/client'
import type {
  ClaimCompilation,
  CoverageProof,
  DeliveryGateStatus,
  FactRecord,
  MaterialLedgerEntry,
  MechanismAuditEvent,
  ResearchItem,
} from '@/types/mechanism'
import type { LegalHit, Scenario } from '@/types/scenario'

const POSITIONING = 'Vela 是面向中国企业法务的拉美投资前合规协查过程保证平台。本次以圣保罗州新能源绿地设厂为首个能力包，提供六维初步协查，其中环境许可为重点深度验证模块；不承诺市级完整覆盖、全巴西覆盖或实时完整更新。'

const route = useRoute()
const scenarioId = computed(() => Number(route.params.id))
const sections = [
  { id: 'overview', label: '项目总览', index: '01' },
  { id: 'materials', label: '材料与事实', index: '02' },
  { id: 'checklist', label: '固定 30 项', index: '03' },
  { id: 'research', label: '法律研究', index: '04' },
  { id: 'claims', label: 'Claim 与缺口', index: '05' },
  { id: 'coverage', label: 'CoverageProof', index: '06' },
  { id: 'delivery', label: '交付中心', index: '07' },
  { id: 'audit', label: '审计记录', index: '08' },
] as const
const activeSection = computed(() => {
  const requested = String(route.params.section || 'overview')
  return sections.some((item) => item.id === requested) ? requested : 'overview'
})

const scenario = ref<Scenario | null>(null)
const ledger = ref<MaterialLedgerEntry[]>([])
const facts = ref<FactRecord[]>([])
const compilation = ref<ClaimCompilation | null>(null)
const researchItems = ref<ResearchItem[]>([])
const proof = ref<CoverageProof | null>(null)
const delivery = ref<DeliveryGateStatus | null>(null)
const audit = ref<MechanismAuditEvent[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const activeResearchIndex = ref(0)

const scopeSnapshot = computed(() => scenario.value?.scenario_scope?.snapshot)
const activeResearch = computed(() => researchItems.value[activeResearchIndex.value] || null)
const claimById = computed(() =>
  new Map((compilation.value?.claims || []).map((claim) => [claim.id, claim])),
)
const checklistByCode = computed(() => {
  const entries = (scenario.value?.checklist?.sections || []).flatMap((section) =>
    section.items.map((item) => [item.code, item] as const),
  )
  return new Map(entries)
})
const activeEvidence = computed<LegalHit[]>(() => {
  if (!activeResearch.value) return []
  return checklistByCode.value.get(activeResearch.value.checklist_code)?.legal_hits || []
})
const inScope = computed(() => researchItems.value.filter((item) => item.scope_status === 'in_scope'))
const outOfScope = computed(() => researchItems.value.filter((item) => item.scope_status === 'out_of_scope_by_scope'))
const dispositionCounts = computed(() => {
  const result: Record<string, number> = {
    supported: 0,
    not_applicable: 0,
    rejected: 0,
    unanswerable: 0,
    uncovered: 0,
  }
  for (const item of inScope.value) {
    if (item.disposition) result[item.disposition] = (result[item.disposition] || 0) + 1
  }
  return result
})

function extractError(cause: unknown): string {
  if (typeof cause === 'object' && cause !== null && 'response' in cause) {
    const response = (cause as { response?: { data?: { detail?: string } } }).response
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return '无法读取正式场景 API 数据'
}

async function loadWorkspace() {
  loading.value = true
  error.value = null
  try {
    const [loadedScenario, loadedLedger, loadedFacts, loadedCompilation, loadedResearch, loadedProof, loadedDelivery, loadedAudit] =
      await Promise.all([
        fetchScenario(scenarioId.value),
        fetchMaterialLedger(scenarioId.value),
        fetchFactRecords(scenarioId.value),
        fetchLatestClaimCompilation(scenarioId.value),
        fetchLatestResearchItems(scenarioId.value),
        fetchLatestCoverageProof(scenarioId.value),
        fetchDeliveryGateStatus(scenarioId.value),
        fetchMechanismAuditEvents(scenarioId.value),
      ])
    scenario.value = loadedScenario
    ledger.value = loadedLedger
    facts.value = loadedFacts
    compilation.value = loadedCompilation
    researchItems.value = loadedResearch
    proof.value = loadedProof
    delivery.value = loadedDelivery
    audit.value = loadedAudit
  } catch (cause: unknown) {
    error.value = extractError(cause)
  } finally {
    loading.value = false
  }
}

onMounted(loadWorkspace)
</script>

<template>
  <div class="rc0-frame competition-frame">
    <aside class="rc0-sidebar" aria-label="比赛正式场景导航">
      <div class="rc0-sidebar__eyebrow">LIVE MATTER WORKSPACE</div>
      <div class="rc0-sidebar__matter">
        <span>SCENARIO {{ scenarioId }}</span>
        <strong>{{ scenario?.project_name || '读取中' }}</strong>
        <small>正式 API 数据 · 非硬编码输出</small>
      </div>
      <nav class="rc0-section-nav">
        <RouterLink
          v-for="section in sections"
          :key="section.id"
          :to="`/competition/${scenarioId}/${section.id}`"
          :class="{ active: activeSection === section.id }"
        ><span>{{ section.index }}</span>{{ section.label }}</RouterLink>
      </nav>
      <div class="rc0-sidebar__boundary">
        <span class="rc0-status rc0-status--progress">LIVE SCENARIO API</span>
        <p>当前页面只读正式服务产生的场景、事实、ResearchItem、Claim、Proof、Gate 与 audit。</p>
        <RouterLink to="/rc0/overview" class="competition-appendix-link">RC0 synthetic 机制附录</RouterLink>
      </div>
    </aside>

    <div class="rc0-workspace">
      <section class="competition-banner" aria-labelledby="competition-positioning">
        <div><span>决赛主演示 · 正式场景</span><h1 id="competition-positioning">{{ POSITIONING }}</h1></div>
        <span class="rc0-status rc0-status--blocked">{{ delivery?.delivery_allowed ? '限时交付已放行' : 'blocked_external' }}</span>
      </section>

      <header v-if="scenario" class="rc0-context-bar">
        <div class="rc0-context-bar__title"><span>当前项目</span><strong>{{ scenario.project_name }}</strong></div>
        <dl class="rc0-context-grid">
          <div><dt>法域</dt><dd>{{ scenario.country }} · {{ scenario.state }} · {{ scenario.city || '市级未承诺' }}</dd></div>
          <div><dt>行业 / 行动</dt><dd>{{ scenario.industry }} · {{ scenario.action_type }}</dd></div>
          <div><dt>Pack / Rules / Corpus</dt><dd><code>{{ scopeSnapshot?.capability_pack_version || '—' }} / {{ scopeSnapshot?.rules_artifact_version || '—' }} / {{ scopeSnapshot?.corpus_artifact_version || '—' }}</code></dd></div>
          <div><dt>Compiler / Proof</dt><dd><code>{{ compilation?.compiler_version || '—' }} / {{ proof?.proof.schema_version || '—' }}</code></dd></div>
          <div><dt>固定分母</dt><dd>{{ researchItems.length || '—' }} · Scope {{ inScope.length }} · Out {{ outOfScope.length }}</dd></div>
          <div><dt>Release Gate</dt><dd><span class="rc0-status rc0-status--blocked">{{ delivery?.delivery_allowed ? 'allowed' : 'blocked_external' }}</span></dd></div>
        </dl>
      </header>

      <main class="rc0-canvas">
        <div v-if="loading" class="competition-loading">Loading 正式场景 API…</div>
        <div v-else-if="error || !scenario" class="competition-error" role="alert">{{ error || '正式场景不存在' }}</div>

        <section v-else-if="activeSection === 'overview'" class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">FORMAL PROCESS ASSURANCE</span><h2>项目总览</h2><p>比赛工作台的每个数字均来自当前 scenario API；演示输入可以是合成企业材料，计算结果不是固定 demo 返回。</p></div><RouterLink :to="`/scenarios/${scenarioId}/mechanism`" class="rc0-button competition-action">进入正式机制工作台</RouterLink></div>
          <div class="rc0-metric-grid">
            <article class="rc0-metric"><span>Pack denominator</span><strong>{{ researchItems.length }}</strong><small>规则制品固定项</small></article>
            <article class="rc0-metric"><span>Business-confirmed facts</span><strong>{{ facts.filter((fact) => fact.status === 'business_confirmed').length }}</strong><small>正式事实确认</small></article>
            <article class="rc0-metric"><span>Real legal Claims</span><strong>{{ compilation?.claims.length || 0 }}</strong><small>仅真实法务草稿</small></article>
            <article class="rc0-metric rc0-metric--blocked"><span>External release</span><strong>{{ delivery?.delivery_allowed ? 'ALLOWED' : 'BLOCKED' }}</strong><small>不以工程测试替代外部证据</small></article>
          </div>
          <article class="rc0-panel"><div class="rc0-panel__heading"><div><span>HASH-BOUND STATE</span><h3>最新正式计算身份</h3></div></div><dl class="rc0-definition-list"><div><dt>Scope snapshot</dt><dd><code>{{ scopeSnapshot?.snapshot_hash || '—' }}</code></dd></div><div><dt>Compiler input</dt><dd><code>{{ compilation?.input_hash || '—' }}</code></dd></div><div><dt>Compiler output</dt><dd><code>{{ compilation?.output_hash || '—' }}</code></dd></div><div><dt>Coverage proof</dt><dd><code>{{ proof?.proof_hash || '—' }}</code></dd></div></dl></article>
        </section>

        <section v-else-if="activeSection === 'materials'" class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">FORMAL INTAKE</span><h2>材料与事实</h2><p>材料走正式上传/账本，事实走登记与业务确认；未确认事实不支持 Claim。</p></div><RouterLink :to="`/scenarios/${scenarioId}/extract`" class="rc0-button competition-action">查看正式材料抽取</RouterLink></div>
          <article class="rc0-panel rc0-table-panel"><table class="rc0-table"><caption>材料账本 API</caption><thead><tr><th>Block</th><th>来源</th><th>状态</th><th>确认</th><th>Revision</th></tr></thead><tbody><tr v-for="item in ledger" :key="item.id"><td><code>{{ item.block_id }}</code></td><td>{{ item.source_document }}</td><td>{{ item.state }}</td><td>{{ item.confirmation_note || '—' }}</td><td>r{{ item.revision }}</td></tr><tr v-if="!ledger.length"><td colspan="5">尚无账本记录；空状态不表示材料齐全。</td></tr></tbody></table></article>
          <article class="rc0-panel rc0-table-panel"><table class="rc0-table"><caption>事实登记/确认 API</caption><thead><tr><th>主体 / 属性</th><th>值</th><th>极性</th><th>时点 / 来源</th><th>确认</th></tr></thead><tbody><tr v-for="fact in facts" :key="fact.id"><td>{{ fact.subject }}<small>{{ fact.attribute }}</small></td><td>{{ fact.value }}</td><td>{{ fact.assertion_polarity }}</td><td>{{ fact.fact_time }}<small><code>{{ fact.block_id }}</code></small></td><td>{{ fact.status }}</td></tr><tr v-if="!facts.length"><td colspan="5">尚无正式事实；Gate 应拒答。</td></tr></tbody></table></article>
        </section>

        <section v-else-if="activeSection === 'checklist'" class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">FIXED PACK DENOMINATOR</span><h2>固定 30 项</h2><p>Scope、trigger、subsector 和 screening 均不会改变分母。未选维度只能是 out_of_scope_by_scope。</p></div><span class="rc0-version-chip">Pack {{ researchItems.length }} / Scope {{ inScope.length }} / Out {{ outOfScope.length }}</span></div>
          <div class="rc0-checklist-list"><article v-for="item in researchItems" :key="item.id" class="rc0-checklist-row"><div class="rc0-checklist-row__code"><code>{{ item.checklist_code }}</code><span>#{{ item.denominator_order }}</span></div><div><small>{{ item.dimension }}</small><h3>{{ item.title }}</h3><p>{{ item.screening_status }} · {{ item.reason_codes.join('；') || '无原因码' }}</p></div><div><span :class="['rc0-status', item.scope_status === 'in_scope' ? 'rc0-status--progress' : 'rc0-status--readonly']">{{ item.scope_status }}</span></div><div><small>Disposition</small><strong>{{ item.disposition || '—' }}</strong></div></article></div>
        </section>

        <section v-else-if="activeSection === 'research'" class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">RESEARCHITEM LEDGER</span><h2>法律研究</h2><p>ResearchItem 与 ClaimRecord 分离；无真实法务草稿时不会产生占位 Claim。</p></div></div>
          <div class="rc0-research-grid">
            <nav class="rc0-research-items" aria-label="ResearchItems"><h3>固定分母项</h3><button v-for="(item, index) in researchItems" :key="item.id" type="button" :aria-pressed="activeResearchIndex === index" :class="{ active: activeResearchIndex === index }" @click="activeResearchIndex = index"><code>{{ item.checklist_code }}</code><span>{{ item.title }}</span></button></nav>
            <article v-if="activeResearch" class="rc0-research-rule"><span class="rc0-column-label">Scope / Disposition / Claim</span><h3>{{ activeResearch.title }}</h3><dl class="rc0-definition-list"><div><dt>Scope</dt><dd>{{ activeResearch.scope_status }}</dd></div><div><dt>Screening</dt><dd>{{ activeResearch.screening_status }}</dd></div><div><dt>Disposition</dt><dd>{{ activeResearch.disposition || '—' }}</dd></div><div><dt>Research status</dt><dd>{{ activeResearch.research_status }}</dd></div><div><dt>Linked Claim</dt><dd>{{ activeResearch.linked_claim_id ? claimById.get(activeResearch.linked_claim_id)?.statement : '无真实法务草稿' }}</dd></div><div><dt>Reasons</dt><dd><code>{{ activeResearch.reason_codes.join(' · ') || '—' }}</code></dd></div></dl></article>
            <div class="rc0-evidence-column"><span class="rc0-column-label">正式 checklist 法源命中</span><article v-for="hit in activeEvidence" :key="hit.id" class="rc0-evidence-card"><div><span :class="['rc0-status', hit.review_status === 'expert_verified' ? 'rc0-status--progress' : 'rc0-status--review']">{{ hit.review_status || 'pending' }}</span></div><h3>{{ hit.title_zh || hit.title_pt || hit.urn }}</h3><dl><div><dt>URN</dt><dd><code>{{ hit.urn }}</code></dd></div><div><dt>Grounded</dt><dd>{{ hit.grounded }}</dd></div><div><dt>Published</dt><dd>{{ hit.published_at }}</dd></div></dl></article><p v-if="!activeEvidence.length" class="competition-empty">无法源命中；系统不会补写结论。</p></div>
          </div>
        </section>

        <section v-else-if="activeSection === 'claims'" class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">REAL LEGAL DRAFTS ONLY</span><h2>Claim 与缺口</h2><p>ClaimRecord 只来自真实法务草稿；其他分母项以 ResearchItem 和 disposition 呈现。</p></div><span class="rc0-version-chip">{{ compilation?.claims.length || 0 }} Claims / {{ researchItems.length }} ResearchItems</span></div>
          <div class="rc0-claim-list"><article v-for="claim in compilation?.claims || []" :key="claim.id" class="rc0-claim-card"><header><code>{{ claim.checklist_code }}</code><span :class="['rc0-status', claim.status === 'supported' ? 'rc0-status--progress' : 'rc0-status--review']">{{ claim.status }}</span></header><h3>{{ claim.statement }}</h3><div class="rc0-claim-grid"><dl><dt>Fact refs</dt><dd><code>{{ claim.fact_refs.join(' · ') }}</code></dd><dt>Evidence refs</dt><dd><code>{{ claim.evidence_refs.join(' · ') }}</code></dd></dl><dl><dt>Reason codes</dt><dd><code>{{ claim.reason_codes.join(' · ') || '—' }}</code></dd><dt>Human note</dt><dd>{{ claim.confirmation_note || '待法务决定' }}</dd></dl></div></article><p v-if="!compilation?.claims.length" class="competition-empty">尚无真实法务 Claim 草稿。系统已保留 {{ researchItems.length }} 个 ResearchItem，未生成占位 Claim。</p></div>
        </section>

        <section v-else-if="activeSection === 'coverage'" class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">COVERAGEPROOF 0.2</span><h2>CoverageProof</h2><p>五类 disposition 与 out-of-scope 计数在同一个哈希绑定的证明体中披露。</p></div><span class="rc0-version-chip">{{ proof?.proof.schema_version || '尚无 proof' }}</span></div>
          <div class="rc0-coverage-hero"><div><span>Pack total</span><strong>{{ proof?.proof.pack_total ?? researchItems.length }}</strong><small>Scope {{ proof?.proof.scope_total ?? inScope.length }} · Out {{ proof?.proof.out_of_scope_by_scope_count ?? outOfScope.length }}</small></div></div>
          <div class="rc0-coverage-grid"><article v-for="(value, key) in dispositionCounts" :key="key"><span>{{ key }}</span><strong>{{ proof ? proof.proof[`${key}_count`] ?? value : value }}</strong></article></div>
          <article class="rc0-panel"><div class="rc0-panel__heading"><div><span>IMMUTABLE IDENTITY</span><h3>证明哈希</h3></div></div><dl class="rc0-definition-list"><div><dt>Denominator SHA</dt><dd><code>{{ proof?.denominator_hash || '—' }}</code></dd></div><div><dt>Proof SHA</dt><dd><code>{{ proof?.proof_hash || '—' }}</code></dd></div><div><dt>Rule</dt><dd>{{ proof?.proof.answerability_rule || '尚未生成正式证明' }}</dd></div></dl></article>
        </section>

        <section v-else-if="activeSection === 'delivery'" class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">FORMAL RELEASE GATE</span><h2>交付中心</h2><p>比赛展示不会创建正式 Release，也不会把工程验证冒充为律师、客户 UAT 或生产部署证据。</p></div><span class="rc0-status rc0-status--blocked">{{ delivery?.delivery_allowed ? 'allowed' : 'blocked_external' }}</span></div>
          <article class="rc0-panel rc0-panel--blocked"><div class="rc0-panel__heading"><div><span>RELEASE BOUNDARY</span><h3>{{ delivery?.boundary || '无 active customer delivery release' }}</h3></div></div><ol class="rc0-block-list"><li v-for="reason in delivery?.blocking_reasons || ['缺少真实外部证据']" :key="reason">{{ reason }}</li></ol><p class="rc0-callout">正式 Gate 未弱化；本页仅披露 API 评估结果。</p></article>
          <div class="rc0-delivery-grid"><article v-for="item in [{name:'Expert Attestation', id:delivery?.expert_attestation_id},{name:'Customer UAT', id:delivery?.uat_acceptance_id},{name:'Deployment Evidence', id:delivery?.deployment_evidence_id},{name:'Formal Release', id:delivery?.release_id}]" :key="item.name"><span class="rc0-status rc0-status--blocked">{{ item.id ? 'present' : 'blocked_external' }}</span><h3>{{ item.name }}</h3><code>{{ item.id || 'missing' }}</code></article></div>
        </section>

        <section v-else class="rc0-page">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">FORMAL AUDIT SERVICE</span><h2>审计记录</h2><p>时间线来自正式 AuditLog API，不是前端预置的演示事件。</p></div><span class="rc0-version-chip">{{ audit.length }} events</span></div>
          <ol class="rc0-timeline"><li v-for="event in audit" :key="event.id"><time>{{ new Date(event.created_at).toLocaleString() }}</time><div><span>{{ event.resource_type }} · {{ event.resource_id }}</span><h3>{{ event.action }}</h3><p>{{ event.detail || '无补充详情' }}</p><dl><dt>Actor</dt><dd>user {{ event.user_id }}</dd></dl></div></li><li v-if="!audit.length" class="competition-empty">尚无机制层审计事件。</li></ol>
        </section>
      </main>
    </div>
  </div>
</template>
