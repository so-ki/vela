<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  completeInterview,
  fetchInterviewScript,
  fetchOnboardingStatus,
  startInterview,
  submitInterviewAnswer,
  uploadInterviewAttachment,
} from '@/api/client'

interface QuestionOption {
  value: string
  label: string
  hint?: string
}

interface UploadFieldConfig {
  purpose: string
  label: string
  hint?: string
  accept?: string
  parse_into?: string | null
  merge_mode?: 'append' | 'replace'
  required_when_answer?: string
}

interface InterviewQuestion {
  id: string
  prompt: string
  hint?: string
  type: string
  placeholder?: string
  required?: boolean
  min_selections?: number
  default?: string
  options?: Array<string | QuestionOption>
  other_field?: {
    id: string
    trigger_value: string
    placeholder?: string
    label?: string
  }
  upload_field?: UploadFieldConfig
}

const router = useRouter()
const loading = ref(true)
const sessionId = ref('')
const script = ref<{ title?: string; subtitle?: string; questions?: InterviewQuestion[] }>({})
const step = ref(0)
const answers = ref<Record<string, unknown>>({})
const stepBusy = ref(false)
const completing = ref(false)
const error = ref<string | null>(null)
const uploadBusy = ref<Record<string, boolean>>({})
const uploadFiles = ref<Record<string, string>>({})
const uploadPreview = ref<Record<string, string>>({})
const uploadErrors = ref<Record<string, string>>({})

const questions = computed(() => script.value.questions || [])
const current = computed(() => questions.value[step.value])
const progress = computed(() =>
  questions.value.length ? Math.round(((step.value + 1) / questions.value.length) * 100) : 0,
)
const primaryLabel = computed(() => {
  if (completing.value) return '正在生成 Playbook…'
  if (stepBusy.value) return '保存本题…'
  return step.value < questions.value.length - 1 ? '下一题' : '完成并生成 Playbook'
})

function storageKey() {
  return sessionId.value ? `vela_interview_${sessionId.value}` : ''
}

function persistLocal() {
  const key = storageKey()
  if (!key) return
  localStorage.setItem(
    key,
    JSON.stringify({ step: step.value, answers: answers.value, uploadFiles: uploadFiles.value }),
  )
}

function restoreLocal() {
  const key = storageKey()
  if (!key) return
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return
    const data = JSON.parse(raw) as {
      step?: number
      answers?: Record<string, unknown>
      uploadFiles?: Record<string, string>
    }
    if (data.answers) answers.value = { ...answers.value, ...data.answers }
    if (typeof data.step === 'number') step.value = Math.min(data.step, questions.value.length - 1)
    if (data.uploadFiles) uploadFiles.value = { ...uploadFiles.value, ...data.uploadFiles }
  } catch {
    /* ignore */
  }
}

watch([answers, step], persistLocal, { deep: true })

function normalizeOptions(options: InterviewQuestion['options']): QuestionOption[] {
  return (options || []).map((opt) => {
    if (typeof opt === 'string') return { value: opt, label: opt }
    return { value: opt.value, label: opt.label, hint: opt.hint }
  })
}

function optionSelected(value: string) {
  if (!current.value) return false
  const id = current.value.id
  const ans = answers.value[id]
  if (current.value.type === 'multi_choice') {
    return Array.isArray(ans) && ans.includes(value)
  }
  return ans === value
}

function setAnswer(val: unknown) {
  if (!current.value) return
  answers.value[current.value.id] = val
  error.value = null
}

function selectSingle(value: string) {
  setAnswer(value)
}

function toggleMulti(value: string) {
  if (!current.value) return
  const id = current.value.id
  const cur = Array.isArray(answers.value[id]) ? [...(answers.value[id] as string[])] : []
  const idx = cur.indexOf(value)
  if (idx >= 0) {
    cur.splice(idx, 1)
    const other = current.value.other_field
    if (other && value === other.trigger_value) {
      answers.value[other.id] = ''
    }
  } else {
    cur.push(value)
  }
  setAnswer(cur)
}

