<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { fetchScenario } from '@/api/client'
import type { Scenario } from '@/types/scenario'

const route = useRoute()
const scenario = ref<Scenario | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const checklistFeedback = computed(() => scenario.value?.business_feedback)
const materialFeedback = computed(() => scenario.value?.material_feedback)
const isMaterialReturn = computed(() => materialFeedback.value?.is_returned === true)
const canRevise = computed(() => !!scenario.value?.can_revise || scenario.value?.status === 'returned_for_revision')

const steps = computed(() => {
  if (!scenario.value) return []
  const status = scenario.value.status
  const finalized = ['review_approved', 'review_partial', 'review_rejected'].includes(status)
  const returned = status === 'returned_for_revision'
  const inReview = status === 'review_in_progress' || finalized
  const scopeConfirmed = status !== 'pending_scope'
  const materialReturned = isMaterialReturn.value

  return [
    {
      key: 'materials',
      title: '已提交材料',
      done: true,
      current: status === 'pending_scope' && !returned,
    },
    {
      key: 'scope',
      title: materialReturned ? '待补充材料（范围已选定）' : '法务确认协查范围',
      done: scopeConfirmed,
      current: status === 'pending_scope' || (returned && materialReturned),
    },
    {
      key: 'review',
      title: '法务复核中',
      done: inReview || (returned && !materialReturned),
      current: status === 'review_in_progress',
    },
    {
      key: 'revise',
      title: materialReturned ? '待补充提交表' : '待业务补充',
      done: returned || finalized,
      current: returned,
    },
    {
      key: 'done',
      title: '复核定稿完成',
      done: finalized,
      current: finalized && !returned,
    },
  ]
})

function dimensionLabel(id: string) {
  const labels: Record<string, string> = {
    labor: '劳工用工',
    foreign_investment: '外资准入',
    tax: '联邦/州/市税制',
    environment: '环保许可',
    industry_access: '行业准入与安全生产',
  }
  return labels[id] || id
}

