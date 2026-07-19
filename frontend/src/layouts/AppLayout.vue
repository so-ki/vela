<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import DisclaimerModal from '@/components/DisclaimerModal.vue'
import { competitionEntryPath, isCompetitionMode } from '@/config/appMode'

const auth = useAuthStore()
const route = useRoute()
const competitionMode = isCompetitionMode()
const competitionHome = computed(() =>
  competitionMode ? competitionEntryPath(auth.user?.role) : '/',
)

const wideLayout = computed(() =>
  ['review', 'checklist', 'mechanism', 'delivery-assurance', 'brief', 'project-hub', 'material-review', 'legal-corpus', 'competition-workspace', 'competition-business', 'rc0-workspace'].includes(String(route.name)),
)
</script>

<template>
  <div class="app-shell">
    <header class="topbar" :class="{ 'topbar--rc0': route.name === 'rc0-workspace' }">
      <div class="brand">
        <img src="/vela.svg" alt="Vela" class="brand-icon" />
        <div>
          <strong>{{ competitionMode ? 'Vela' : 'Vela 出海法务平台' }}</strong>
          <span class="subtitle">{{ competitionMode ? '拉美投资前合规协查过程保证平台' : '拉美涉外投资合规协查助手' }}</span>
        </div>
      </div>
      <nav v-if="competitionMode" class="nav" aria-label="比赛导航">
        <RouterLink :to="competitionHome">比赛主演示</RouterLink>
      </nav>
      <nav v-else class="nav">
        <RouterLink to="/">工作台</RouterLink>
        <RouterLink v-if="route.params.id" :to="`/competition/${route.params.id}/overview`">比赛主演示</RouterLink>
        <RouterLink to="/rc0/overview">机制附录</RouterLink>
        <RouterLink v-if="auth.isLegal" to="/legal/corpus">法源维护</RouterLink>
      </nav>
      <div class="user-area" v-if="auth.user">
        <span class="role-badge">{{ auth.roleLabel }}</span>
        <span>{{ auth.user.full_name }}</span>
        <span class="org" v-if="!competitionMode && auth.user.organization">{{ auth.user.organization }}</span>
        <button class="btn-text" @click="auth.logout(); $router.push('/login')">退出</button>
      </div>
    </header>

    <main class="main-content" :class="{ 'main-content--wide': wideLayout, 'main-content--rc0': route.name === 'rc0-workspace' || route.name === 'competition-workspace' }">
      <RouterView />
    </main>

    <DisclaimerModal v-if="auth.needsDisclaimer" />
  </div>
</template>
