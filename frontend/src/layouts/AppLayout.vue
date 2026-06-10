<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import DisclaimerModal from '@/components/DisclaimerModal.vue'

const auth = useAuthStore()
const route = useRoute()

const wideLayout = computed(() =>
  ['review', 'checklist', 'brief', 'project-hub', 'material-review', 'legal-corpus'].includes(String(route.name)),
)
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <img src="/vela.svg" alt="Vela" class="brand-icon" />
        <div>
          <strong>Vela 出海法务平台</strong>
          <span class="subtitle">拉美涉外投资合规协查助手</span>
        </div>
      </div>
      <nav class="nav">
        <RouterLink to="/">工作台</RouterLink>
        <RouterLink v-if="auth.isLegal" to="/legal/corpus">法源维护</RouterLink>
      </nav>
      <div class="user-area" v-if="auth.user">
        <span class="role-badge">{{ auth.roleLabel }}</span>
        <span>{{ auth.user.full_name }}</span>
        <span class="org" v-if="auth.user.organization">{{ auth.user.organization }}</span>
        <button class="btn-text" @click="auth.logout(); $router.push('/login')">退出</button>
      </div>
    </header>

    <main class="main-content" :class="{ 'main-content--wide': wideLayout }">
      <RouterView />
    </main>

    <DisclaimerModal v-if="auth.needsDisclaimer" />
  </div>
</template>
