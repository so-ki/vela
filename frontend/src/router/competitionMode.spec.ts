import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AppLayout from '@/layouts/AppLayout.vue'
import LoginView from '@/views/LoginView.vue'
import { makeBusinessUser, makeLegalUser } from '@/test/factories'
import { useAuthStore } from '@/stores/auth'
import { createAppRouter } from './index'

const api = vi.hoisted(() => ({
  acceptDisclaimer: vi.fn(),
  fetchMe: vi.fn(),
  fetchSsoConfig: vi.fn(),
  login: vi.fn(),
}))

vi.mock('@/api/client', () => api)

function authenticatedRouter(role: 'business' | 'legal' = 'business') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.setSession(
    'competition-token',
    role === 'business' ? makeBusinessUser() : makeLegalUser(),
  )
  return { pinia, auth, router: createAppRouter(createMemoryHistory()) }
}

describe('competition clean entry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    localStorage.clear()
    api.fetchSsoConfig.mockResolvedValue({
      enabled: false,
      provider_name: 'SSO',
      allow_password_login: true,
      allow_open_registration: false,
    })
    vi.stubEnv('VITE_APP_MODE', 'competition')
    vi.stubEnv('VITE_COMPETITION_SCENARIO_ID', '23')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  async function loginAs(user: ReturnType<typeof makeBusinessUser>) {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter(createMemoryHistory())
    await router.push('/login')
    await router.isReady()
    api.login.mockResolvedValue({
      access_token: 'competition-token',
      token_type: 'bearer',
      user,
    })

    const wrapper = mount(LoginView, { global: { plugins: [pinia, router] } })
    await flushPromises()
    await wrapper.get('input[type="email"]').setValue(user.email)
    await wrapper.get('input[type="password"]').setValue('Demo1234!')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    await vi.waitFor(() => {
      expect(router.currentRoute.value.fullPath).toBe(
        user.role === 'business' ? '/competition/23/business' : '/competition/23/overview',
      )
    })
    return router.currentRoute.value.fullPath
  }

  it('redirects a successful legal login directly to Aurora overview', async () => {
    expect(await loginAs(makeLegalUser())).toBe('/competition/23/overview')
  })

  it('redirects a successful business login directly to the business center', async () => {
    expect(await loginAs(makeBusinessUser())).toBe('/competition/23/business')
  })

  it('redirects competition root to the legal workspace for legal users', async () => {
    const { router } = authenticatedRouter('legal')
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/competition/23/overview')
  })

  it('redirects competition root to the business center for business users', async () => {
    const { router } = authenticatedRouter('business')
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/competition/23/business')
  })

  it.each(['overview', 'research', 'claims', 'coverage', 'delivery', 'audit'])(
    'redirects business users away from the legal %s page',
    async (section) => {
      const { router } = authenticatedRouter('business')
      await router.push(`/competition/23/${section}`)
      await router.isReady()
      expect(router.currentRoute.value.fullPath).toBe('/competition/23/business')
    },
  )

  it('redirects legal users away from the business center', async () => {
    const { router } = authenticatedRouter('legal')
    await router.push('/competition/23/business')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/competition/23/overview')
  })

  it('shows only the competition link and user controls in the top navigation', async () => {
    const { pinia, router } = authenticatedRouter()
    await router.push('/competition/23/business')
    await router.isReady()
    const wrapper = mount(AppLayout, {
      global: {
        plugins: [pinia, router],
        stubs: { RouterView: true, DisclaimerModal: true },
      },
    })

    const header = wrapper.get('.topbar').text()
    expect(header).toContain('Vela')
    expect(header).toContain('比赛主演示')
    expect(header).toContain('业务协同')
    expect(header).toContain('演示业务')
    expect(header).toContain('退出')
    expect(header).not.toContain('工作台')
    expect(header).not.toContain('机制附录')
    expect(header).not.toContain('RC0')
    expect(header).not.toContain('法源维护')
  })

  it('keeps the development root Dashboard and normal navigation unchanged', async () => {
    vi.stubEnv('VITE_APP_MODE', 'development')
    const { pinia, router } = authenticatedRouter()
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('dashboard')

    const wrapper = mount(AppLayout, {
      global: {
        plugins: [pinia, router],
        stubs: { RouterView: true, DisclaimerModal: true },
      },
    })
    expect(wrapper.get('.topbar').text()).toContain('工作台')
    expect(wrapper.get('.topbar').text()).toContain('机制附录')
  })
})
