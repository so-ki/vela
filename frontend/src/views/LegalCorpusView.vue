<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  fetchCorpusEntries,
  fetchCorpusMeta,
  fetchLegalStatus,
  rebuildCorpusIndex,
} from '@/api/client'

interface CorpusMeta {
  version: string
  content_status: string
  quality_notice?: string | null
  document_count: number
  sources: string[]
  levels: string[]
  dimensions: Array<{ id: string; name: string }>
  checklist_codes: Array<{ id: string; title: string; dimension: string }>
}

interface CorpusItem {
  id: string
  source: string
  urn: string
  url: string
  title_pt: string
  title_zh: string
  dimension: string
  level: string
  validity: string
  published_at: string
  tags: string[]
  checklist_codes: string[]
  text_pt: string
  text_zh: string
  review_status: string
  verification_scope: string
  quarantine_reason?: string | null
}

const loading = ref(true)
const reindexing = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const meta = ref<CorpusMeta | null>(null)
const items = ref<CorpusItem[]>([])
const indexInfo = ref<{ mode?: string; document_count?: number } | null>(null)

const filterQ = ref('')
const filterDimension = ref('')
const filterSource = ref('')

const dimensionLabel = computed(() => {
  const map: Record<string, string> = {}
  meta.value?.dimensions.forEach((d) => {
    map[d.id] = d.name
  })
  return map
})

const filteredCount = computed(() => items.value.length)

async function loadData() {
  loading.value = true
  error.value = null
  try {
    const [m, list, status] = await Promise.all([
      fetchCorpusMeta(),
      fetchCorpusEntries({
        q: filterQ.value || undefined,
        dimension: filterDimension.value || undefined,
        source: filterSource.value || undefined,
      }),
      fetchLegalStatus().catch(() => null),
    ])
    meta.value = m
    items.value = list.items
    indexInfo.value = status
  } catch {
    error.value = '加载法源语料失败，请确认已用法务账号登录且后端已启动'
  } finally {
    loading.value = false
  }
}

