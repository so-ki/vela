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
const matchThreshold = ref(70)
const retrievalTopK = ref(3)
const submitting = ref(false)
const error = ref<string | null>(null)
const dimensionsLocked = ref(false)

let generateTimer: ReturnType<typeof setTimeout> | null = null

const archivedFiles = computed(() => props.scenario.document_extract?.archived_files ?? [])

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
</script>

<template>
  <section class="panel review-gate-section">
    <div class="review-gate-head">
      <h2>① 选定协查范围</h2>
      <p class="muted">
        勾选合规维度后，系统将<strong>自动生成协查包</strong>（清单 · 多源 RAG · 匹配度 · 简报）；生成完成后在本页下方查看构成要件聚合与清单复核。材料是否齐备，以生成后的 Gate A 聚合视图为准。
      </p>
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
          <p class="muted threshold-hint">
            低于该分数的 RAG 命中将标注「需法务复核」；阈值越高，门控越严。
          </p>
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
          <p class="muted threshold-hint">
            默认 3 条；调高可展示更多依据，但复核与 grounding 工作量会增加。
          </p>
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
            <p class="muted">正在执行：核查项定位 → 核查清单 → 多源 RAG → 匹配度 → 简报草稿</p>
          </div>
          <div v-else-if="error" class="gate-error-banner">
            <p class="error">{{ error }}</p>
            <button type="button" class="btn-primary sm" @click="generatePack">重试生成</button>
          </div>
          <p v-else class="muted">已选定 {{ selected.length }} 个维度，即将自动生成协查包…</p>
        </div>
        <div v-else class="auto-generate-status panel">
          <p class="muted">请至少勾选一个合规维度。</p>
        </div>
      </div>
    </div>

    <div class="material-gate-footer">
      <RouterLink :to="`/scenarios/${scenario.id}/extract`" class="btn-secondary link-btn sm">
        查看 AI 抽取表
      </RouterLink>
    </div>
  </section>
</template>
