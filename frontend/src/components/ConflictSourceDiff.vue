<script setup lang="ts">
import { computed } from 'vue'
import { segmentConflictSources, uniqueExcerpt } from '@/utils/conflictDiff'

const props = withDefaults(
  defineProps<{
    sources: Array<{ filename: string; value: string }>
    compact?: boolean
    showLegend?: boolean
  }>(),
  {
    compact: false,
    showLegend: true,
  },
)

const segmented = computed(() => segmentConflictSources(props.sources))

const hasAnyDifference = computed(() => segmented.value.some((item) => item.uniqueCount > 0))

const pairwiseSummary = computed(() => {
  if (props.sources.length !== 2) return []
  const [a, b] = props.sources
  const aOnly = uniqueExcerpt(a.value, [b.value])
  const bOnly = uniqueExcerpt(b.value, [a.value])
  if (!aOnly && !bOnly) return []
  return [
    { filename: a.filename, excerpt: aOnly },
    { filename: b.filename, excerpt: bOnly },
  ].filter((item) => item.excerpt)
})
</script>

<template>
  <div class="conflict-source-diff">
    <p v-if="showLegend && hasAnyDifference" class="conflict-diff-legend">
      <span class="conflict-diff-swatch" aria-hidden="true" />
      黄色高亮 = 该片段未在其他文件中出现（即冲突差异部分）
    </p>

    <ul v-if="pairwiseSummary.length" class="conflict-diff-summary">
      <li v-for="item in pairwiseSummary" :key="item.filename">
        <strong>{{ item.filename }}</strong>
        <span class="muted">独有内容：</span>
        <span>{{ item.excerpt }}</span>
      </li>
    </ul>

    <ul class="conflict-source-list" :class="{ 'conflict-source-list--compact': compact }">
      <li
        v-for="source in segmented"
        :key="source.filename"
        class="conflict-source-item"
        :class="{ 'conflict-source-item--all-diff': source.fullyDifferent }"
      >
        <div class="conflict-source-filename">
          <span>{{ source.filename }}</span>
          <span v-if="source.uniqueCount" class="conflict-diff-count">
            {{ source.fullyDifferent ? '与其他文件完全不同' : `${source.uniqueCount} 处不同` }}
          </span>
          <span v-else class="conflict-diff-count conflict-diff-count--none">无独有片段</span>
        </div>
        <div class="conflict-source-value">
          <template v-for="(segment, segmentIndex) in source.segments" :key="segmentIndex">
            <mark v-if="segment.kind === 'unique'" class="conflict-diff-unique">{{ segment.text }}</mark>
            <span v-else>{{ segment.text }}</span>
          </template>
        </div>
      </li>
    </ul>
  </div>
</template>
