<script setup lang="ts">
import { ref } from 'vue'
import { useTextareaAutoGrow } from '@/composables/useTextareaAutoGrow'

const props = withDefaults(
  defineProps<{
    modelValue: string
    rows?: number
    placeholder?: string
    inputClass?: string
  }>(),
  {
    modelValue: '',
    rows: 2,
    placeholder: '',
    inputClass: 'cell-textarea',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const { autoGrow } = useTextareaAutoGrow(textareaRef, () => props.modelValue)

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
  autoGrow()
}
</script>

<template>
  <textarea
    ref="textareaRef"
    :class="[inputClass, 'auto-grow-textarea']"
    :rows="rows"
    :placeholder="placeholder"
    :value="modelValue"
    @input="onInput"
  />
</template>
