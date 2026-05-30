<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { fetchScenario, retrieveLegalSources } from '@/api/client'
import type { ChecklistSection, Scenario } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const scenario = ref<Scenario | null>(null)
const legalSections = ref<ChecklistSection[] | null>(null)
const loading = ref(true)
const retrieving = ref(false)
const generatingBrief = ref(false)
const error = ref<string | null>(null)
const retrievalNote = ref<string | null>(null)

const priorityLabel: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

onMounted(async () => {
  try {
    const id = Number(route.params.id)
    scenario.value = await fetchScenario(id)
    await runRetrieval(id)
  } catch {
    error.value = '无法加载核查清单'
  } finally {
    loading.value = false
  }
})

async function runRetrieval(id: number) {
  retrieving.value = true
  error.value = null
  try {
    const result = await retrieveLegalSources(id)
    legalSections.value = result.sections
    retrievalNote.value = `已绑定 ${result.total_hits} 条法源片段（索引 ${result.index_status?.document_count ?? 0} 条）`
    if (result.zero_hit_items?.length) {
      retrievalNote.value += `；${result.zero_hit_items.length} 条未命中，建议扩大检索`
    }
  } catch (e: unknown) {
    const msg = extractError(e)
    error.value = msg
  } finally {
    retrieving.value = false
  }
}

function extractError(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const resp = (e as { response?: { status?: number; data?: { detail?: string } } }).response
    if (resp?.status === 404) return '接口未找到，请重启后端（./scripts/start.sh）'
    if (typeof resp?.data?.detail === 'string') return resp.data.detail
  }
  return '法条检索失败，请确认已安装 RAG 依赖并重启服务'
}

const checklist = computed(() => scenario.value?.checklist)
const displaySections = computed(() => legalSections.value || checklist.value?.sections || [])

async function goToBrief() {
  if (!scenario.value) return
  generatingBrief.value = true
  error.value = null
  try {
    await router.push({ name: 'brief', params: { id: scenario.value.id } })
  } catch {
    error.value = '无法打开简报页'
  } finally {
    generatingBrief.value = false
  }
}
</script>

<template>
  <div class="checklist-page">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error && !displaySections.length" class="error banner-error">{{ error }}</div>
    <template v-else-if="scenario && checklist">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">专项核查清单 · Step 3 法源绑定</p>
          <h1>{{ checklist.title }}</h1>
          <p class="meta">
            识别行业：<strong>{{ checklist.detected_industry_name }}</strong> ·
            动作类型：<strong>{{ checklist.detected_action_type_name }}</strong> ·
            共 <strong>{{ checklist.total_items }}</strong> 条
          </p>
          <p class="meta" v-if="retrievalNote">{{ retrievalNote }}</p>
          <p class="meta warn" v-if="retrieving">正在检索 LexML / STF / STJ 法源…</p>
        </div>
        <RouterLink to="/scenarios/new" class="btn-secondary link-btn">新建场景</RouterLink>
      </header>

      <div class="disclaimer-banner" v-if="legalSections">
        以下法条片段来自 LexML / STF / STJ 开放法源索引，仅供协查参考，不构成正式法律意见。匹配度低于 70 分须标注「需法务复核」。
      </div>
      <div class="disclaimer-banner" v-else>
        {{ checklist.disclaimer }}
      </div>

      <p class="error banner-error" v-if="error">{{ error }}</p>

      <section
        v-for="section in displaySections"
        :key="section.dimension_id"
        class="checklist-section panel"
      >
        <div class="section-head">
          <div>
            <h2>{{ section.dimension_name }}</h2>
            <span class="dim-pt">{{ section.dimension_name_pt }}</span>
          </div>
          <span class="badge ok">{{ section.items.length }} 条</span>
        </div>
        <p class="section-desc">{{ section.description }}</p>

        <div class="checklist-items">
          <article v-for="item in section.items" :key="item.code" class="checklist-item">
            <div class="item-head">
              <span class="item-code">{{ item.code }}</span>
              <span class="badge" :class="'pri-' + item.priority">
                {{ priorityLabel[item.priority] || item.priority }}优先级
              </span>
              <span class="score">清单相关度 {{ item.relevance_score }}</span>
            </div>
            <h3>{{ item.title }}</h3>
            <p class="item-desc">{{ item.description }}</p>
            <p class="item-rationale">
              <strong>纳入理由：</strong>{{ item.rationale }}
            </p>

            <div v-if="item.legal_hits?.length" class="legal-hits">
              <h4>相关法条（Top {{ item.legal_hits.length }}）</h4>
              <div v-for="hit in item.legal_hits" :key="hit.id" class="legal-hit">
                <div class="hit-head">
                  <span class="source-badge">{{ hit.source_label }}</span>
                  <span class="badge" :class="hit.requires_review ? 'pri-medium' : 'ok'">
                    匹配度 {{ hit.match_score }}
                    <template v-if="hit.requires_review"> · 需法务复核</template>
                  </span>
                </div>
                <strong>{{ hit.title_zh || hit.title_pt }}</strong>
                <p class="hit-excerpt">{{ hit.excerpt_pt }}</p>
                <p class="hit-excerpt zh" v-if="hit.excerpt_zh">{{ hit.excerpt_zh }}</p>
                <p class="hit-meta">
                  {{ hit.validity }} · {{ hit.level }} · {{ hit.published_at }}
                </p>
                <a :href="hit.url" target="_blank" rel="noopener" class="hit-link">溯源：LexML / 法院门户 ↗</a>
              </div>
            </div>
            <p v-else class="no-hit muted">未检索到相关法条片段，建议扩大检索范围或外聘律所补充。</p>
          </article>
        </div>
      </section>

      <div class="next-step panel">
        <h2>下一步（Step 5）</h2>
        <p class="muted">条目级匹配度门控（阈值 70 分）通过后，自动汇编中葡双语法律风险简报。</p>
        <button
          type="button"
          class="btn-primary"
          :disabled="generatingBrief || retrieving || !legalSections"
          @click="goToBrief"
        >
          {{ generatingBrief ? '跳转中…' : '生成双语简报' }}
        </button>
        <p class="muted hint" v-if="!legalSections && !retrieving">请先等待法源检索完成</p>
      </div>
    </template>
  </div>
</template>
