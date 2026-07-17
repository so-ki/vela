<script setup lang="ts">
import { computed } from 'vue'
import type { CapabilityPackDisplay } from '@/types/scenario'

const props = withDefaults(
  defineProps<{
    pack: CapabilityPackDisplay | null
    frozen?: boolean
    compact?: boolean
  }>(),
  {
    frozen: false,
    compact: false,
  },
)

const isFrozen = computed(() => props.frozen || props.pack?.status === 'frozen')
const isOperational = computed(() => isFrozen.value || props.pack?.status === 'active')
const eyebrow = computed(() =>
  isFrozen.value ? '已冻结试点能力包' : isOperational.value ? '当前受控试点能力包' : '待工程复核的能力包',
)
const statusLabel = computed(() =>
  isFrozen.value ? '工程配置已冻结' : isOperational.value ? '工程可用' : '待工程复核',
)
const boundaryLabel = computed(() =>
  props.pack?.content_status === 'expert_verified'
    ? '当前仅覆盖上述场景的受控试点流程；工程状态不等同于正式法律意见。'
    : '当前仅覆盖上述场景的受控试点流程；法律内容为临时版本，须由巴西执业律师或相关专家逐项复核。',
)
</script>

<template>
  <section
    class="panel capability-pack-card"
    :class="{ 'is-frozen': isFrozen, compact }"
    :data-pack-id="pack?.pack_id"
  >
    <p class="eyebrow dark">{{ eyebrow }}</p>
    <template v-if="pack">
      <h2>{{ pack.display_name }}</h2>
      <div class="capability-pack-meta">
        <span>版本 {{ pack.version }}</span>
        <span class="badge" :class="{ ok: isOperational }">{{ statusLabel }}</span>
      </div>
      <p v-if="pack.description && !compact" class="muted">{{ pack.description }}</p>
      <p class="muted capability-pack-boundary">{{ boundaryLabel }}</p>
    </template>
    <template v-else>
      <h2>能力包加载失败</h2>
      <p class="error">无法加载当前受控试点能力包，已禁止确认与提交，请刷新重试。</p>
    </template>
    <slot />
  </section>
</template>

<style scoped>
.capability-pack-card h2 {
  margin: 0.25rem 0;
}

.capability-pack-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.capability-pack-boundary {
  margin-bottom: 0;
}

.capability-pack-card.is-frozen {
  border-color: color-mix(in srgb, var(--primary, #244d3f) 38%, var(--border-muted, #ddd));
}

.capability-pack-card.compact {
  padding: 0.75rem 1rem;
}
</style>
