import { nextTick, onMounted, watch, type Ref } from 'vue'

export function useTextareaAutoGrow(
  textareaRef: Ref<HTMLTextAreaElement | null>,
  value: Ref<string> | (() => string),
) {
  function getValue() {
    return typeof value === 'function' ? value() : value.value
  }

  function autoGrow() {
    const textarea = textareaRef.value
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${textarea.scrollHeight}px`
  }

  watch(
    () => getValue(),
    () => {
      nextTick(autoGrow)
    },
  )

  onMounted(() => {
    nextTick(autoGrow)
  })

  return { autoGrow }
}