function isOtherSelected(q: InterviewQuestion | undefined) {
  if (!q?.other_field) return false
  const selected = answers.value[q.id]
  return Array.isArray(selected) && selected.includes(q.other_field.trigger_value)
}

function setOtherAnswer(fieldId: string, val: string) {
  answers.value[fieldId] = val
}

function initDefaultAnswer(q: InterviewQuestion) {
  if (answers.value[q.id] !== undefined) return
  if (q.type === 'multi_choice') {
    answers.value[q.id] = []
    return
  }
  if (q.default) answers.value[q.id] = q.default
}

function uploadRequired(q: InterviewQuestion | undefined) {
  const uf = q?.upload_field
  if (!uf?.required_when_answer) return false
  return answers.value[q!.id] === uf.required_when_answer
}

function showUploadField(q: InterviewQuestion | undefined) {
  const uf = q?.upload_field
  if (!uf) return false
  if (uf.required_when_answer) {
    return answers.value[q!.id] === uf.required_when_answer
  }
  return true
}

function validateCurrent(): string | null {
  if (!current.value) return '题目加载失败'
  const qid = current.value.id
  const val = answers.value[qid]
  if (current.value.required) {
    if (current.value.type === 'multi_choice') {
      const min = current.value.min_selections ?? 1
      const count = Array.isArray(val) ? val.length : 0
      if (count < min) return `请至少选择 ${min} 项`
      const other = current.value.other_field
      if (other && Array.isArray(val) && val.includes(other.trigger_value)) {
        const otherText = String(answers.value[other.id] ?? '').trim()
        if (!otherText) return '选择「其他」后请填写具体行业'
      }
    } else if (val === undefined || val === '' || (Array.isArray(val) && val.length === 0)) {
      return '请完成本题后再继续'
    }
  }
  const uf = current.value.upload_field
  if (uf?.required_when_answer && answers.value[qid] === uf.required_when_answer) {
    if (!uploadFiles.value[uf.purpose]) return `请上传：${uf.label}`
  }
  return null
}

async function persistCurrentStepAnswers(q: InterviewQuestion) {
  await submitInterviewAnswer(sessionId.value, q.id, answers.value[q.id] ?? '')
  if (q.other_field && q.type === 'multi_choice') {
    await submitInterviewAnswer(sessionId.value, q.other_field.id, answers.value[q.other_field.id] ?? '')
  }
}

async function handleUpload(file: File, field: UploadFieldConfig) {
  if (!sessionId.value) return
  uploadBusy.value[field.purpose] = true
  uploadErrors.value[field.purpose] = ''
  try {
    const result = await uploadInterviewAttachment(sessionId.value, file, {
      purpose: field.purpose,
      parse: Boolean(field.parse_into),
      parseInto: field.parse_into,
      mergeMode: field.merge_mode || 'append',
    })
    if (result.parse_error) {
      uploadErrors.value[field.purpose] = result.parse_error
    }
    uploadFiles.value[field.purpose] = result.meta.original_name
    if (result.preview) uploadPreview.value[field.purpose] = result.preview
    if (field.parse_into && result.merged_value != null) {
      answers.value[field.parse_into] = result.merged_value
    }
    persistLocal()
  } catch (e: unknown) {
    uploadErrors.value[field.purpose] =
      e instanceof Error ? e.message : '文件上传或解析失败，请换格式重试'
  } finally {
    uploadBusy.value[field.purpose] = false
  }
}

function onUploadChange(ev: Event, field: UploadFieldConfig) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void handleUpload(file, field)
  input.value = ''
}

