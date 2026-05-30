<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { fetchDisclaimer, register } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { Disclaimer } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const disclaimer = ref<Disclaimer | null>(null)
const form = ref({
  email: '',
  password: '',
  full_name: '',
  organization: '',
  accept_disclaimer: false,
})
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  disclaimer.value = await fetchDisclaimer()
})

async function handleSubmit() {
  if (!form.value.accept_disclaimer) {
    error.value = '注册须勾选同意免责声明与数据使用条款'
    return
  }
  loading.value = true
  error.value = null
  try {
    await register({
      email: form.value.email,
      password: form.value.password,
      full_name: form.value.full_name,
      organization: form.value.organization || undefined,
      accept_disclaimer: true,
    })
    await auth.login(form.value.email, form.value.password)
    router.push('/')
  } catch (e: unknown) {
    error.value = auth.error || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card wide">
      <div class="auth-header">
        <h1>注册企业法务账户</h1>
        <p>注册即表示您已阅读并同意平台免责声明</p>
      </div>

      <form @submit.prevent="handleSubmit" class="auth-form">
        <div class="form-row">
          <label>
            <span>姓名</span>
            <input v-model="form.full_name" required placeholder="张法务" />
          </label>
          <label>
            <span>所属企业</span>
            <input v-model="form.organization" placeholder="可选" />
          </label>
        </div>
        <label>
          <span>工作邮箱</span>
          <input v-model="form.email" type="email" required />
        </label>
        <label>
          <span>密码（至少 8 位）</span>
          <input v-model="form.password" type="password" minlength="8" required />
        </label>

        <div class="disclaimer-preview" v-if="disclaimer">
          <h3>{{ disclaimer.title }}</h3>
          <div class="preview-scroll">
            <section v-for="s in disclaimer.sections" :key="s.title">
              <strong>{{ s.title }}</strong>
              <p>{{ s.content }}</p>
            </section>
          </div>
        </div>

        <label class="checkbox-row">
          <input type="checkbox" v-model="form.accept_disclaimer" />
          <span>我已阅读并同意免责声明与数据使用条款</span>
        </label>

        <p class="error" v-if="error">{{ error }}</p>

        <button type="submit" class="btn-primary full" :disabled="loading">
          {{ loading ? '注册中…' : '注册并登录' }}
        </button>
      </form>

      <p class="auth-footer">
        已有账户？<RouterLink to="/login">返回登录</RouterLink>
      </p>
    </div>
  </div>
</template>
