<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  createCorpusEntry,
  deleteCorpusEntry,
  fetchCorpusEntries,
  fetchCorpusMeta,
  fetchLegalStatus,
  rebuildCorpusIndex,
  updateCorpusEntry,
} from '@/api/client'

interface CorpusMeta {
  version: string
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
}

const loading = ref(true)
const saving = ref(false)
const reindexing = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const meta = ref<CorpusMeta | null>(null)
const items = ref<CorpusItem[]>([])
const indexInfo = ref<{ mode?: string; document_count?: number } | null>(null)

const filterQ = ref('')
const filterDimension = ref('')
const filterSource = ref('')

const editingId = ref<string | null>(null)
const showForm = ref(false)

const emptyForm = (): CorpusItem => ({
  id: '',
  source: 'lexml',
  urn: '',
  url: '',
  title_pt: '',
  title_zh: '',
  dimension: 'labor',
  level: 'federal',
  validity: 'vigente',
  published_at: new Date().toISOString().slice(0, 10),
  tags: [],
  checklist_codes: [],
  text_pt: '',
  text_zh: '',
})

const form = reactive<CorpusItem>(emptyForm())
const tagsInput = ref('')
const codesInput = ref('')

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

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  tagsInput.value = ''
  codesInput.value = ''
  showForm.value = true
  success.value = null
}

function openEdit(item: CorpusItem) {
  editingId.value = item.id
  Object.assign(form, { ...item })
  tagsInput.value = item.tags.join(', ')
  codesInput.value = item.checklist_codes.join(', ')
  showForm.value = true
  success.value = null
}

function closeForm() {
  showForm.value = false
  editingId.value = null
}

function syncArrayFields() {
  form.tags = tagsInput.value
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
  form.checklist_codes = codesInput.value
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function saveEntry() {
  saving.value = true
  error.value = null
  success.value = null
  syncArrayFields()
  try {
    if (editingId.value) {
      const { id, ...payload } = form
      await updateCorpusEntry(editingId.value, payload)
      success.value = '条目已更新，请记得重建索引使检索生效'
    } else {
      const payload = { ...form }
      if (!payload.id) delete (payload as Partial<CorpusItem>).id
      await createCorpusEntry(payload)
      success.value = '新条目已添加，请重建索引使检索生效'
    }
    closeForm()
    await loadData()
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    error.value = typeof msg === 'string' ? msg : '保存失败，请检查必填项'
  } finally {
    saving.value = false
  }
}

async function removeEntry(item: CorpusItem) {
  if (!window.confirm(`确定删除「${item.title_zh || item.title_pt}」？此操作不可撤销。`)) return
  saving.value = true
  error.value = null
  try {
    await deleteCorpusEntry(item.id)
    success.value = '条目已删除，请重建索引'
    if (editingId.value === item.id) closeForm()
    await loadData()
  } catch {
    error.value = '删除失败'
  } finally {
    saving.value = false
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
        <h1>法源语料维护</h1>
        <p class="lead">
          补充或更新平台内置法条片段，供协查检索绑定。修改后须<strong>重建索引</strong>，新协查才会引用最新语料。
        </p>
      </div>
      <div class="hero-actions">
        <RouterLink class="btn-secondary" to="/">返回工作台</RouterLink>
        <button type="button" class="btn-primary" @click="openCreate">新增法条条目</button>
      </div>
    </section>

    <section class="panel stats-row">
      <div class="stat">
        <span class="stat-label">语料版本</span>
        <strong>{{ meta?.version ?? '—' }}</strong>
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
              <th>操作</th>
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
                <button type="button" class="btn-text" @click="openEdit(item)">编辑</button>
                <button type="button" class="btn-text danger" @click="removeEntry(item)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!items.length" class="muted empty">暂无匹配条目。</p>
      </div>
    </section>

    <section v-if="showForm" class="panel form-panel">
      <div class="form-header">
        <h2>{{ editingId ? '编辑法条条目' : '新增法条条目' }}</h2>
        <button type="button" class="btn-text" @click="closeForm">关闭</button>
      </div>

      <p class="muted form-tip">
        请先在 LexML / STF / STJ 等官方法源核对 URN 与原文，再录入平台。`checklist_codes` 须与核查清单编号一致（如 LAB-001）。
      </p>

      <div class="form-grid">
        <label v-if="!editingId">
          条目 ID（可选，留空自动生成）
          <input v-model="form.id" type="text" placeholder="lexml-xxx" />
        </label>
        <label v-else>
          条目 ID
          <input :value="form.id" type="text" disabled />
        </label>

        <label>
          法源类型
          <select v-model="form.source">
            <option v-for="s in meta?.sources ?? []" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>

        <label>
          合规维度
          <select v-model="form.dimension">
            <option v-for="d in meta?.dimensions ?? []" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </label>

        <label>
          效力层级
          <select v-model="form.level">
            <option v-for="l in meta?.levels ?? []" :key="l" :value="l">{{ l }}</option>
          </select>
        </label>

        <label>
          效力状态
          <input v-model="form.validity" type="text" placeholder="vigente" />
        </label>

        <label>
          发布日期
          <input v-model="form.published_at" type="date" />
        </label>

        <label class="span-2">
          葡语标题
          <input v-model="form.title_pt" type="text" required />
        </label>

        <label class="span-2">
          中文标题
          <input v-model="form.title_zh" type="text" required />
        </label>

        <label class="span-2">
          URN
          <input v-model="form.urn" type="text" placeholder="urn:lex:br:..." />
        </label>

        <label class="span-2">
          官方链接
          <input v-model="form.url" type="url" placeholder="https://www.lexml.gov.br/..." />
        </label>

        <label class="span-2">
          关联核查项（逗号分隔）
          <input v-model="codesInput" type="text" placeholder="LAB-001, SEC-012" list="checklist-codes" />
          <datalist id="checklist-codes">
            <option v-for="c in meta?.checklist_codes ?? []" :key="c.id" :value="c.id">
              {{ c.title }}
            </option>
          </datalist>
        </label>

        <label class="span-2">
          标签（逗号分隔）
          <input v-model="tagsInput" type="text" placeholder="CLT, 劳工" />
        </label>

        <label class="span-2">
          葡语原文片段
          <textarea v-model="form.text_pt" rows="5" />
        </label>

        <label class="span-2">
          中文摘要
          <textarea v-model="form.text_zh" rows="4" />
        </label>
      </div>

      <div class="form-actions">
        <button type="button" class="btn-secondary" @click="closeForm">取消</button>
        <button type="button" class="btn-primary" :disabled="saving" @click="saveEntry">
          {{ saving ? '保存中…' : '保存条目' }}
        </button>
      </div>
    </section>

    <section class="panel notice-panel">
      <h2>操作须知</h2>
      <ul>
        <li>本页维护的是<strong>法源检索语料</strong>，不是单次协查结论；个案补充请在复核页批注。</li>
        <li>新增核查<strong>条目</strong>（如 IBAMA 新检查点）须由实施人员更新规则库，并在此绑定对应 <code>checklist_codes</code>。</li>
        <li>保存条目后请点击<strong>重建法源索引</strong>；已定稿底稿不会自动变更，重大法规变化应通知业务重新协查。</li>
        <li>正式投产建议保留变更审批记录；当前版本会写入系统审计日志。</li>
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
