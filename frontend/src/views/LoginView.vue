<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { fetchSsoConfig } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { competitionOverviewPath, isCompetitionMode } from '@/config/appMode'
import type { SsoConfig } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const showDemoHint = import.meta.env.DEV
const competitionMode = isCompetitionMode()
const localError = ref<string | null>(null)
const ssoConfig = ref<SsoConfig | null>(null)

onMounted(async () => {
  ssoConfig.value = await fetchSsoConfig()
  const ssoError = route.query.sso_error
  if (typeof ssoError === 'string') {
    localError.value = `SSO 登录失败：${ssoError}`
  }
})

async function handleSubmit() {
  localError.value = null
  try {
    const user = await auth.login(email.value, password.value)
    const redirect = competitionMode
      ? competitionOverviewPath()
      : typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(user.disclaimer_accepted ? redirect : redirect)
  } catch {
    localError.value = auth.error
  }
}

function startSsoLogin() {
  const redirect =
    typeof route.query.redirect === 'string' ? encodeURIComponent(route.query.redirect) : ''
  const base = `${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/auth/sso/login`
  window.location.href = redirect ? `${base}?redirect=${redirect}` : base
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <img src="/vela.svg" alt="Vela" class="brand-icon lg" />
        <h1>{{ competitionMode ? 'Vela 比赛主演示' : 'Vela 出海法务平台' }}</h1>
        <template v-if="competitionMode">
          <p>Vela 是面向中国企业法务的拉美投资前合规协查过程保证平台。</p>
          <p class="competition-login-pack">当前完成端到端验证的首个 Capability Pack：<br /><strong>巴西 · 圣保罗州 · 新能源制造 · 绿地设厂</strong></p>
          <p>本次演示案例：<br /><strong>Aurora 储能系统集成工厂（虚构测试案例）</strong></p>
        </template>
        <p v-else>拉美涉外投资合规协查与法律风险简报助手</p>
      </div>

      <button
        v-if="ssoConfig?.enabled"
        type="button"
        class="btn-secondary full sso-btn"
        @click="startSsoLogin"
      >
        使用 {{ ssoConfig.provider_name }} 登录
      </button>

      <div v-if="ssoConfig?.enabled && ssoConfig.allow_password_login" class="auth-divider">
        <span>或使用邮箱密码</span>
      </div>

      <form
        v-if="!ssoConfig || ssoConfig.allow_password_login"
        @submit.prevent="handleSubmit"
        class="auth-form"
      >
        <label>
          <span>邮箱</span>
          <input v-model="email" type="email" required autocomplete="email" placeholder="name@company.com" />
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

      <p class="auth-footer" v-if="!competitionMode && (ssoConfig === null || ssoConfig.allow_open_registration)">
        还没有账户？
        <RouterLink to="/register">注册账户</RouterLink>
      </p>

      <p class="demo-hint" v-if="showDemoHint && ssoConfig?.allow_password_login !== false">
        演示账户：<br />
        法务 legal@demo.vela / Demo1234!<br />
        业务 biz@demo.vela / Demo1234!
      </p>
    </div>
  </div>
</template>
