<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import {
  downloadScenarioMaterialFile,
  fetchScenario,
  fetchUserPreferences,
  generateInvestigationPack,
  retryInvestigationPack,
} from '@/api/client'
import CapabilityPackCard from '@/components/CapabilityPackCard.vue'
import {
  capabilityPackFromProposal,
  capabilityPackFromSnapshot,
  catalogMatchesProposal,
  catalogMatchesSnapshot,
} from '@/config/sceneClassification'
import type { DimensionInfo, RulesCatalog, Scenario, ScenarioScopeSnapshot } from '@/types/scenario'

const props = defineProps<{
  scenario: Scenario
  catalog: RulesCatalog | null
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
const dimensionsLocked = ref(
  !!props.scenario.scenario_scope?.snapshot || props.scenario.status !== 'pending_scope',
)
const sceneConfirmed = ref(false)

const archivedFiles = computed(() => props.scenario.document_extract?.archived_files ?? [])
const scope = computed(() => props.scenario.scenario_scope)
const proposedScene = computed(() => scope.value?.proposed)
const frozenSnapshot = computed(() => scope.value?.snapshot)
const proposalCatalogMatches = computed(() => catalogMatchesProposal(props.catalog, proposedScene.value))
const snapshotCatalogMatches = computed(() => catalogMatchesSnapshot(props.catalog, frozenSnapshot.value))
const catalogDimensions = computed(() => {
  if (frozenSnapshot.value) {
    return snapshotCatalogMatches.value ? props.catalog?.dimensions ?? [] : []
  }
  return proposalCatalogMatches.value ? props.catalog?.dimensions ?? [] : []
})
const displayedDimensions = computed<DimensionInfo[]>(() => {
  if (!frozenSnapshot.value) return catalogDimensions.value
  const byId = new Map(catalogDimensions.value.map((dimension) => [dimension.id, dimension]))
  return selected.value.map((id, index) =>
    byId.get(id) ?? {
      id,
      name: id,
      name_pt: '',
      description: '冻结快照中的合规维度',
      order: index,
    },
  )
})
const displayedPack = computed(() =>
  frozenSnapshot.value
    ? capabilityPackFromSnapshot(frozenSnapshot.value, proposedScene.value)
    : capabilityPackFromProposal(proposedScene.value, props.catalog),
)
const fitAssessment = computed(() => scope.value?.fit_assessment)
const fitDecision = computed<'fit' | 'accept_warning'>(() =>
  fitAssessment.value?.result === 'fit' ? 'fit' : 'accept_warning',
)
const materialFindings = computed(() => props.scenario.material_scope_findings ?? [])
const issueSuggestions = computed(() => props.scenario.issue_suggestions ?? [])
const unverifiedFacts = computed(() => props.scenario.unverified_facts ?? [])
const docConflicts = computed(() => props.scenario.document_extract?.field_conflicts ?? [])
const canConfirmScope = computed(
  () =>
    !frozenSnapshot.value &&
    props.scenario.status === 'pending_scope' &&
    proposalCatalogMatches.value &&
    !!proposedScene.value?.proposal_hash &&
    selected.value.length > 0 &&
    sceneConfirmed.value &&
    fitAssessment.value?.result !== 'blocked' &&
    !submitting.value,
)
const canRetryScope = computed(
  () =>
    !!frozenSnapshot.value &&
    props.scenario.status === 'scope_generation_failed' &&
    selected.value.length > 0 &&
    !submitting.value,
)

async function downloadArchivedFile(storedName: string, filename: string) {
  const accepted = window.confirm(
    '原始文件仅通过格式、压缩结构和常见主动内容筛查，未做完整杀毒或内容净化。请确认文件已通过贵司终端/DMS安全扫描，并在隔离查看器中打开。',
  )
  if (!accepted) return
  await downloadScenarioMaterialFile(props.scenario.id, storedName, filename)
}

const suggestedDimensions = computed(() => {
  const fromExtract = props.scenario.document_extract?.compliance_dimensions || []
  return fromExtract.filter((id) => catalogDimensions.value.some((d) => d.id === id))
})

function toggleDimension(id: string) {
  if (dimensionsLocked.value) return
  const set = new Set(selected.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  selected.value = [...set]
}

function toggleIssueCode(code: string) {
  if (dimensionsLocked.value) return
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

function applyFrozenSnapshot(snapshot: ScenarioScopeSnapshot) {
  matchThreshold.value = snapshot.match_threshold
  retrievalTopK.value = snapshot.retrieval_top_k
  selectedIssueCodes.value = [...snapshot.selected_issue_codes]
  selected.value = [...snapshot.compliance_dimensions]
  sceneConfirmed.value = true
  dimensionsLocked.value = true
}

onMounted(async () => {
  const frozen = scope.value?.snapshot
  matchThreshold.value = frozen?.match_threshold ?? props.scenario.investigation_settings?.match_threshold ?? 70
  retrievalTopK.value = frozen?.retrieval_top_k ?? props.scenario.investigation_settings?.retrieval_top_k ?? 3
  if (frozen) {
    applyFrozenSnapshot(frozen)
  } else {
    initIssueSelections()
  }
  if (!frozen) try {
    const prefs = await fetchUserPreferences()
    if (prefs.match_threshold != null) {
      matchThreshold.value = prefs.match_threshold
    }
    if (prefs.retrieval_top_k != null) {
      retrievalTopK.value = prefs.retrieval_top_k
    }
  } catch {
    /* ignore */
  }
  if (frozen) {
    return
  }
  if (suggestedDimensions.value.length) {
    selected.value = [...suggestedDimensions.value]
  } else if (catalogDimensions.value.length) {
    selected.value = catalogDimensions.value.map((d: DimensionInfo) => d.id)
  }
})

watch(
  () => props.scenario.issue_suggestions,
  () => {
    if (!scope.value?.snapshot) initIssueSelections()
  },
)

watch(
  frozenSnapshot,
  (snapshot) => {
    if (snapshot) applyFrozenSnapshot(snapshot)
  },
)

async function generatePack() {
  const retryingFrozenSnapshot = !!frozenSnapshot.value
  if (retryingFrozenSnapshot ? !canRetryScope.value : !canConfirmScope.value) return
  submitting.value = true
  dimensionsLocked.value = true
  error.value = null
  try {
    const updated = retryingFrozenSnapshot
      ? await retryInvestigationPack(props.scenario.id)
      : await generateInvestigationPack(
          props.scenario.id,
          selected.value,
          false,
          matchThreshold.value,
          retrievalTopK.value,
          selectedIssueCodes.value,
          proposedScene.value?.proposal_hash || '',
          fitDecision.value,
        )
    emit('investigationGenerated', updated)
  } catch (e: unknown) {
    // confirm-scope may have frozen the snapshot before generation failed. Until the
    // authoritative row is reloaded, keep every generation field locked (fail closed).
    dimensionsLocked.value = true
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '协查包生成失败，请稍后重试'
    } else {
      error.value = '协查包生成失败，请稍后重试'
    }
    try {
      const refreshed = await fetchScenario(props.scenario.id)
      const refreshedSnapshot = refreshed.scenario_scope?.snapshot
      if (refreshedSnapshot) {
        applyFrozenSnapshot(refreshedSnapshot)
      } else {
        dimensionsLocked.value = refreshed.status !== 'pending_scope'
      }
      emit('investigationGenerated', refreshed)
    } catch {
      error.value = `${error.value}；无法确认服务端冻结状态，请刷新页面后再操作。`
    }
  } finally {
    submitting.value = false
  }
}

function conflictValueSummary(conflict: { sources: Array<{ value: string }> }): string {
  return conflict.sources.map((item) => item.value).join(' / ')
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

    <CapabilityPackCard
      :pack="displayedPack"
      :frozen="!!frozenSnapshot"
      compact
      class="legal-scene-card"
    >
      <div
        v-if="fitAssessment"
        class="scope-fit-banner"
        :class="fitAssessment.result === 'blocked' ? 'error' : 'warn-note'"
      >
        适配判断：{{ fitAssessment.result }} · {{ fitAssessment.reasons.join('；') }}
      </div>
      <p v-if="!frozenSnapshot && !proposalCatalogMatches" class="error">
        当前 Registry catalog 与后端 proposed scope 的能力包身份不一致，已禁止确认。
      </p>
      <label v-if="!frozenSnapshot" class="scope-legal-confirmation">
        <input
          v-model="sceneConfirmed"
          type="checkbox"
          :disabled="dimensionsLocked || !proposalCatalogMatches || fitAssessment?.result === 'blocked'"
        />
        <span>我已结合项目材料核对该场景，并确认按以下维度生成协查包。</span>
      </label>
    </CapabilityPackCard>

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
              :disabled="dimensionsLocked"
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
          {{ c.field }}：{{ conflictValueSummary(c) }}
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
              .map((id) => catalogDimensions.find((d) => d.id === id)?.name)
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
            v-for="dim in displayedDimensions"
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
          <p class="warn-note">未做完整杀毒扫描；下载前须经贵司终端或 DMS 安全扫描。</p>
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
            <button
              type="button"
              class="btn-primary sm"
              :disabled="frozenSnapshot ? !canRetryScope : !canConfirmScope"
              @click="generatePack"
            >
              {{ frozenSnapshot ? '按冻结快照重试' : '重新确认并生成' }}
            </button>
          </div>
          <p v-else class="muted">
            已选定 {{ selected.length }} 个维度
            <span v-if="selectedIssueCodes.length">· 含 {{ selectedIssueCodes.length }} 条 LLM 建议议题</span>
          </p>
          <button
            v-if="!submitting && !error"
            type="button"
            class="btn-primary"
            :disabled="frozenSnapshot ? !canRetryScope : !canConfirmScope"
            @click="generatePack"
          >
            {{ scope?.snapshot ? '按冻结快照重试' : '确认范围并生成' }}
          </button>
        </div>
        <div v-else class="auto-generate-status panel">
          <p class="muted">请至少勾选一个合规维度。</p>
          <button v-if="!frozenSnapshot && !proposalCatalogMatches" type="button" class="btn-primary" disabled>
            当前能力包验证失败，禁止确认
          </button>
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