onMounted(async () => {
  try {
    const status = await fetchOnboardingStatus()
    if (status.completed) {
      router.replace('/')
      return
    }
    script.value = await fetchInterviewScript()
    const started = await startInterview()
    sessionId.value = started.session_id
    for (const q of questions.value) initDefaultAnswer(q)
    restoreLocal()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
})

function prevStep() {
  if (stepBusy.value || completing.value) return
  if (step.value > 0) {
    step.value -= 1
    error.value = null
  }
}

async function nextStep() {
  if (!current.value || !sessionId.value || stepBusy.value || completing.value) return
  const validation = validateCurrent()
  if (validation) {
    error.value = validation
    return
  }
  error.value = null
  const q = current.value
  const isLast = step.value >= questions.value.length - 1
  stepBusy.value = true
  try {
    await persistCurrentStepAnswers(q)
    if (!isLast) {
      step.value += 1
      const nextQ = questions.value[step.value]
      if (nextQ) initDefaultAnswer(nextQ)
      persistLocal()
      return
    }
    completing.value = true
    await completeInterview(sessionId.value)
    localStorage.removeItem(storageKey())
    router.push('/')
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '保存失败'
    error.value = msg.includes('timeout') ? '网络超时，请确认后端已启动后重试' : msg
  } finally {
    stepBusy.value = false
    completing.value = false
  }
}
</script>

<template>
  <div class="cold-start-page">
    <header class="cold-start-hero">
      <div class="hero-badge">首次配置</div>
      <h1>{{ script.title || '首次使用 · 冷启动访谈' }}</h1>
      <p class="hero-sub">{{ script.subtitle }}</p>
    </header>

    <div v-if="loading" class="state-card muted">加载访谈脚本…</div>

    <div v-else-if="current" class="interview-shell">
      <div class="progress-row">
        <div class="progress-meta">
          <span>第 {{ step + 1 }} / {{ questions.length }} 题</span>
          <span>{{ progress }}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progress + '%' }" />
        </div>
        <div class="step-dots" aria-hidden="true">
          <span
            v-for="(q, i) in questions"
            :key="q.id"
            class="dot"
            :class="{ active: i === step, done: i < step }"
          />
        </div>
      </div>

      <section class="question-card">
        <h2 class="question-title">{{ current.prompt }}</h2>
        <p v-if="current.hint" class="question-hint">{{ current.hint }}</p>

        <div v-if="current.type === 'choice'" class="option-grid" @click.stop>
          <button
            v-for="opt in normalizeOptions(current.options)"
            :key="opt.value"
            type="button"
            class="option-card"
            :class="{ selected: optionSelected(opt.value) }"
            @click.stop="selectSingle(opt.value)"
          >
            <span class="option-radio" aria-hidden="true" />
            <span class="option-body">
              <strong>{{ opt.label }}</strong>
              <span v-if="opt.hint" class="option-hint">{{ opt.hint }}</span>
            </span>
          </button>
        </div>

        <div v-else-if="current.type === 'multi_choice'" class="option-grid multi" @click.stop>
          <button
            v-for="opt in normalizeOptions(current.options)"
            :key="opt.value"
            type="button"
            class="option-card"
            :class="{ selected: optionSelected(opt.value) }"
            @click.stop="toggleMulti(opt.value)"
          >
            <span class="option-check" aria-hidden="true">✓</span>
            <span class="option-body">
              <strong>{{ opt.label }}</strong>
              <span v-if="opt.hint" class="option-hint">{{ opt.hint }}</span>
            </span>
          </button>
          <div v-if="current.other_field && isOtherSelected(current)" class="other-field-block">
            <label :for="current.other_field.id" class="other-field-label">
              {{ current.other_field.label || '请说明其他行业' }}
            </label>
            <input
              :id="current.other_field.id"
              class="field-input"
              type="text"
              :placeholder="current.other_field.placeholder || '请填写具体行业…'"
              :value="(answers[current.other_field.id] as string) || ''"
              @input="setOtherAnswer(current.other_field!.id, ($event.target as HTMLInputElement).value)"
            />
          </div>
          <p class="multi-summary muted">
            已选
            <strong>{{ Array.isArray(answers[current.id]) ? (answers[current.id] as string[]).length : 0 }}</strong>
            项 · 选择不会自动保存，点「下一题」才提交
          </p>
        </div>

        <textarea
          v-else-if="current.type === 'textarea'"
          class="field-textarea"
          rows="5"
          :placeholder="current.placeholder || '请在此输入…'"
          :value="(answers[current.id] as string) || ''"
          @input="setAnswer(($event.target as HTMLTextAreaElement).value)"
        />

        <input
          v-else
          class="field-input"
          type="text"
          :placeholder="current.placeholder || '请在此输入…'"
          :value="(answers[current.id] as string) || ''"
          @input="setAnswer(($event.target as HTMLInputElement).value)"
        />

        <div
          v-if="showUploadField(current)"
          class="upload-block"
          :class="{ required: uploadRequired(current) }"
        >
          <label class="upload-label">
            <span class="upload-title">
              {{ current.upload_field.label }}
              <span v-if="uploadRequired(current)" class="req-tag">必传</span>
            </span>
            <span class="upload-hint">{{ current.upload_field.hint }}</span>
            <input
              type="file"
              :accept="current.upload_field.accept || '.docx,.pdf,.txt,.md'"
              :disabled="uploadBusy[current.upload_field.purpose]"
              @change="onUploadChange($event, current.upload_field!)"
            />
            <span v-if="uploadBusy[current.upload_field.purpose]" class="upload-status">正在上传并解析…</span>
            <span v-else-if="uploadFiles[current.upload_field.purpose]" class="upload-file">
              已上传：{{ uploadFiles[current.upload_field.purpose] }}
            </span>
            <p v-if="uploadPreview[current.upload_field.purpose]" class="upload-preview muted">
              解析预览：{{ uploadPreview[current.upload_field.purpose] }}
            </p>
            <p v-if="uploadErrors[current.upload_field.purpose]" class="upload-error">
              {{ uploadErrors[current.upload_field.purpose] }}
            </p>
          </label>
        </div>

        <p v-if="error" class="error-banner">{{ error }}</p>

        <div class="action-row">
          <button type="button" class="btn ghost" :disabled="step === 0 || stepBusy || completing" @click="prevStep">
            上一题
          </button>
          <button type="button" class="btn primary" :disabled="stepBusy || completing" @click="nextStep">
            {{ primaryLabel }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.cold-start-page {
  max-width: 820px;
  margin: 0 auto;
  padding: 1.5rem 1.25rem 3rem;
}

.cold-start-hero {
  text-align: center;
  margin-bottom: 1.75rem;
}

.hero-badge {
  display: inline-block;
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  background: rgba(26, 58, 92, 0.08);
  color: var(--primary);
  font-size: 0.8rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
}

.cold-start-hero h1 {
  font-size: 1.65rem;
  color: var(--primary);
  margin-bottom: 0.5rem;
}

.hero-sub {
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.6;
  max-width: 36rem;
  margin: 0 auto;
}

.state-card {
  background: var(--surface);
  border-radius: var(--radius);
  padding: 2rem;
  text-align: center;
  box-shadow: var(--shadow);
}

.interview-shell {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.progress-row {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  box-shadow: var(--shadow);
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  color: var(--muted);
  margin-bottom: 0.5rem;
}

.progress-bar {
  height: 8px;
  background: #e8edf2;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), var(--primary-light));
  border-radius: 4px;
  transition: width 0.25s ease;
}

.step-dots {
  display: flex;
  justify-content: center;
  gap: 0.4rem;
  margin-top: 0.85rem;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d1d5db;
  transition: all 0.2s;
}

.dot.done {
  background: var(--primary-light);
}

.dot.active {
  width: 22px;
  border-radius: 4px;
  background: var(--accent);
}

.question-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: calc(var(--radius) + 2px);
  padding: 1.75rem;
  box-shadow: var(--shadow);
  min-height: 420px;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.question-title {
  font-size: 1.35rem;
  line-height: 1.45;
  color: var(--text);
}

.question-hint {
  color: var(--muted);
  font-size: 0.92rem;
  line-height: 1.55;
  margin-bottom: 0.75rem;
}

.option-grid {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.option-grid.multi {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.75rem;
}

.option-card {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  width: 100%;
  text-align: left;
  padding: 1rem 1.1rem;
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  background: #fafbfc;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.option-card:hover {
  border-color: var(--primary-light);
  background: #fff;
}

.option-card.selected {
  border-color: var(--primary);
  background: rgba(26, 58, 92, 0.04);
  box-shadow: 0 0 0 1px rgba(26, 58, 92, 0.12);
}

.option-radio,
.option-check {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 2px;
  border: 2px solid #cbd5e1;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  color: transparent;
}

.option-check {
  border-radius: 5px;
}

.option-card.selected .option-radio {
  border-color: var(--primary);
  box-shadow: inset 0 0 0 4px var(--primary);
}

.option-card.selected .option-check {
  border-color: var(--primary);
  background: var(--primary);
  color: #fff;
}

.option-body {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.option-body strong {
  font-size: 1rem;
  font-weight: 600;
}

.option-hint {
  font-size: 0.85rem;
  color: var(--muted);
  line-height: 1.45;
}

.multi-summary {
  grid-column: 1 / -1;
  font-size: 0.88rem;
}

.other-field-block {
  grid-column: 1 / -1;
  padding: 1rem 1.1rem;
  border: 1.5px solid rgba(230, 126, 34, 0.35);
  border-radius: var(--radius);
  background: rgba(230, 126, 34, 0.06);
}

.other-field-label {
  display: block;
  font-size: 0.92rem;
  font-weight: 600;
  margin-bottom: 0.55rem;
}

.field-input,
.field-textarea {
  width: 100%;
  padding: 0.9rem 1rem;
  font-size: 1rem;
  line-height: 1.5;
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  background: #fafbfc;
  color: var(--text);
}

.field-input {
  min-height: 52px;
}

.field-textarea {
  min-height: 140px;
  resize: vertical;
}

.field-input:focus,
.field-textarea:focus {
  outline: none;
  border-color: var(--primary-light);
  box-shadow: 0 0 0 3px rgba(45, 90, 135, 0.15);
  background: #fff;
}

.upload-block {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px dashed var(--border);
}

.upload-block.required .upload-label {
  border-color: rgba(230, 126, 34, 0.45);
}

.upload-label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 1rem 1.1rem;
  border: 1.5px dashed #cbd5e1;
  border-radius: var(--radius);
  background: #f8fafc;
}

.upload-title {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.req-tag {
  font-size: 0.72rem;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  background: rgba(230, 126, 34, 0.15);
  color: #c2410c;
}

.upload-hint {
  font-size: 0.85rem;
  color: var(--muted);
}

.upload-label input[type='file'] {
  margin-top: 0.35rem;
  font-size: 0.88rem;
}

.upload-file {
  font-size: 0.88rem;
  color: var(--primary-light);
}

.upload-status {
  font-size: 0.88rem;
  color: var(--accent);
}

.upload-preview {
  font-size: 0.82rem;
  line-height: 1.5;
  max-height: 4.5em;
  overflow: hidden;
}

.upload-error {
  font-size: 0.85rem;
  color: var(--err);
}

.error-banner {
  margin-top: 0.75rem;
  padding: 0.65rem 0.85rem;
  border-radius: 8px;
  background: #fef2f2;
  color: var(--err);
  font-size: 0.9rem;
}

.action-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-top: auto;
  padding-top: 1.25rem;
}

.btn {
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.35rem;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn.primary {
  background: var(--primary);
  color: #fff;
  min-width: 168px;
}

.btn.ghost {
  background: transparent;
  color: var(--muted);
  border: 1px solid var(--border);
}

@media (max-width: 640px) {
  .option-grid.multi {
    grid-template-columns: 1fr;
  }

  .question-card {
    padding: 1.25rem;
    min-height: auto;
  }

  .action-row {
    flex-direction: column-reverse;
  }

  .btn {
    width: 100%;
  }
}
</style>
