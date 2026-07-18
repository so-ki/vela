<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  fetchLlmSettings,
  patchLlmSettings,
  clearLlmApiKey,
  testLlmConnection,
  type LlmSettings,
} from '@/api/client'

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const error = ref<string | null>(null)
const testResult = ref<string | null>(null)

const settings = ref<LlmSettings>({
  available: true,
  disabled_reason: null,
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
]

const taskModelFields: Array<{
  key: keyof LlmSettings['task_models']
  label: string
}> = [
  { key: 'extract', label: '材料抽取' },
  { key: 'issue_id', label: '议题识别' },
  { key: 'gap', label: '缺口说明' },
  { key: 'red_team', label: 'Red Team' },
  { key: 'polish', label: '简报润色' },
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
      base_url: defaultBaseUrl.value,
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
      base_url: defaultBaseUrl.value,
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

async function clearKey() {
  saving.value = true
  error.value = null
  testResult.value = null
  try {
    settings.value = await clearLlmApiKey()
    apiKeyInput.value = ''
    testResult.value = '短期 API Key 已从当前进程清除'
  } catch {
    error.value = '清除失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="panel llm-settings-panel">
    <h2>AI 模型与 API 设置</h2>
    <p class="muted">
      API Key 不写入数据库或 JSON，仅在当前服务进程内短期保存并绑定官方 HTTPS 端点；服务重启或到期后需重新输入。
    </p>

    <div v-if="loading" class="muted">加载中…</div>
    <div v-else-if="!settings.available" class="llm-disabled-notice">
      <strong>生产受控试点：第三方模型外发已关闭</strong>
      <p>{{ settings.disabled_reason || '系统不会接收 API Key，材料与提示词保持在本部署内。' }}</p>
    </div>
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
        <strong>已批准的官方 Base URL</strong>
        <input
          :value="defaultBaseUrl"
          type="text"
          readonly
        />
      </label>

      <label>
        <strong>默认 Model</strong>
        <input v-model="settings.default_model" type="text" :placeholder="defaultModel || 'model name'" />
      </label>

      <label>
        <strong>API Key</strong>
        <input v-model="apiKeyInput" type="password" autocomplete="off" placeholder="sk-..." />
        <span v-if="settings.has_api_key" class="muted">当前进程已配置：{{ settings.api_key_masked }}</span>
      </label>

      <details class="task-models-details">
        <summary>按任务选模型（高级，留空则用默认 model）</summary>
        <div class="task-models-grid">
          <label v-for="field in taskModelFields" :key="field.key">
            {{ field.label }}
            <input v-model="settings.task_models[field.key]" type="text" />
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
        <button
          v-if="settings.has_api_key"
          type="button"
          class="btn secondary"
          :disabled="saving"
          @click="clearKey"
        >
          清除 API Key
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
.llm-disabled-notice {
  max-width: 620px;
  padding: 0.9rem 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted, #f6f7f9);
}
.llm-disabled-notice p {
  margin: 0.4rem 0 0;
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
