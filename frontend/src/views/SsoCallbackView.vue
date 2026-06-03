<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const message = ref('正在完成 SSO 登录…')

onMounted(async () => {
  const token = route.query.access_token
  if (typeof token !== 'string' || !token) {
    message.value = 'SSO 回调缺少令牌，请返回登录页重试。'
    return
  }

  const user: User = {
    id: 0,
    email: String(route.query.email || ''),
    full_name: String(route.query.full_name || ''),
    organization: null,
    role: String(route.query.role || 'legal'),
    is_active: true,
    disclaimer_accepted: route.query.disclaimer_accepted === 'true',
    disclaimer_accepted_at: null,
    created_at: new Date().toISOString(),
  }

  auth.setSession(token, user)
  await auth.loadUser()

  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  router.replace(redirect)
})
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <p class="muted">{{ message }}</p>
    </div>
  </div>
</template>
