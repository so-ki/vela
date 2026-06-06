<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { fetchScenario, retrieveLegalSources } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { ChecklistSection, Scenario } from '@/types/scenario'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
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

const sectionOpen = ref<Record<string, boolean>>({})
const itemOpen = ref<Record<string, boolean>>({})

function initCollapseState(sections: ChecklistSection[]) {
  if (!sections.length) return
  const nextSection: Record<string, boolean> = { ...sectionOpen.value }
  const nextItem: Record<string, boolean> = { ...itemOpen.value }
  for (const section of sections) {
    if (!(section.dimension_id in nextSection)) {
      nextSection[section.dimension_id] = false
    }
    for (const item of section.items) {
      if (!(item.code in nextItem)) {
        nextItem[item.code] = false
      }
    }
  }
  sectionOpen.value = nextSection
  itemOpen.value = nextItem
}

watch(
  displaySections,
  (sections) => {
    initCollapseState(sections)
  },
  { immediate: true },
)

function isSectionOpen(id: string) {
  return sectionOpen.value[id] ?? false
}

function isItemOpen(code: string) {
  return itemOpen.value[code] ?? false
}

function toggleSection(id: string) {
  sectionOpen.value = { ...sectionOpen.value, [id]: !isSectionOpen(id) }
}

function toggleItem(code: string) {
  itemOpen.value = { ...itemOpen.value, [code]: !isItemOpen(code) }
}

function setAllSections(open: boolean) {
  const next: Record<string, boolean> = { ...sectionOpen.value }
  for (const section of displaySections.value) {
    next[section.dimension_id] = open
  }
  sectionOpen.value = next
}

function setAllItems(open: boolean) {
  const next: Record<string, boolean> = { ...itemOpen.value }
  for (const section of displaySections.value) {
    for (const item of section.items) {
      next[item.code] = open
    }
  }
  itemOpen.value = next
}

const openSectionCount = computed(
  () => displaySections.value.filter((s) => isSectionOpen(s.dimension_id)).length,
)

function scenarioHasBrief(status: string | undefined) {
  if (!status || status === 'checklist_generated') return false
  return (
    status === 'brief_generated' ||
    status === 'brief_blocked' ||
    status === 'pending_legal_review' ||
    status === 'returned_for_revision' ||
    status === 'review_in_progress' ||
    status.startsWith('review_')
  )
}

const hasBrief = computed(() => scenarioHasBrief(scenario.value?.status))

const showViewBrief = computed(
  () => auth.isLegal && (route.query.from === 'review' || hasBrief.value),
)