async function runReindex() {
  reindexing.value = true
  error.value = null
  success.value = null
  try {
    const result = await rebuildCorpusIndex(true)
    success.value = result.index?.message || '索引重建完成'
    indexInfo.value = await fetchLegalStatus()
  } catch {
    error.value = '索引重建失败'
  } finally {
    reindexing.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="corpus-admin">
    <section class="hero-card">
      <div>
        <p class="eyebrow">法务专属</p>
        <h1>法源语料制品</h1>
        <p class="lead">
          当前版本展示的是经哈希固定的只读语料制品。候选变更须进入复核队列，并作为新的能力包版本发布；本页禁止原地改写。
        </p>
      </div>
      <div class="hero-actions">
        <RouterLink class="btn-secondary" to="/">返回工作台</RouterLink>
        <button type="button" class="btn-primary" disabled title="请通过候选复核与能力包发布流程更新">只读发布制品</button>
      </div>
    </section>

    <section class="panel stats-row">
      <div class="stat">
        <span class="stat-label">语料版本</span>
        <strong>{{ meta?.version ?? '—' }} · {{ meta?.content_status ?? '—' }}</strong>
      </div>
      <div class="stat">
        <span class="stat-label">条目总数</span>
        <strong>{{ meta?.document_count ?? '—' }}</strong>
      </div>
      <div class="stat">
        <span class="stat-label">当前列表</span>
        <strong>{{ filteredCount }}</strong>
      </div>
      <div class="stat">
        <span class="stat-label">检索模式</span>
        <strong>{{ indexInfo?.mode ?? '—' }}</strong>
      </div>
      <div class="stat actions">
        <button type="button" class="btn-secondary" :disabled="reindexing" @click="runReindex">
          {{ reindexing ? '重建中…' : '重建法源索引' }}
        </button>
      </div>
    </section>

    <p class="error" v-if="error">{{ error }}</p>
    <p class="success-msg" v-if="success">{{ success }}</p>

    <section class="panel">
      <div class="toolbar">
        <input v-model="filterQ" type="search" placeholder="搜索标题、ID 或核查项编号…" @keyup.enter="loadData" />
        <select v-model="filterDimension">
          <option value="">全部维度</option>
          <option v-for="d in meta?.dimensions ?? []" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <select v-model="filterSource">
          <option value="">全部来源</option>
          <option v-for="s in meta?.sources ?? []" :key="s" :value="s">{{ s }}</option>
        </select>
        <button type="button" class="btn-secondary" :disabled="loading" @click="loadData">
          {{ loading ? '加载中…' : '筛选' }}
        </button>
      </div>

      <div v-if="loading" class="muted">加载中…</div>
      <div v-else class="table-wrap">
        <table class="corpus-table">
          <thead>
            <tr>
              <th>中文标题</th>
              <th>维度</th>
              <th>来源</th>
              <th>核查项</th>
              <th>内容状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.id">
              <td>
                <strong>{{ item.title_zh }}</strong>
                <span class="sub">{{ item.id }}</span>
              </td>
              <td>{{ dimensionLabel[item.dimension] || item.dimension }}</td>
              <td>{{ item.source }}</td>
              <td>
                <span v-for="code in item.checklist_codes.slice(0, 3)" :key="code" class="code-tag">{{ code }}</span>
                <span v-if="item.checklist_codes.length > 3" class="muted">+{{ item.checklist_codes.length - 3 }}</span>
              </td>
              <td class="row-actions">
                <span :class="item.review_status === 'quarantined' ? 'status-quarantined' : 'muted'">
                  {{ item.review_status }} · 只读
                </span>
                <span v-if="item.quarantine_reason" class="sub">{{ item.quarantine_reason }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!items.length" class="muted empty">暂无匹配条目。</p>
      </div>
    </section>

    <section class="panel notice-panel">
      <h2>操作须知</h2>
      <p v-if="meta?.quality_notice" class="status-quarantined">{{ meta.quality_notice }}</p>
      <ul>
        <li>本页展示的是<strong>法源检索语料发布制品</strong>，不是单次协查结论；个案补充请在复核页批注。</li>
        <li>新增核查<strong>条目</strong>（如 IBAMA 新检查点）须由实施人员更新规则库，并在此绑定对应 <code>checklist_codes</code>。</li>
        <li>任何法规变化先作为候选记录，经法务核验、生成新制品哈希并发布新版本后，才允许重建索引。</li>
        <li>旧场景继续引用冻结快照；新版本发布与索引重建均须保留审计记录。</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.corpus-admin {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.hero-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}

.hero-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 1rem;
  align-items: end;
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: var(--muted);
  margin-bottom: 0.25rem;
}

.stat.actions {
  display: flex;
  justify-content: flex-end;
}

.success-msg {
  color: var(--ok);
  font-size: 0.9rem;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.toolbar input[type='search'] {
  flex: 1;
  min-width: 200px;
}

.toolbar select,
.toolbar input {
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.table-wrap {
  overflow-x: auto;
}

.corpus-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.corpus-table th,
.corpus-table td {
  padding: 0.65rem 0.5rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.corpus-table .sub {
  display: block;
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 0.15rem;
}

.code-tag {
  display: inline-block;
  font-size: 0.7rem;
  padding: 0.1rem 0.35rem;
  margin-right: 0.25rem;
  border-radius: 4px;
  background: #eef2ff;
  color: var(--primary);
}

.row-actions {
  white-space: nowrap;
}

.status-quarantined {
  color: var(--err);
  font-weight: 600;
}

.btn-text.danger {
  color: var(--err);
}

.form-panel {
  border: 2px solid var(--primary-light);
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.form-tip {
  margin-bottom: 1rem;
  font-size: 0.875rem;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem 1rem;
}

.form-grid label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.85rem;
}

.form-grid label.span-2 {
  grid-column: span 2;
}

.form-grid input,
.form-grid select,
.form-grid textarea {
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font: inherit;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}

.notice-panel ul {
  margin-left: 1.25rem;
  font-size: 0.9rem;
  color: var(--muted);
}

.notice-panel li {
  margin-bottom: 0.35rem;
}

.empty {
  padding: 1rem 0;
}

@media (max-width: 720px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-grid label.span-2 {
    grid-column: span 1;
  }
}
</style>
