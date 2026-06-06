<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { buildConflictHighlightHtml, conflictSegmentsForFieldValue } from '@/utils/conflictDiff'
import { useTextareaAutoGrow } from '@/composables/useTextareaAutoGrow'

const props = withDefaults(
  defineProps<{
    modelValue: string
    conflictSources: Array<{ filename: string; value: string }>
    rows?: number
    placeholder?: string
    readonly?: boolean
  }>(),
  {
    modelValue: '',
    rows: 2,
    placeholder: '',
    readonly: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const editorRef = ref<HTMLDivElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const backdropRef = ref<HTMLDivElement | null>(null)
const readonlyRef = ref<HTMLDivElement | null>(null)

const { autoGrow } = useTextareaAutoGrow(textareaRef, () => props.modelValue)

const highlightHtml = computed(() => {
  const segments = conflictSegmentsForFieldValue(props.modelValue, props.conflictSources)
  if (!segments.length) return escapePlain(props.modelValue)
  return buildConflictHighlightHtml(segments)
})

function escapePlain(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function syncBackdropHeight() {
  const textarea = textareaRef.value
  const backdrop = backdropRef.value
  if (!textarea || !backdrop) return
  backdrop.style.minHeight = `${textarea.offsetHeight}px`
}

function syncEditorHeight() {
  autoGrow()
  nextTick(() => {
    syncBackdropHeight()
  })
}

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
  syncEditorHeight()
}

watch(
  () => props.modelValue,
  () => {
    syncEditorHeight()
  },
)

watch(
  () => props.conflictSources,
  () => {
    syncEditorHeight()
  },
  { deep: true },
)

onMounted(() => {
  syncEditorHeight()
})
</script>

<template>
  <div ref="editorRef" class="conflict-highlight-editor input-conflict" :class="{ 'conflict-highlight-editor--readonly': readonly }">
    <div
      ref="backdropRef"
      class="conflict-highlight-backdrop"
      aria-hidden="true"
      v-html="highlightHtml || '&nbsp;'"
    />
    <textarea
      v-if="!readonly"
      ref="textareaRef"
      class="conflict-highlight-textarea auto-grow-textarea"
      :rows="1"
      :placeholder="placeholder"
      :value="modelValue"
      spellcheck="false"
      @input="onInput"
    />
    <div
      v-else
      ref="readonlyRef"
      class="conflict-highlight-readonly"
      v-html="highlightHtml || '—'"
    />
  </div>
</template>
