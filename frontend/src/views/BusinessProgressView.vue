<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { fetchScenario } from '@/api/client'
import type { Scenario } from '@/types/scenario'

const route = useRoute()
const scenario = ref<Scenario | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const feedback = computed(() => scenario.value?.business_feedback)
const canRevise = computed(() => !!scenario.value?.can_revise || scenario.value?.status === 'returned_for_revision')

const steps = computed(() => {
  if (!scenario.value) return []
  const status = scenario.value.status
  const finalized = ['review_approved', 'review_partial', 'review_rejected'].includes(status)
  const returned = status === 'returned_for_revision'
  const inReview = status === 'review_in_progress' || finalized
  const submitted = status === 'pending_legal_review' || inReview || returned

  return [
    { key: 'submit', title: '已提交法务', done: submitted, current: status === 'pending_legal_review' },
    { key: 'review', title: '法务复核中', done: inReview || returned, current: status === 'review_in_progress' },
    { key: 'revise', title: '待业务补充', done: returned || finalized, current: returned },
    { key: 'done', title: '复核定稿完成', done: finalized, current: finalized && !returned },
  ]
})

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
  <div class="progress-page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error" class="error banner-error">{{ error }}</div>
    <template v-else-if="scenario">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">业务协查 · 进度跟踪</p>
          <h1>{{ scenario.project_name }}</h1>
          <p class="muted" v-if="canRevise">
            法务已退回本项目，请根据下方批注<strong>补充材料</strong>后重新提交（无需新建项目）。
          </p>
          <p class="muted" v-else>
            您无需在此做法律判断；法务反馈会显示在下方。
          </p>
          <p class="muted" v-if="scenario.revision_round">
            当前为第 {{ scenario.revision_round + 1 }} 轮协查
          </p>
        </div>
        <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
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

      <section class="panel business-feedback-panel" v-if="feedback">
        <h2>法务反馈</h2>
        <p class="feedback-summary" :class="{ warn: feedback.action_required || feedback.is_returned }">
          {{ feedback.summary }}
        </p>
        <p class="feedback-comment" v-if="feedback.return_note">
          <strong>退回说明：</strong>{{ feedback.return_note }}
        </p>
        <p class="muted feedback-stats">
          已确认 {{ feedback.approved_count }} · 已驳回 {{ feedback.rejected_count }} · 待处理 {{ feedback.pending_count }}
        </p>

        <ul v-if="feedback.items.length" class="feedback-list">
          <li v-for="item in feedback.items" :key="item.code" class="feedback-item">
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

        <div class="feedback-actions" v-if="canRevise">
          <RouterLink :to="`/scenarios/${scenario.id}/edit`" class="btn-primary link-btn">
            补充材料并重新提交
          </RouterLink>
        </div>
        <div class="feedback-actions" v-else-if="feedback.action_required">
          <p class="muted">如有疑问请联系法务同事；已定稿项目请按内部制度处理。</p>
        </div>
      </section>

      <section class="panel" v-else>
        <h2>说明</h2>
        <ul class="progress-notes">
          <li>清单、法条检索与双语简报已由系统自动生成并提交法务。</li>
          <li>法务开始复核后，驳回意见与「需外聘」标记会显示在本页。</li>
          <li>若被退回补充，您可在<strong>同一项目</strong>修改后重新提交。</li>
        </ul>
      </section>
    </template>
  </div>
</template>
