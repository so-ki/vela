<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  fetchLlmSettings,
  patchLlmSettings,
  testLlmConnection,
  type LlmSettings,
} from '@/api/client'

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const error = ref<string | null>(null)
const testResult = ref<string | null>(null)

const settings = ref<LlmSettings>({
  enabled: null,
  provider: 'qwen',
  base_url: '',
  api_key_masked: '',
  has_api_key: false,
  default_model: '',
  task_models: {
    extract: '',
    issue_id: '',
    gap: '',
    red_team: '',
    polish: '',
  },
  provider_defaults: {},
})

const apiKeyInput = ref('')
const enabledToggle = ref(true)

const providerOptions = [
  { id: 'qwen', label: '通义千问 (Qwen)' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'siliconflow', label: 'SiliconFlow' },
  { id: 'ollama', label: 'Ollama (本地)' },
  { id: 'openai_compatible', label: 'OpenAI 兼容' },
]

const defaultBaseUrl = computed(() => {
  const defs = settings.value.provider_defaults?.[settings.value.provider]
  return defs?.base_url || ''
})

const defaultModel = computed(() => {
  const defs = settings.value.provider_defaults?.[settings.value.provider]
  return defs?.default_model || ''
})

onMounted(async () => {
  try {
    settings.value = await fetchLlmSettings()
    enabledToggle.value = settings.value.enabled !== false
  } catch {
    error.value = '无法加载 AI 设置'
  } finally {
    loading.value = false
  }
})

async function saveSettings() {
  saving.value = true
  error.value = null
  testResult.value = null
  try {
    const payload: Record<string, unknown> = {
      enabled: enabledToggle.value,
      provider: settings.value.provider,
      base_url: settings.value.base_url || defaultBaseUrl.value,
      default_model: settings.value.default_model || defaultModel.value,
      task_models: settings.value.task_models,
    }
    if (apiKeyInput.value.trim()) {
      payload.api_key = apiKeyInput.value.trim()
    }
    settings.value = await patchLlmSettings(payload)
    apiKeyInput.value = ''
  } catch {
    error.value = '保存失败'
  } finally {
    saving.value = false
  }
}

async function runTest() {
  testing.value = true
  testResult.value = null
  error.value = null
  try {
    const res = await testLlmConnection({
      provider: settings.value.provider,
      base_url: settings.value.base_url || defaultBaseUrl.value,
      api_key: apiKeyInput.value,
      model: settings.value.default_model || defaultModel.value,
    })
    if (res.ok) {
      testResult.value = `连接成功 · ${res.model} · ${res.latency_ms}ms`
    } else {
      testResult.value = res.error || '连接失败'
    }
  } catch {
    testResult.value = '连接失败'
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <section class="panel llm-settings-panel">
    <h2>AI 模型与 API 设置</h2>
    <p class="muted">
      配置后将覆盖服务端 <code>.env</code> 默认项；API Key 仅存于本机用户偏好，不会提交到 git。
    </p>

    <div v-if="loading" class="muted">加载中…</div>
    <form v-else class="llm-settings-form" @submit.prevent="saveSettings">
      <label class="toggle-row">
        <input v-model="enabledToggle" type="checkbox" />
        <span>启用 LLM（抽取 / 议题 / 缺口 / Red Team / 简报润色）</span>
      </label>

      <label>
        <strong>默认 Provider</strong>
        <select v-model="settings.provider">
          <option v-for="p in providerOptions" :key="p.id" :value="p.id">{{ p.label }}</option>
        </select>
      </label>

      <label>
        <strong>Base URL</strong>
        <input
          v-model="settings.base_url"
          type="text"
          :placeholder="defaultBaseUrl || 'https://...'"
        />
      </label>

      <label>
        <strong>默认 Model</strong>
        <input v-model="settings.default_model" type="text" :placeholder="defaultModel || 'model name'" />
      </label>

      <label>
        <strong>API Key</strong>
        <input v-model="apiKeyInput" type="password" autocomplete="off" placeholder="sk-..." />
        <span v-if="settings.has_api_key" class="muted">已保存：{{ settings.api_key_masked }}</span>
      </label>

      <details class="task-models-details">
        <summary>按任务选模型（高级，留空则用默认 model）</summary>
        <div class="task-models-grid">
          <label v-for="(label, key) in {
            extract: '材料抽取',
            issue_id: '议题识别',
            gap: '缺口说明',
            red_team: 'Red Team',
            polish: '简报润色',
          }" :key="key">
            {{ label }}
            <input v-model="settings.task_models[key as keyof typeof settings.task_models]" type="text" />
          </label>
        </div>
      </details>

      <div class="llm-settings-actions">
        <button type="button" class="btn secondary" :disabled="testing" @click="runTest">
          {{ testing ? '测试中…' : '测试连接' }}
        </button>
        <button type="submit" class="btn primary" :disabled="saving">
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
      </div>

      <p v-if="testResult" class="test-result">{{ testResult }}</p>
      <p v-if="error" class="error-text">{{ error }}</p>
    </form>
  </section>
</template>

<style scoped>
.llm-settings-panel {
  margin-top: 1rem;
}
.llm-settings-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 520px;
}
.llm-settings-form label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.toggle-row {
  flex-direction: row !important;
  align-items: center;
  gap: 0.5rem !important;
}
.task-models-grid {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.llm-settings-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.test-result {
  color: var(--color-success, #0a7);
}
</style>
