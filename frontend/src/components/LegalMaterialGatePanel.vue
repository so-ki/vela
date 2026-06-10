<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { generateInvestigationPack, downloadScenarioMaterialFile, fetchUserPreferences } from '@/api/client'
import type { DimensionInfo, RulesCatalog, Scenario } from '@/types/scenario'

const props = defineProps<{
  scenario: Scenario
  catalog: RulesCatalog
}>()

const emit = defineEmits<{
  investigationGenerated: [scenario: Scenario]
}>()

const selected = ref<string[]>([])
const selectedIssueCodes = ref<string[]>([])
const matchThreshold = ref(70)
const retrievalTopK = ref(3)
const submitting = ref(false)
const error = ref<string | null>(null)
const dimensionsLocked = ref(false)
const legalHitsExpanded = ref<Record<string, boolean>>({})

let generateTimer: ReturnType<typeof setTimeout> | null = null

const archivedFiles = computed(() => props.scenario.document_extract?.archived_files ?? [])
const materialFindings = computed(() => props.scenario.material_scope_findings ?? [])
const issueSuggestions = computed(() => props.scenario.issue_suggestions ?? [])
const unverifiedFacts = computed(() => props.scenario.unverified_facts ?? [])
const docConflicts = computed(() => props.scenario.document_extract?.field_conflicts ?? [])

const gapSummary = computed(() => {
  const adequacy = props.scenario.investigation_adequacy
  if (adequacy?.gap_summary) return adequacy.gap_summary
  const missing = materialFindings.value.filter((f) => f.risk === 'RED').length
  const yellow = materialFindings.value.filter((f) => f.risk === 'YELLOW').length
  return {
    missing_count: missing,
    at_risk_count: yellow,
    s2_count: 0,
    s3_count: 0,
    zero_hit_count: 0,
  }
})

async function downloadArchivedFile(storedName: string, filename: string) {
  await downloadScenarioMaterialFile(props.scenario.id, storedName, filename)
}

const suggestedDimensions = computed(() => {
  const fromExtract = props.scenario.document_extract?.compliance_dimensions || []
  return fromExtract.filter((id) => props.catalog.dimensions.some((d) => d.id === id))
})

function toggleDimension(id: string) {
  if (dimensionsLocked.value) return
  const set = new Set(selected.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  selected.value = [...set]
}

function toggleIssueCode(code: string) {
  const set = new Set(selectedIssueCodes.value)
  if (set.has(code)) set.delete(code)
  else set.add(code)
  selectedIssueCodes.value = [...set]
}

function initIssueSelections() {
  const codes = issueSuggestions.value
    .filter((s) => s.confidence === 'high' || s.confidence === 'medium' || s.confidence === 'low')
    .map((s) => s.code)
  selectedIssueCodes.value = [...new Set(codes)]
}

function scheduleGenerate() {
  if (generateTimer) clearTimeout(generateTimer)
  if (selected.value.length === 0) return
  generateTimer = setTimeout(() => {
    void generatePack()
  }, 400)
}

watch(selected, (dims) => {
  error.value = null
  if (dims.length === 0) {
    if (generateTimer) clearTimeout(generateTimer)
    return
  }
  scheduleGenerate()
})

onMounted(async () => {
  matchThreshold.value = props.scenario.investigation_settings?.match_threshold ?? 70
  retrievalTopK.value = props.scenario.investigation_settings?.retrieval_top_k ?? 3
  initIssueSelections()
  try {
    const prefs = await fetchUserPreferences()
    if (prefs.match_threshold != null && !props.scenario.investigation_settings?.match_threshold) {
      matchThreshold.value = prefs.match_threshold
    }
    if (prefs.retrieval_top_k != null && !props.scenario.investigation_settings?.retrieval_top_k) {
      retrievalTopK.value = prefs.retrieval_top_k
    }
  } catch {
    /* ignore */
  }
  if (suggestedDimensions.value.length) {
    selected.value = [...suggestedDimensions.value]
  } else if (props.catalog.dimensions.length) {
    selected.value = props.catalog.dimensions.map((d: DimensionInfo) => d.id)
  }
})

watch(
  () => props.scenario.issue_suggestions,
  () => initIssueSelections(),
)

onBeforeUnmount(() => {
  if (generateTimer) clearTimeout(generateTimer)
})

async function generatePack() {
  if (selected.value.length === 0 || submitting.value) return
  submitting.value = true
  dimensionsLocked.value = true
  error.value = null
  try {
    const updated = await generateInvestigationPack(
      props.scenario.id,
      selected.value,
      false,
      matchThreshold.value,
      retrievalTopK.value,
      selectedIssueCodes.value,
    )
    emit('investigationGenerated', updated)
  } catch (e: unknown) {
    dimensionsLocked.value = false
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '协查包生成失败，请稍后重试'
    } else {
      error.value = '协查包生成失败，请稍后重试'
    }
  } finally {
    submitting.value = false
  }
}

