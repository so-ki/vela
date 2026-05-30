<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDisclaimer } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { Disclaimer } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const disclaimer = ref<Disclaimer | null>(null)
const checked = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  disclaimer.value = await fetchDisclaimer()
})

async function handleAccept() {
  if (!checked.value) {
    error.value = '请先勾选同意条款'
    return
  }
  submitting.value = true
  error.value = null
  try {
    await auth.confirmDisclaimer()
    router.push('/')
  } catch (e: unknown) {
    error.value = '提交失败，请重试'
  } finally {
    submitting.value = false
  }
}

function handleDecline() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="modal-overlay">
    <div class="modal-card disclaimer-modal">
      <h2>{{ disclaimer?.title ?? '免责声明' }}</h2>
      <p class="version" v-if="disclaimer">版本 {{ disclaimer.version }}</p>

      <div class="disclaimer-body" v-if="disclaimer">
        <section v-for="section in disclaimer.sections" :key="section.title">
          <h3>{{ section.title }}</h3>
          <p>{{ section.content }}</p>
        </section>
      </div>

      <label class="checkbox-row">
        <input type="checkbox" v-model="checked" />
        <span>我已阅读并同意上述免责声明与数据使用条款</span>
      </label>

      <p class="error" v-if="error">{{ error }}</p>

      <div class="modal-actions">
        <button class="btn-secondary" @click="handleDecline">不同意并退出</button>
        <button class="btn-primary" :disabled="submitting" @click="handleAccept">
          {{ submitting ? '提交中…' : '同意并继续' }}
        </button>
      </div>
    </div>
  </div>
</template>
