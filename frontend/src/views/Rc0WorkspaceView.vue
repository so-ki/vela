<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Rc0StatePanel from '@/components/Rc0StatePanel.vue'
import { rc0SyntheticCase as matter } from '@/demo/rc0SyntheticCase'

const route = useRoute()
const sections = [
  { id: 'overview', label: '项目总览', index: '01' },
  { id: 'materials', label: '材料与事实', index: '02' },
  { id: 'checklist', label: '调查清单', index: '03' },
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
const activeResearchIndex = ref(0)
const activeResearch = computed(() => matter.researchItems[activeResearchIndex.value])

const exportSyntheticSummary = () => {
  const payload = {
    warning: '拟制演示 / SYNTHETIC DEMO — 非真实法律、客户或生产证据，不得用于正式发布。',
    ...matter,
  }
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
  link.download = 'vela-rc0-synthetic-demo.json'
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>

<template>
  <div class="rc0-frame">
    <aside class="rc0-sidebar" aria-label="RC0 项目导航">
      <div class="rc0-sidebar__eyebrow">MATTER WORKSPACE</div>
      <div class="rc0-sidebar__matter">
        <span>{{ matter.id }}</span><strong>Projeto Aurora</strong><small>Engineering Demonstrator RC0</small>
      </div>
      <nav class="rc0-section-nav">
        <RouterLink v-for="section in sections" :key="section.id" :to="`/rc0/${section.id}`" :class="{ active: activeSection === section.id }">
          <span>{{ section.index }}</span>{{ section.label }}
        </RouterLink>
      </nav>
      <div class="rc0-sidebar__boundary">
        <span class="rc0-status rc0-status--demo">SYNTHETIC DEMO</span>
        <p>非真实律师、客户或生产证据。正式 Release Gate 未放行。</p>
      </div>
    </aside>

    <div class="rc0-workspace">
      <section class="rc0-demo-banner" aria-labelledby="synthetic-title">
        <div class="rc0-demo-banner__flag">拟制演示<strong>SYNTHETIC DEMO</strong></div>
        <div><h1 id="synthetic-title">本工作台仅验证工程演示链</h1><p>所有对象均为 synthetic_demo；不得作为法律意见、客户验收、律师认证或生产部署证据。</p></div>
        <div class="rc0-demo-banner__machine"><code>simulated=true</code><code>status=demo_only</code><code>formal_release_allowed=false</code></div>
      </section>

      <header class="rc0-context-bar">
        <div class="rc0-context-bar__title"><span>当前项目</span><strong>{{ matter.title }}</strong></div>
        <dl class="rc0-context-grid">
          <div><dt>法域</dt><dd>{{ matter.context.country }} · {{ matter.context.state }}</dd></div>
          <div><dt>行业 / 行动</dt><dd>{{ matter.context.industry }} · {{ matter.context.actionType }}</dd></div>
          <div><dt>Pack / Rules / Corpus</dt><dd><code>{{ matter.versions.pack }}</code> · {{ matter.versions.rules }} · {{ matter.versions.corpus }}</dd></div>
          <div><dt>内容状态</dt><dd><span class="rc0-status rc0-status--progress">Engineering RC0</span></dd></div>
          <div><dt>Release Gate</dt><dd><span class="rc0-status rc0-status--blocked">blocked_external</span></dd></div>
          <div><dt>对象来源</dt><dd><span class="rc0-status rc0-status--demo">DEMO ONLY</span></dd></div>
        </dl>
      </header>

      <main class="rc0-canvas">
        <section v-if="activeSection === 'overview'" class="rc0-page" aria-labelledby="overview-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">CONTROLLED MATTER</span><h2 id="overview-title">项目总览</h2><p>{{ matter.summary }}</p></div><button class="rc0-button rc0-button--demo" type="button" @click="exportSyntheticSummary">导出拟制 JSON</button></div>
          <div class="rc0-metric-grid"><article v-for="metric in matter.metrics" :key="metric.label" :class="`rc0-metric rc0-metric--${metric.tone}`"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong><small>{{ metric.detail }}</small></article></div>
          <div class="rc0-two-column">
            <article class="rc0-panel"><div class="rc0-panel__heading"><div><span>调查状态</span><h3>当前阶段与下一动作</h3></div><span class="rc0-status rc0-status--progress">进行中</span></div><dl class="rc0-definition-list"><div><dt>当前阶段</dt><dd>{{ matter.currentStage }}</dd></div><div><dt>待确认事实</dt><dd>最终场址坐标、危险品最大库存、设备技术分类</dd></div><div><dt>未覆盖事项</dt><dd>DATA-001 数据处理活动清单</dd></div><div><dt>版本</dt><dd><code>compiler {{ matter.versions.compiler }} · proof {{ matter.versions.coverageProof }} · snapshot {{ matter.versions.snapshot }} · release {{ matter.versions.release }}</code></dd></div><div><dt>下一动作</dt><dd>{{ matter.nextAction }}</dd></div></dl></article>
            <article class="rc0-panel rc0-panel--blocked"><div class="rc0-panel__heading"><div><span>正式交付边界</span><h3>外部阻断未解除</h3></div><span class="rc0-status rc0-status--blocked">禁止发布</span></div><ol class="rc0-block-list"><li v-for="item in matter.externalBlocks" :key="item">{{ item }}</li></ol><p class="rc0-callout">工程测试通过不证明法律内容正确，也不代表真实客户或生产验收。</p></article>
          </div>
          <article class="rc0-panel"><div class="rc0-panel__heading"><div><span>状态语言</span><h3>非 happy-path 完整覆盖</h3></div><span class="rc0-muted">文字 + 图形，不只依靠颜色</span></div><div class="rc0-state-grid"><Rc0StatePanel state="loading" title="Loading" detail="正在读取受控证据，不显示猜测值。"/><Rc0StatePanel state="empty" title="Empty" detail="尚无对象；明确给出创建前提。"/><Rc0StatePanel state="error" title="Error" detail="请求失败；保留 reason code 与重试入口。"/><Rc0StatePanel state="blocked" title="Blocked" detail="门禁拒绝；说明责任方和解除条件。"/><Rc0StatePanel state="readonly" title="Read-only" detail="冻结对象只能读取，不能原地改写。"/><Rc0StatePanel state="demo" title="Demo-only" detail="紫色纹理持续标识拟制对象。"/><Rc0StatePanel state="stale" title="Stale" detail="事实、版本或 hash 已变化，必须重验。"/><Rc0StatePanel state="unknown" title="Unknown version" detail="不回退 current/latest；正式路径 fail-closed。"/></div></article>
        </section>

        <section v-else-if="activeSection === 'materials'" class="rc0-page" aria-labelledby="materials-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">SOURCE LEDGER</span><h2 id="materials-title">材料与事实</h2><p>材料抽取、业务确认、来源定位和缺失事实同屏可追溯。</p></div><span class="rc0-status rc0-status--readonly">只读拟制快照</span></div>
          <article class="rc0-panel rc0-table-panel"><table class="rc0-table"><caption>材料账本（拟制演示）</caption><thead><tr><th scope="col">材料</th><th scope="col">类型</th><th scope="col">抽取</th><th scope="col">账本状态</th><th scope="col">来源 / 负责人</th><th scope="col">缺失事实</th></tr></thead><tbody><tr v-for="item in matter.materials" :key="item.id"><td><strong>{{ item.name }}</strong><code>{{ item.id }}</code></td><td>{{ item.kind }}</td><td><span class="rc0-status rc0-status--review">{{ item.extraction }}</span></td><td>{{ item.ledger }}</td><td>{{ item.source }}<small>{{ item.owner }}</small></td><td>{{ item.missing }}</td></tr></tbody></table></article>
          <article class="rc0-panel rc0-table-panel"><table class="rc0-table"><caption>事实五元组与业务确认</caption><thead><tr><th scope="col">事实</th><th scope="col">主体 / 属性</th><th scope="col">值</th><th scope="col">时间</th><th scope="col">来源定位</th><th scope="col">确认</th></tr></thead><tbody><tr v-for="fact in matter.facts" :key="fact.id"><td><code>{{ fact.id }}</code></td><td>{{ fact.subject }}<small>{{ fact.attribute }}</small></td><td>{{ fact.value }}</td><td>{{ fact.time }}</td><td><code>{{ fact.source }}</code></td><td><span :class="['rc0-status', fact.confirmation === 'needs_review' ? 'rc0-status--review' : 'rc0-status--demo']">{{ fact.confirmation }}</span></td></tr></tbody></table></article>
        </section>

        <section v-else-if="activeSection === 'checklist'" class="rc0-page" aria-labelledby="checklist-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">FROZEN DENOMINATOR</span><h2 id="checklist-title">调查清单</h2><p>Pack 分母固定 30；screening 只影响优先级，不让事项静默消失。</p></div><span class="rc0-version-chip">scope 18 / pack 30</span></div>
          <div class="rc0-checklist-list"><article v-for="item in matter.checklist" :key="item.code" class="rc0-checklist-row"><div class="rc0-checklist-row__code"><code>{{ item.code }}</code><span>{{ item.priority }}</span></div><div><small>{{ item.group }}</small><h3>{{ item.title }}</h3><p>缺失：{{ item.missing }}</p></div><div><span :class="['rc0-status', item.state === 'uncovered' || item.state === 'unanswerable' ? 'rc0-status--blocked' : item.state === 'pending_review' ? 'rc0-status--review' : 'rc0-status--demo']">{{ item.state }}</span></div><div><small>{{ item.owner }}</small><strong>{{ item.next }}</strong></div></article></div>
        </section>

        <section v-else-if="activeSection === 'research'" class="rc0-page" aria-labelledby="research-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">SOURCE-BACKED RESEARCH</span><h2 id="research-title">法律研究工作台</h2><p>调查事项、规则要件与权威证据三栏对齐；拟制来源不会升级为真实证据。</p></div><span class="rc0-status rc0-status--demo">SYNTHETIC SOURCES</span></div>
          <div class="rc0-research-grid">
            <nav class="rc0-research-items" aria-label="调查事项"><h3>调查事项</h3><button v-for="(item, index) in matter.researchItems" :key="item.code" type="button" :aria-pressed="activeResearchIndex === index" :class="{ active: activeResearchIndex === index }" @click="activeResearchIndex = index"><code>{{ item.code }}</code><span>{{ item.title }}</span></button></nav>
            <article class="rc0-research-rule"><span class="rc0-column-label">规则、要件与事实映射</span><h3>{{ activeResearch.title }}</h3><p>{{ activeResearch.rule }}</p><h4>判断要件</h4><ul><li v-for="element in activeResearch.elements" :key="element">{{ element }}</li></ul><h4>已映射事实</h4><div class="rc0-chip-row"><code v-for="fact in activeResearch.mappedFacts" :key="fact">{{ fact }}</code></div><h4>例外</h4><p>{{ activeResearch.exceptions }}</p><h4>限制</h4><p class="rc0-text-blocked">{{ activeResearch.limitations }}</p></article>
            <div class="rc0-evidence-column"><span class="rc0-column-label">权威法源与证据</span><article v-for="evidence in activeResearch.evidence" :key="evidence.pinpoint" class="rc0-evidence-card"><div><span class="rc0-status rc0-status--demo">DEMO ONLY</span><code>{{ evidence.version }}</code></div><h3>{{ evidence.authority }}</h3><dl><div><dt>Jurisdiction</dt><dd>{{ evidence.jurisdiction }}</dd></div><div><dt>Effective date</dt><dd>{{ evidence.effectiveDate }}</dd></div><div><dt>Pinpoint</dt><dd><code>{{ evidence.pinpoint }}</code></dd></div><div><dt>Source type</dt><dd>{{ evidence.sourceType }}</dd></div><div><dt>Review status</dt><dd>{{ evidence.reviewStatus }}</dd></div><div><dt>Content hash</dt><dd><code>{{ evidence.contentHash }}</code></dd></div></dl><p>{{ evidence.relation }}</p></article></div>
          </div>
        </section>

        <section v-else-if="activeSection === 'claims'" class="rc0-page" aria-labelledby="claims-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">CLAIM LEDGER</span><h2 id="claims-title">Claim 与缺口</h2><p>真正的 statement 与研究缺口分开呈现；零命中不补写结论。</p></div><span class="rc0-status rc0-status--review">人工确认受控</span></div>
          <div class="rc0-claim-list"><article v-for="claim in matter.claims" :key="claim.code" class="rc0-claim-card"><header><code>{{ claim.code }}</code><span :class="['rc0-status', claim.humanDecision.includes('confirmed') ? 'rc0-status--demo' : 'rc0-status--review']">{{ claim.humanDecision }}</span></header><h3>{{ claim.statement }}</h3><div class="rc0-claim-grid"><dl><dt>Fact refs</dt><dd><code>{{ claim.factRefs.join(' · ') || 'none' }}</code></dd><dt>Evidence refs</dt><dd><code>{{ claim.evidenceRefs.join(' · ') || 'none' }}</code></dd><dt>Reason codes</dt><dd><code>{{ claim.reasonCodes.join(' · ') }}</code></dd></dl><dl><dt>不可回答原因</dt><dd>{{ claim.unanswerable }}</dd><dt>缺失事实</dt><dd>{{ claim.missingFacts.join(' · ') }}</dd><dt>下一步</dt><dd><strong>{{ claim.next }}</strong></dd></dl></div></article></div>
        </section>

        <section v-else-if="activeSection === 'coverage'" class="rc0-page" aria-labelledby="coverage-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">DENOMINATOR PROOF</span><h2 id="coverage-title">CoverageProof</h2><p>披露分母、五类 disposition、版本、生成时间和完整 hash。</p></div><span class="rc0-version-chip">compiler {{ matter.coverage.compilerVersion }} · proof {{ matter.coverage.schemaVersion }}</span></div>
          <div class="rc0-coverage-hero"><div><span>Pack total</span><strong>{{ matter.coverage.counts.total }}</strong><small>Scope total {{ matter.coverage.counts.scopeTotal }}</small></div><div class="rc0-coverage-bar" aria-label="CoverageProof 分布"><span style="--segment:7" class="demo"></span><span style="--segment:5" class="review"></span><span style="--segment:2" class="blocked"></span><span style="--segment:3" class="unknown"></span><span style="--segment:1" class="empty"></span></div></div>
          <div class="rc0-coverage-grid"><article v-for="(value, key) in matter.coverage.counts" :key="key"><span>{{ key }}</span><strong>{{ value }}</strong></article></div>
          <article class="rc0-panel"><dl class="rc0-definition-list"><div><dt>Denominator</dt><dd><code>{{ matter.coverage.denominatorRef }}</code></dd></div><div><dt>Denominator hash</dt><dd><code>{{ matter.coverage.denominatorHash }}</code></dd></div><div><dt>Proof hash</dt><dd><code>{{ matter.coverage.proofHash }}</code></dd></div><div><dt>生成时间</dt><dd>{{ matter.coverage.generatedAt }}</dd></div></dl></article>
        </section>

        <section v-else-if="activeSection === 'delivery'" class="rc0-page" aria-labelledby="delivery-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">DELIVERY ASSURANCE</span><h2 id="delivery-title">交付中心</h2><p>工程 checkpoint 与真实外部证据严格分层。拟制步骤永远不能进入正式 Release。</p></div><span class="rc0-status rc0-status--blocked">formal release blocked</span></div>
          <section class="rc0-release-warning"><strong>SYNTHETIC DEMO</strong><span>无真实专家签署、客户 UAT 或生产部署证据。</span><code>formal_release_allowed=false</code></section>
          <ol class="rc0-pipeline"><li v-for="(stage, index) in matter.deliveryStages" :key="stage.name" :class="`rc0-pipeline__stage rc0-pipeline__stage--${stage.state}`"><span class="rc0-pipeline__index">{{ String(index + 1).padStart(2, '0') }}</span><div><h3>{{ stage.name }}</h3><p>{{ stage.detail }}</p><code>{{ stage.hash }}</code></div><span :class="['rc0-status', stage.state === 'blocked' ? 'rc0-status--blocked' : 'rc0-status--demo']">{{ stage.state === 'blocked' ? 'blocked_external' : 'demo_only' }}</span></li></ol>
        </section>

        <section v-else class="rc0-page" aria-labelledby="audit-title">
          <div class="rc0-page-heading"><div><span class="rc0-kicker">IMMUTABLE TRACE</span><h2 id="audit-title">审计记录</h2><p>时间、操作者、动作、版本、hash、状态变化、来源和阻断原因一一对应。</p></div><span class="rc0-status rc0-status--readonly">只读时间线</span></div>
          <ol class="rc0-timeline"><li v-for="event in matter.audit" :key="`${event.at}-${event.action}`"><div class="rc0-timeline__rail" aria-hidden="true"><span></span></div><article><header><time>{{ event.at }}</time><span :class="['rc0-status', event.result === 'blocked' ? 'rc0-status--blocked' : 'rc0-status--demo']">{{ event.result }}</span></header><h3>{{ event.action }}</h3><dl><div><dt>操作者</dt><dd>{{ event.actor }}</dd></div><div><dt>版本</dt><dd><code>{{ event.version }}</code></dd></div><div><dt>Hash</dt><dd><code>{{ event.hash }}</code></dd></div><div><dt>状态变化</dt><dd>{{ event.change }}</dd></div><div><dt>来源 / 原因</dt><dd>synthetic_demo · {{ event.reason }}</dd></div></dl></article></li></ol>
        </section>
      </main>
    </div>
  </div>
</template>