const briefLinkQuery = computed(() =>
  route.query.from === 'review' ? { from: 'review' } : undefined,
)

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
  <div class="checklist-page" :class="{ 'with-review-return': auth.isLegal && route.query.from === 'review' }">
    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="error && !displaySections.length" class="error banner-error">{{ error }}</div>
    <template v-else-if="scenario && checklist">
      <header class="page-header">
        <div>
          <p class="eyebrow dark">
            {{ auth.isBusiness ? '业务协查 · 核查清单（只读）' : '专项核查清单 · Step 3 法源绑定' }}
          </p>
          <h1>{{ checklist.title }}</h1>
          <p class="meta">
            协查法域：<strong>{{ checklist.industry_pack_name || checklist.detected_industry_name }}</strong> ·
            动作类型：<strong>{{ checklist.detected_action_type_name }}</strong> ·
            共 <strong>{{ checklist.total_items }}</strong> 条
          </p>
          <p class="meta sub-sectors" v-if="checklist.detected_sub_sectors?.length">
            识别子赛道：
            <span
              v-for="sub in checklist.detected_sub_sectors"
              :key="sub.id"
              class="badge sub-sector"
            >{{ sub.name }}</span>
          </p>
          <p class="meta" v-if="retrievalNote">{{ retrievalNote }}</p>
          <p class="meta warn" v-if="retrieving">正在检索 LexML / STF / STJ 法源…</p>
        </div>
        <div class="header-actions">
          <RouterLink
            v-if="auth.isLegal && route.query.from === 'review' && scenario"
            :to="{ name: 'review', params: { id: scenario.id } }"
            class="btn-primary link-btn"
          >
            返回继续复核
          </RouterLink>
          <RouterLink
            v-if="auth.isBusiness"
            :to="{ name: 'scenario-progress', params: { id: scenario.id } }"
            class="btn-secondary link-btn"
          >
            查看进度
          </RouterLink>
          <RouterLink
            v-if="auth.isBusiness"
            :to="{ name: 'brief', params: { id: scenario.id } }"
            class="btn-primary link-btn"
          >
            查看双语简报
          </RouterLink>
          <RouterLink
            v-if="showViewBrief && scenario"
            :to="{ name: 'brief', params: { id: scenario.id }, query: briefLinkQuery }"
            class="btn-secondary link-btn"
          >
            查看简报
          </RouterLink>
          <button
            v-else-if="auth.isLegal"
            type="button"
            class="btn-primary"
            :disabled="generatingBrief || retrieving || !legalSections"
            @click="goToBrief"
          >
            {{ generatingBrief ? '跳转中…' : '生成双语简报' }}
          </button>
          <RouterLink to="/" class="btn-secondary link-btn">返回工作台</RouterLink>
        </div>
      </header>

      <div class="disclaimer-banner" v-if="auth.isBusiness">
        清单与法条检索结果仅供业务侧<strong>查阅</strong>，不构成正式法律意见；法律判断与定稿由法务完成。
      </div>
      <div class="disclaimer-banner" v-else-if="legalSections">
        以下法条片段来自 LexML / STF / STJ 开放法源索引，仅供协查参考，不构成正式法律意见。匹配度低于 70 分须标注「需法务复核」。
      </div>
      <div class="disclaimer-banner" v-else>
        {{ checklist.disclaimer }}
      </div>

      <p class="error banner-error" v-if="error">{{ error }}</p>

      <div class="collapse-toolbar panel" v-if="displaySections.length">
        <span class="muted">
          共 {{ displaySections.length }} 个合规维度 · 已展开 {{ openSectionCount }} 个
        </span>
        <div class="collapse-toolbar-actions">
          <button type="button" class="btn-text" @click="setAllSections(true)">展开全部维度</button>
          <button type="button" class="btn-text" @click="setAllSections(false)">折叠全部维度</button>
          <button type="button" class="btn-text" @click="setAllItems(true)">展开全部条目</button>
          <button type="button" class="btn-text" @click="setAllItems(false)">折叠全部条目</button>
        </div>
      </div>

      <section
        v-for="section in displaySections"
        :key="section.dimension_id"
        class="checklist-section panel collapsible-section"
        :class="{ 'is-open': isSectionOpen(section.dimension_id) }"
      >
        <button
          type="button"
          class="section-toggle"
          :aria-expanded="isSectionOpen(section.dimension_id)"
          @click="toggleSection(section.dimension_id)"
        >
          <span class="collapse-chevron" aria-hidden="true" />
          <div class="section-toggle-main">
            <h2>{{ section.dimension_name }}</h2>
            <span class="dim-pt">{{ section.dimension_name_pt }}</span>
          </div>
          <span class="badge ok">{{ section.items.length }} 条</span>
        </button>

        <div v-show="isSectionOpen(section.dimension_id)" class="section-body">
          <p class="section-desc">{{ section.description }}</p>

          <div class="checklist-items">
            <article
              v-for="item in section.items"
              :key="item.code"
              class="checklist-item collapsible-item"
              :class="{ 'is-open': isItemOpen(item.code) }"
            >
              <button
                type="button"
                class="item-toggle"
                :aria-expanded="isItemOpen(item.code)"
                @click="toggleItem(item.code)"
              >
                <span class="collapse-chevron sm" aria-hidden="true" />
                <div class="item-toggle-main">
                  <div class="item-head">
                    <span class="item-code">{{ item.code }}</span>
                    <span
                      v-for="tag in item.sub_sector_tags || []"
                      :key="tag"
                      class="badge sub-sector"
                    >{{ tag }}</span>
                    <span class="badge" :class="'pri-' + item.priority">
                      {{ priorityLabel[item.priority] || item.priority }}优先级
                    </span>
                    <span class="score">清单相关度 {{ item.relevance_score }}</span>
                  </div>
                  <h3>{{ item.title }}</h3>
                </div>
              </button>

              <div v-show="isItemOpen(item.code)" class="item-body">
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
              </div>
            </article>
          </div>
        </div>
      </section>

      <div v-if="auth.isLegal && route.query.from === 'review' && scenario" class="review-return-bar">
        <RouterLink
          :to="{ name: 'review', params: { id: scenario.id } }"
          class="btn-primary link-btn review-return-btn"
        >
          ← 返回继续复核
        </RouterLink>
      </div>
    </template>
  </div>
</template>