function toggleLegalHits(code: string) {
  legalHitsExpanded.value = { ...legalHitsExpanded.value, [code]: !legalHitsExpanded.value[code] }
}
</script>

<template>
  <section class="panel review-gate-section">
    <div class="review-gate-head">
      <h2>① 选定协查范围</h2>
      <p class="muted">
        先看<strong>协查缺口摘要</strong>与材料 Playbook 命中，可选采纳 LLM 建议议题，再勾选维度生成协查包。
      </p>
    </div>

    <div v-if="scenario.document_extract?.extraction_warning" class="conflict-banner red-flag-banner">
      <strong>抽取警告</strong>
      <p>{{ scenario.document_extract.extraction_warning }}</p>
    </div>

    <div class="gap-summary-panel panel" v-if="materialFindings.length || issueSuggestions.length">
      <h3>协查缺口摘要（Gate A 预览）</h3>
      <div class="gap-summary-stats">
        <span class="badge warn">材料 Playbook {{ materialFindings.length }} 项</span>
        <span class="badge pri-medium">LLM 建议 {{ issueSuggestions.length }} 项</span>
        <span v-if="unverifiedFacts.length" class="badge err">未验证抽取 {{ unverifiedFacts.length }}</span>
        <span v-if="docConflicts.length" class="badge warn">多文件冲突 {{ docConflicts.length }}</span>
      </div>
    </div>

    <div v-if="materialFindings.length" class="material-findings panel">
      <h3>材料 House Rules 命中</h3>
      <ul class="finding-card-list">
        <li v-for="f in materialFindings" :key="f.rule_id" class="finding-card" :class="f.risk?.toLowerCase()">
          <strong>{{ f.label }}</strong>
          <span class="badge" :class="f.risk === 'RED' ? 'err' : 'warn'">{{ f.risk_label || f.risk }}</span>
          <p class="muted">{{ f.guidance }}</p>
          <p v-if="f.feeds_checklist?.length" class="muted">
            建议对照 checklist：{{ f.feeds_checklist.join('、') }}
          </p>
        </li>
      </ul>
    </div>

    <div v-if="issueSuggestions.length" class="issue-suggestions panel">
      <h3>LLM 建议增加的核查项</h3>
      <p class="muted">默认预选；法务可取消勾选。须 grounding 通过才会出现。</p>
      <ul class="issue-suggestion-list">
        <li v-for="s in issueSuggestions" :key="s.code">
          <label>
            <input
              type="checkbox"
              :checked="selectedIssueCodes.includes(s.code)"
              @change="toggleIssueCode(s.code)"
            />
            <strong>{{ s.code }}</strong> {{ s.title }}
            <span class="badge pri-medium">{{ s.confidence }}</span>
          </label>
          <p class="muted snippet">锚点：{{ s.fact_anchor }}</p>
        </li>
      </ul>
    </div>

    <div v-if="docConflicts.length" class="conflict-banner panel">
      <strong>材料冲突</strong>
      <ul>
        <li v-for="c in docConflicts" :key="c.field">
          {{ c.field }}：{{ c.values?.map((v: { value: string }) => v.value).join(' / ') }}
        </li>
      </ul>
    </div>

    <div v-if="unverifiedFacts.length" class="unverified-facts panel">
      <strong>未验证抽取</strong>
      <ul>
        <li v-for="(u, idx) in unverifiedFacts" :key="idx">
          {{ u.field }} · {{ u.snippet }}
          <span v-if="u.score != null" class="muted">score {{ u.score }}</span>
        </li>
      </ul>
    </div>

    <div class="review-gate-split">
      <aside class="review-gate-scope-column">
        <h3>协查范围</h3>
        <p class="muted scope-ai-hint" v-if="suggestedDimensions.length">
          AI 识别（仅供参考）：{{
            suggestedDimensions
              .map((id) => catalog.dimensions.find((d) => d.id === id)?.name)
              .filter(Boolean)
              .join('、')
          }}
        </p>
        <p class="muted scope-ai-hint" v-if="dimensionsLocked">
          协查包生成中，暂不可修改维度…
        </p>
        <div class="threshold-control panel" :class="{ disabled: dimensionsLocked }">
          <label for="match-threshold">
            <strong>匹配度门控阈值</strong>
            <span class="threshold-value">{{ matchThreshold }} 分</span>
          </label>
          <input
            id="match-threshold"
            v-model.number="matchThreshold"
            type="range"
            min="50"
            max="95"
            step="5"
            :disabled="dimensionsLocked"
          />
        </div>
        <div class="threshold-control panel" :class="{ disabled: dimensionsLocked }">
          <label for="retrieval-top-k">
            <strong>每条核查题绑定法条数</strong>
            <span class="threshold-value">Top {{ retrievalTopK }}</span>
          </label>
          <input
            id="retrieval-top-k"
            v-model.number="retrievalTopK"
            type="range"
            min="1"
            max="10"
            step="1"
            :disabled="dimensionsLocked"
          />
        </div>
        <div class="dimension-grid dimension-grid-sidebar">
          <label
            v-for="dim in catalog.dimensions"
            :key="dim.id"
            class="dimension-card"
            :class="{ active: selected.includes(dim.id), disabled: dimensionsLocked }"
          >
            <input
              type="checkbox"
              :value="dim.id"
              :checked="selected.includes(dim.id)"
              :disabled="dimensionsLocked"
              @change="toggleDimension(dim.id)"
            />
            <div class="dimension-body">
              <strong>{{ dim.name }}</strong>
              <span class="dim-pt">{{ dim.name_pt }}</span>
              <p>{{ dim.description }}</p>
            </div>
          </label>
        </div>
      </aside>

      <div class="review-gate-material-column">
        <div v-if="archivedFiles.length" class="archived-files-block panel">
          <h3>归档方案文件</h3>
          <ul class="archived-files-list">
            <li v-for="file in archivedFiles" :key="file.id">
              <button type="button" class="btn-link sm" @click="downloadArchivedFile(file.stored_name, file.filename)">
                {{ file.filename }}
              </button>
            </li>
          </ul>
        </div>

        <div v-if="selected.length" class="auto-generate-status panel">
          <div v-if="submitting" class="gate-generating-banner">
            <strong>协查包生成中…</strong>
          </div>
          <div v-else-if="error" class="gate-error-banner">
            <p class="error">{{ error }}</p>
            <button type="button" class="btn-primary sm" @click="generatePack">重试生成</button>
          </div>
          <p v-else class="muted">
            已选定 {{ selected.length }} 个维度
            <span v-if="selectedIssueCodes.length">· 含 {{ selectedIssueCodes.length }} 条 LLM 建议议题</span>
          </p>
        </div>
        <div v-else class="auto-generate-status panel">
          <p class="muted">请至少勾选一个合规维度。</p>
        </div>
      </div>
    </div>

    <div class="material-gate-footer">
      <RouterLink to="/" class="btn-secondary link-btn sm">工作台 · AI 设置</RouterLink>
      <RouterLink :to="`/scenarios/${scenario.id}/extract`" class="btn-secondary link-btn sm">
        查看 AI 抽取表
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.gap-summary-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.finding-card-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.finding-card {
  border: 1px solid var(--border-muted, #ddd);
  border-radius: 8px;
  padding: 0.75rem;
}
.issue-suggestion-list {
  list-style: none;
  padding: 0;
}
.issue-suggestion-list li {
  margin-bottom: 0.5rem;
}
.snippet {
  font-size: 0.85rem;
  margin-left: 1.5rem;
}
</style>
