<script setup lang="ts">
import { computed } from 'vue'
import type { Scenario } from '@/types/scenario'

const props = defineProps<{
  scenario: Scenario
}>()

const answerability = computed(() => props.scenario.answerability ?? null)
const claims = computed(() => props.scenario.claims ?? null)
const coverage = computed(() => props.scenario.coverage ?? null)
const ledger = computed(() => props.scenario.material_ledger ?? null)

const hasAny = computed(
  () =>
    !!answerability.value ||
    !!claims.value ||
    !!coverage.value ||
    !!(ledger.value && ledger.value.length),
)

const REASON_LABELS: Record<string, string> = {
  pack_not_installed: '未安装能力包',
  insufficient_material: '材料不足',
  no_grounded_evidence: '证据不足',
  llm_unavailable: '模型不可用',
}

function reasonLabel(code: string | null | undefined) {
  if (!code) return ''
  return REASON_LABELS[code] || code
}

const groundingRateText = computed(() => {
  const rate = answerability.value?.signals?.grounding_rate
  if (rate == null) return null
  return `${Math.round(rate * 100)}%`
})

const VERDICT_META: Array<{ key: string; label: string; cls: string }> = [
  { key: 'supported', label: 'supported', cls: 'ok' },
  { key: 'needs_review', label: 'needs_review', cls: 'warn' },
  { key: 'blocked', label: 'blocked', cls: 'rejected' },
  { key: 'unanswerable', label: 'unanswerable', cls: 'muted-badge' },
]

function verdictCount(key: string) {
  return claims.value?.summary?.by_verdict?.[key] ?? 0
}

const KIND_LABELS: Record<string, string> = {
  file: '文件',
  field_set: '表单',
  extract_snapshot: '抽取快照',
}

function kindLabel(kind: string) {
  return KIND_LABELS[kind] || kind
}

const STATE_META: Record<string, { label: string; cls: string }> = {
  raw_archived: { label: '已归档', cls: 'muted-badge' },
  extracted: { label: '已抽取', cls: 'warn' },
  verified: { label: '已核验', cls: 'ok' },
  unverified: { label: '未核验', cls: 'rejected' },
  in_use: { label: '使用中', cls: 'ok' },
  returned: { label: '已退回', cls: 'rejected' },
  superseded: { label: '已替换', cls: 'muted-badge' },
}

function stateLabel(state: string) {
  return STATE_META[state]?.label || state
}

function stateClass(state: string) {
  return STATE_META[state]?.cls || 'muted-badge'
}
</script>

<template>
  <section v-if="hasAny" class="panel mechanism-panel">
    <h2>机制层 v0.1（只读）</h2>
    <p class="muted">可答性判定、Claim 编译、覆盖证明与材料账本的机制投影，供复核参考。</p>

    <div v-if="answerability" class="mechanism-block">
      <h3>可答性</h3>
      <div class="mechanism-row">
        <template v-if="answerability.answerable">
          <span class="badge ok">可交付</span>
          <span v-if="groundingRateText" class="badge muted-badge">
            grounding {{ groundingRateText }}
          </span>
          <span v-if="answerability.degraded_mode" class="badge warn">降级模式</span>
        </template>
        <template v-else>
          <span class="badge rejected">拒答</span>
          <span v-if="answerability.reason_code" class="badge warn">
            {{ reasonLabel(answerability.reason_code) }}
          </span>
        </template>
      </div>
      <p v-if="!answerability.answerable && answerability.message" class="muted">
        {{ answerability.message }}
      </p>
    </div>

    <div v-if="claims" class="mechanism-block">
      <h3>Claim 编译</h3>
      <div class="mechanism-row">
        <span class="badge muted-badge">共 {{ claims.summary?.total ?? 0 }} 条</span>
        <span v-for="v in VERDICT_META" :key="v.key" class="badge" :class="v.cls">
          {{ v.label }} {{ verdictCount(v.key) }}
        </span>
      </div>
      <p class="muted mechanism-note">每条结论均已编译为带证据链的 Claim；无证据的结论不进入定稿。</p>
    </div>

    <div v-if="coverage" class="mechanism-block">
      <h3>覆盖证明</h3>
      <template v-if="coverage.proof">
        <div class="mechanism-row">
          <span class="badge ok">
            覆盖 {{ coverage.proof.covered_count }}/{{ coverage.proof.denominator_count }}
          </span>
          <span class="badge muted-badge">分母来源：包声明要件全集</span>
          <span class="badge" :class="coverage.proof.open_count > 0 ? 'warn' : 'ok'">
            未闭环任务 {{ coverage.proof.open_count }}
          </span>
        </div>
        <p class="muted mechanism-note">
          proof_hash <code class="mechanism-mono">{{ (coverage.proof.proof_hash || '').slice(0, 12) }}</code>
        </p>
      </template>
      <p v-else class="muted">未生成（无包声明分母时不自证覆盖）。</p>
    </div>

    <div v-if="ledger && ledger.length" class="mechanism-block">
      <h3>材料账本</h3>
      <ul class="mechanism-ledger-list">
        <li v-for="block in ledger" :key="block.block_uid" class="mechanism-ledger-row">
          <span class="badge muted-badge">{{ kindLabel(block.kind) }}</span>
          <span class="mechanism-ledger-name">{{ block.filename || block.block_uid }}</span>
          <span class="badge" :class="stateClass(block.state)">{{ stateLabel(block.state) }}</span>
          <code v-if="block.content_hash" class="mechanism-mono">
            {{ block.content_hash.slice(0, 10) }}
          </code>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.mechanism-block {
  margin-top: 0.9rem;
}

.mechanism-block h3 {
  margin: 0 0 0.4rem;
  font-size: 0.95rem;
}

.mechanism-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.mechanism-note {
  margin: 0.35rem 0 0;
  font-size: 0.8rem;
}

.mechanism-mono {
  font-family: monospace;
  font-size: 0.8rem;
}

.mechanism-ledger-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.mechanism-ledger-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.mechanism-ledger-name {
  font-size: 0.85rem;
}
</style>
