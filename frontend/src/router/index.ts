import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { guest: true },
    },
    {
      path: '/login/sso/callback',
      name: 'sso-callback',
      component: () => import('@/views/SsoCallbackView.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { requiresDisclaimer: true },
        },
        {
          path: 'scenarios/new',
          name: 'scenario-create',
          component: () => import('@/views/ScenarioCreateView.vue'),
          meta: { requiresDisclaimer: true, businessOnly: true },
        },
        {
          path: 'scenarios/:id/edit',
          name: 'scenario-edit',
          component: () => import('@/views/ScenarioCreateView.vue'),
          meta: { requiresDisclaimer: true, businessRevision: true },
        },
        {
          path: 'scenarios/:id/progress',
          name: 'scenario-progress',
          component: () => import('@/views/BusinessProgressView.vue'),
          meta: { requiresDisclaimer: true },
        },
        {
          path: 'scenarios/:id/checklist',
          name: 'checklist',
          component: () => import('@/views/ChecklistView.vue'),
          meta: { requiresDisclaimer: true, legalOnly: true },
        },
        {
          path: 'scenarios/:id/brief',
          name: 'brief',
          component: () => import('@/views/BriefView.vue'),
          meta: { requiresDisclaimer: true, legalOnly: true },
        },
        {
          path: 'scenarios/:id/review',
          name: 'review',
          component: () => import('@/views/ReviewView.vue'),
          meta: { requiresDisclaimer: true, legalOnly: true },
        },
        {
          path: 'legal/corpus',
          name: 'legal-corpus',
          component: () => import('@/views/LegalCorpusView.vue'),
          meta: { requiresDisclaimer: true, legalOnly: true },
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (auth.token && !auth.user) {
    await auth.loadUser()
  }

  if (to.meta.guest && auth.isAuthenticated && auth.user?.disclaimer_accepted) {
    return { name: 'dashboard' }
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresDisclaimer && auth.needsDisclaimer) {
    return true
  }

  if (auth.isBusiness && to.meta.legalOnly) {
    const id = to.params.id
    if (id) {
      return { name: 'scenario-progress', params: { id } }
    }
    return { name: 'dashboard' }
  }

  if (auth.isLegal && to.meta.businessRevision) {
    return { name: 'dashboard' }
  }

  if (auth.isLegal && to.meta.businessOnly) {
    return { name: 'dashboard' }
  }

  return true
})

export default router
