<script setup lang="ts">
import { ref, computed } from 'vue'
import { returnScenarioMaterials } from '@/api/client'
import type { InvestigationAdequacy, IncrementalRegen, RulesCatalog, Scenario } from '@/types/scenario'

const props = defineProps<{
  scenario: Scenario
  catalog: RulesCatalog
  adequacy: InvestigationAdequacy
  canReturn: boolean
  blocksReview?: boolean
  incrementalRegen?: IncrementalRegen | null
}>()

const emit = defineEmits<{
  materialsReturned: []
}>()

const returning = ref(false)
const returnNote = ref('')
const error = ref<string | null>(null)
const expandedDimensions = ref<string[]>([...(props.adequacy.dimensions?.map((d) => d.dimension_id) ?? [])])
const legalMissingElements = ref<string[]>([...(props.adequacy.suggest_material_return ?? [])])

function elementStatusLabel(status: string) {
  if (status === 'covered') return '已覆盖'
  if (status === 'at_risk') return '待核实'
  if (status === 'not_applicable') return '不适用'
  return '缺项'
}

function elementStatusClass(status: string) {
  if (status === 'covered') return 'ok'
  if (status === 'at_risk') return 'warn'
  if (status === 'not_applicable') return 'muted'
  return 'rejected'
}

function toggleExpanded(id: string) {
  const set = new Set(expandedDimensions.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  expandedDimensions.value = [...set]
}

function toggleMissingElement(id: string) {
  const set = new Set(legalMissingElements.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  legalMissingElements.value = [...set]
}

function elementLabel(id: string) {
  return props.adequacy.element_labels?.[id] || id
}

const dimensions = computed(() => props.adequacy.dimensions ?? [])

async function returnMaterials() {
  if (!props.canReturn || !legalMissingElements.value.length) return
  returning.value = true
  error.value = null
  try {
    const dims =
      props.scenario.compliance_dimensions.length > 0
        ? props.scenario.compliance_dimensions
        : props.adequacy.compliance_dimensions
    await returnScenarioMaterials(props.scenario.id, {
      compliance_dimensions: dims,
      missing_elements: legalMissingElements.value,
      note: returnNote.value.trim() || null,
    })
    emit('materialsReturned')
  } catch (e: unknown) {
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '打回失败'
    } else {
      error.value = '打回失败'
    }
  } finally {
    returning.value = false
  }
}
</script>

<template>
  <section class="panel investigation-adequacy-section">
    <div class="investigation-adequacy-head">
      <h2>① 范围与构成要件（协查包聚合视图）</h2>
      <p class="muted">
        以下由<strong>条目级 RAG + 匹配度 + 材料预检</strong>聚合而成，与下方清单复核同源；发现材料事实不足时可随时打回业务。
      </p>
      <div class="adequacy-stats">
        <span class="badge ok">简报通过 {{ adequacy.brief_summary.passed_count }} 条</span>
        <span class="badge rejected">门控未过 {{ adequacy.brief_summary.blocked_count }} 条</span>
        <span v-if="scenario.investigation_settings?.match_threshold" class="badge muted-badge">
          阈值 {{ scenario.investigation_settings.match_threshold }} 分
        </span>
        <span v-if="scenario.investigation_settings?.retrieval_top_k" class="badge muted-badge">
          Top {{ scenario.investigation_settings.retrieval_top_k }} 法条
        </span>
        <span v-if="adequacy.tier_report?.S1 != null" class="badge ok">S1 {{ adequacy.tier_report.S1 }}</span>
        <span v-if="adequacy.tier_report?.S2 != null" class="badge warn">S2 {{ adequacy.tier_report.S2 }}</span>
        <span v-if="adequacy.tier_report?.S3" class="badge rejected">S3 硬阻断 {{ adequacy.tier_report.S3 }}</span>
        <span v-if="blocksReview" class="badge rejected">Gate A 未通过 · 清单复核已锁定</span>
        <span v-else-if="!adequacy.is_investigation_ready" class="badge warn">存在待补充构成要件</span>
        <span v-else class="badge ok">构成要件整体可协查</span>
      </div>
      <p v-if="blocksReview" class="gate-incomplete-banner">
        <template v-if="adequacy.tier_report?.has_hard_block">
          存在 S3 硬阻断条目（{{ (adequacy.tier_report.s3_codes || []).slice(0, 4).join('、') }}）：高优先级且无可靠法条支撑，须补充材料或调整检索后再复核。
        </template>
        <template v-else>
          构成要件仍不完整，请先打回业务补充材料。重新生成协查包且 Gate A 通过后，方可进入下方清单条目复核。
        </template>
      </p>
      <p v-else-if="incrementalRegen?.mode === 'incremental'" class="incremental-regen-banner">
        增量更新：重算
        <strong>{{ incrementalRegen.target_codes.length }}</strong>
        条关联核查项 / 构成要件，沿用
        <strong>{{ incrementalRegen.frozen_codes.length }}</strong>
        条未变更结果（材料字段变更：{{ incrementalRegen.changed_fields.join('、') || '无' }}）。
      </p>
      <div v-if="scenario.conflict_flags?.length" class="conflict-banner red-flag-banner">
        <strong>红旗提示（材料 vs 公开线索 · {{ scenario.conflict_flags.length }} 项）</strong>
        <p class="muted">以下为非阻断提示，供 Gate A 与清单复核参考；不构成法律意见。</p>
        <ul class="conflict-banner-list">
          <li
            v-for="flag in scenario.conflict_flags"
            :key="flag.id"
            class="conflict-banner-item"
          >
            <div class="conflict-banner-item-head">
              <span class="badge" :class="flag.severity === 'medium' ? 'warn' : 'muted-badge'">
                {{ flag.severity }}
              </span>
              <strong>{{ flag.title }}</strong>
            </div>
            <p>{{ flag.summary }}</p>
            <p v-if="flag.material_claim" class="muted">材料表述：{{ flag.material_claim }}</p>
            <p v-if="flag.suggested_action" class="field-conflict-hint">{{ flag.suggested_action }}</p>
          </li>
        </ul>
      </div>
    </div>

    <div class="material-gate-body">
      <div
        v-for="block in dimensions"
        :key="block.dimension_id"
        class="gate-dimension-block"
        :class="{ 'gate-dimension-incomplete': !block.is_complete }"
      >
        <button type="button" class="gate-dimension-head" @click="toggleExpanded(block.dimension_id)">
          <div class="gate-dimension-title">
            <strong>{{ block.dimension_name }}</strong>
            <span class="dim-pt">{{ block.dimension_name_pt }}</span>
          </div>
          <span class="badge" :class="block.is_complete ? 'ok' : 'rejected'">
            {{ block.is_complete ? '可协查' : '有缺口' }}
          </span>
          <span class="gate-expand-icon">{{ expandedDimensions.includes(block.dimension_id) ? '−' : '+' }}</span>
        </button>

        <div v-show="expandedDimensions.includes(block.dimension_id)" class="gate-dimension-body">
          <div
            v-for="el in block.elements"
            :key="el.id"
            class="gate-element-row"
            :class="`gate-element-${el.status}`"
          >
            <div class="gate-element-main">
              <div class="gate-element-head">
                <strong>{{ el.label }}</strong>
                <span class="badge status-badge" :class="elementStatusClass(el.status)">
                  {{ elementStatusLabel(el.status) }}
                </span>
                <span v-if="el.carry_forward" class="badge ok sm">沿用上一轮</span>
              </div>
              <p v-if="el.excerpt" class="gate-element-excerpt">{{ el.excerpt }}</p>
              <p class="muted gate-element-rationale">{{ el.rationale }}</p>
              <p v-if="el.linked_codes.length" class="muted gate-element-source">
                关联核查项：{{ el.linked_codes.join('、') }}
                <template v-if="el.avg_match_score"> · 均匹配 {{ el.avg_match_score }}</template>
              </p>
            </div>
            <label
              v-if="canReturn && ['missing', 'at_risk'].includes(el.status)"
              class="gate-element-return-check"
            >
              <input
                type="checkbox"
                :checked="legalMissingElements.includes(el.id)"
                @change="toggleMissingElement(el.id)"
              />
              打回此项
            </label>
          </div>
        </div>
      </div>

      <div v-if="canReturn" class="material-return-block">
        <h4>打回补充材料</h4>
        <p class="muted">系统已预选可能缺材料的构成要件；未定稿前均可打回，已生成协查包将归档为草稿。</p>
        <p v-if="legalMissingElements.length" class="missing-field-summary muted">
          已选 {{ legalMissingElements.length }} 项：{{ legalMissingElements.map(elementLabel).join('、') }}
        </p>
        <label class="return-note-field">
          <span>退回说明</span>
          <textarea v-model="returnNote" rows="2" placeholder="例如：请补充分阶段用工计划与本地雇员规模" />
        </label>
        <p class="error" v-if="error">{{ error }}</p>
        <button
          type="button"
          class="btn-secondary"
          :disabled="!legalMissingElements.length || returning"
          @click="returnMaterials"
        >
          {{ returning ? '打回中…' : `打回补充材料（${legalMissingElements.length} 项）` }}
        </button>
      </div>
    </div>
  </section>
</template>
