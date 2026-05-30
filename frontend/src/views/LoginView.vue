<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const email = ref('legal@demo.vela')
const password = ref('Demo1234!')
const localError = ref<string | null>(null)

async function handleSubmit() {
  localError.value = null
  try {
    const user = await auth.login(email.value, password.value)
    if (user.disclaimer_accepted) {
      router.push('/')
    } else {
      router.push('/')
    }
  } catch {
    localError.value = auth.error
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <img src="/vela.svg" alt="Vela" class="brand-icon lg" />
        <h1>Vela 出海法务平台</h1>
        <p>拉美涉外投资合规协查与法律风险简报助手</p>
      </div>

      <form @submit.prevent="handleSubmit" class="auth-form">
        <label>
          <span>邮箱</span>
          <input v-model="email" type="email" required autocomplete="email" placeholder="legal@demo.vela" />
        </label>
        <label>
          <span>密码</span>
          <input v-model="password" type="password" required autocomplete="current-password" />
        </label>

        <p class="error" v-if="localError">{{ localError }}</p>

        <button type="submit" class="btn-primary full" :disabled="auth.loading">
          {{ auth.loading ? '登录中…' : '登录' }}
        </button>
      </form>

      <p class="auth-footer">
        还没有账户？
        <RouterLink to="/register">注册企业法务账户</RouterLink>
      </p>

      <p class="demo-hint">演示账户：legal@demo.vela / Demo1234!</p>
    </div>
  </div>
</template>
