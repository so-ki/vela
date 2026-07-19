<script setup lang="ts">
defineProps<{
  state: 'loading' | 'empty' | 'error' | 'blocked' | 'readonly' | 'demo' | 'stale' | 'unknown'
  title: string
  detail: string
}>()
</script>

<template>
  <div class="rc0-state-panel" :class="`rc0-state-panel--${state}`" role="status">
    <span class="rc0-state-panel__mark" aria-hidden="true"></span>
    <div><strong>{{ title }}</strong><p>{{ detail }}</p></div>
  </div>
</template>