onMounted(async () => {
  try {
    scenario.value = await fetchScenario(Number(route.params.id))
  } catch {
    error.value = '无法加载进度，请返回工作台重试'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="progress-page page-stack">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error banner-error">{{ error }}</div>
    <template v-else-if="scenario">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">业务协查 · 进度跟踪</p>
          <h1>{{ scenario.project_name }}</h1>
          <p class="muted" v-if="canRevise && isMaterialReturn">
            法务已驳回提交表中未覆盖的<strong>构成要件</strong>。请在本项目核对表中修改后重新提交，无需重新上传文件（除非法务另有要求）。
          </p>
          <p class="muted" v-else-if="canRevise">
            法务已退回本项目，请根据下方批注<strong>补充材料</strong>后重新提交（无需新建项目）。
          </p>
          <p class="muted" v-else-if="scenario.status === 'pending_scope'">
            材料已提交。法务将选定协查维度并<strong>生成协查包</strong>（清单 + RAG + 简报），您无需选择合规维度。
          </p>
          <p class="muted" v-else>您无需在此做法律判断；法务反馈会显示在下方。</p>
          <p class="muted" v-if="scenario.revision_round">
            当前为第 {{ scenario.revision_round + 1 }} 轮协查
          </p>
        </div>
        <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
        <RouterLink :to="`/scenarios/${scenario.id}/extract`" class="btn-primary link-btn">查看AI抽取表</RouterLink>
      </header>

      <section class="panel progress-timeline">
        <h2>处理进度</h2>
        <ol class="timeline">
          <li v-for="step in steps" :key="step.key" :class="{ done: step.done, current: step.current }">
            <span class="timeline-dot" />
            <div>
              <strong>{{ step.title }}</strong>
              <p class="muted" v-if="step.current">当前阶段</p>
            </div>
          </li>
        </ol>
      </section>

      <section class="panel business-feedback-panel" v-if="materialFeedback">
        <h2>材料完整性反馈</h2>
        <p class="feedback-summary" :class="{ warn: materialFeedback.action_required }">
          {{ materialFeedback.summary }}
        </p>
        <p class="feedback-comment" v-if="materialFeedback.return_note">
          <strong>退回说明：</strong>{{ materialFeedback.return_note }}
        </p>
        <p class="muted" v-if="materialFeedback.selected_dimensions.length">
          协查维度：{{
            materialFeedback.selected_dimensions.map((id) => dimensionLabel(id)).join('、')
          }}
        </p>

        <div
          v-for="(elementIds, dimId) in materialFeedback.missing_elements_by_dimension || {}"
          :key="`el-${dimId}`"
          class="material-feedback-group"
        >
          <strong>{{ dimId === '_general' ? '通用' : dimensionLabel(String(dimId)) }}</strong>
          <ul class="feedback-list compact">
            <li v-for="eid in elementIds" :key="`${dimId}-${eid}`" class="feedback-item">
              <span class="decision-badge rejected">需补充</span>
              <strong>{{ materialFeedback.element_labels?.[eid] || eid }}</strong>
            </li>
          </ul>
        </div>

        <div
          v-if="!(materialFeedback.missing_elements_by_dimension && Object.keys(materialFeedback.missing_elements_by_dimension).length)"
          v-for="(fields, dimId) in materialFeedback.missing_by_dimension"
          :key="dimId"
          class="material-feedback-group"
        >
          <strong>{{ dimId === '_general' ? '通用' : dimensionLabel(String(dimId)) }}</strong>
          <ul class="feedback-list compact">
            <li v-for="key in fields" :key="`${dimId}-${key}`" class="feedback-item">
              <span class="decision-badge rejected">需补充</span>
              <strong>{{ materialFeedback.field_labels[key] || key }}</strong>
            </li>
          </ul>
        </div>

        <div class="feedback-actions" v-if="canRevise && isMaterialReturn">
          <RouterLink :to="`/scenarios/${scenario.id}/edit`" class="btn-primary link-btn">
            修改核对表并重新提交
          </RouterLink>
        </div>
      </section>

      <section class="panel business-feedback-panel" v-if="checklistFeedback">
        <h2>清单复核反馈</h2>
        <p class="feedback-summary" :class="{ warn: checklistFeedback.action_required || checklistFeedback.is_returned }">
          {{ checklistFeedback.summary }}
        </p>
        <p class="feedback-comment" v-if="checklistFeedback.return_note">
          <strong>退回说明：</strong>{{ checklistFeedback.return_note }}
        </p>
        <p class="muted feedback-stats">
          已确认 {{ checklistFeedback.approved_count }} · 已驳回 {{ checklistFeedback.rejected_count }} · 待处理
          {{ checklistFeedback.pending_count }}
        </p>

        <ul v-if="checklistFeedback.items.length" class="feedback-list">
          <li v-for="item in checklistFeedback.items" :key="item.code" class="feedback-item">
            <div class="feedback-item-head">
              <span class="item-code">{{ item.code }}</span>
              <span class="decision-badge" :class="item.decision === 'rejected' ? 'rejected' : 'pending'">
                {{ item.decision === 'rejected' ? '已驳回' : '待确认' }}
              </span>
              <span class="badge pri-medium" v-if="item.external_counsel_required">需外聘</span>
            </div>
            <strong>{{ item.title }}</strong>
            <p class="muted" v-if="item.dimension_name">{{ item.dimension_name }}</p>
            <p class="feedback-comment" v-if="item.comment">
              <strong>法务批注：</strong>{{ item.comment }}
            </p>
          </li>
        </ul>

        <div class="feedback-actions" v-if="canRevise && !isMaterialReturn">
          <RouterLink :to="`/scenarios/${scenario.id}/edit`" class="btn-primary link-btn">
            补充材料并重新提交
          </RouterLink>
        </div>
        <div class="feedback-actions" v-else-if="checklistFeedback.action_required">
          <p class="muted">如有疑问请联系法务同事；已定稿项目请按内部制度处理。</p>
        </div>
      </section>

      <section class="panel" v-if="!materialFeedback && !checklistFeedback">
        <h2>AI 抽取信息表</h2>
        <p class="muted">提交时可回看从方案抽取或手动填写的项目字段及原文依据。</p>
        <div class="action-row stack-actions">
          <RouterLink :to="`/scenarios/${scenario.id}/extract`" class="btn-primary link-btn full">
            查看AI抽取表
          </RouterLink>
        </div>
        <ul class="progress-notes">
          <li v-if="scenario.status === 'pending_scope'">
            法务确认协查范围后，系统将自动生成清单、法条检索与双语简报。
          </li>
          <li v-else>清单、法条检索与双语简报已由法务确认范围后自动生成。</li>
          <li>法务开始复核后，驳回意见与「需外聘」标记会显示在本页上方。</li>
          <li>若被退回补充，您可在<strong>同一项目</strong>修改后重新提交。</li>
        </ul>
      </section>
    </template>
  </div>
</template>
