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
          meta: { requiresDisclaimer: true },
        },
        {
          path: 'scenarios/:id/checklist',
          name: 'checklist',
          component: () => import('@/views/ChecklistView.vue'),
          meta: { requiresDisclaimer: true },
        },
        {
          path: 'scenarios/:id/brief',
          name: 'brief',
          component: () => import('@/views/BriefView.vue'),
          meta: { requiresDisclaimer: true },
        },
        {
          path: 'scenarios/:id/review',
          name: 'review',
          component: () => import('@/views/ReviewView.vue'),
          meta: { requiresDisclaimer: true },
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

  return true
})

export default router
