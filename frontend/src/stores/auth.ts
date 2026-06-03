import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { acceptDisclaimer, fetchMe, login as apiLogin } from '@/api/client'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(readStoredToken())
  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)
  const needsDisclaimer = computed(() => isAuthenticated.value && user.value && !user.value.disclaimer_accepted)
  const isLegal = computed(() => user.value?.role === 'legal' || user.value?.role === 'admin')
  const isBusiness = computed(() => user.value?.role === 'business')
  const roleLabel = computed(() => {
    const labels: Record<string, string> = {
      business: '业务协同',
      legal: '法务复核',
      admin: '系统管理员',
    }
    return user.value ? labels[user.value.role] || user.value.role : ''
  })

  function setSession(accessToken: string, userData: User) {
    token.value = accessToken
    user.value = userData
    try {
      localStorage.setItem('vela_token', accessToken)
    } catch {
      /* Safari 隐私模式等场景可能禁用 storage */
    }
  }

  function clearSession() {
    token.value = null
    user.value = null
    try {
      localStorage.removeItem('vela_token')
    } catch {
      /* ignore */
    }
  }

  async function login(email: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const data = await apiLogin(email, password)
      setSession(data.access_token, data.user)
      return data.user
    } catch (e: unknown) {
      error.value = extractError(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loadUser() {
    if (!token.value) return null
    loading.value = true
    error.value = null
    try {
      user.value = await fetchMe()
      return user.value
    } catch {
      clearSession()
      return null
    } finally {
      loading.value = false
    }
  }

  async function confirmDisclaimer() {
    const updated = await acceptDisclaimer()
    user.value = updated
    return updated
  }

  function logout() {
    clearSession()
  }

  return {
    token,
    user,
    loading,
    error,
    isAuthenticated,
    needsDisclaimer,
    isLegal,
    isBusiness,
    roleLabel,
    login,
    loadUser,
    confirmDisclaimer,
    logout,
    setSession,
  }
})

function readStoredToken(): string | null {
  try {
    return localStorage.getItem('vela_token')
  } catch {
    return null
  }
}

function extractError(e: unknown): string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const resp = (e as { response?: { status?: number; data?: { detail?: string | { msg: string }[] } } }).response
    if (resp?.status === 404) {
      return '后端 API 未找到（404）。请重启后端：在终端按 Ctrl+C 停止后重新运行 ./scripts/start.sh'
    }
    const detail = resp?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  }
  return '操作失败，请稍后重试'
}
