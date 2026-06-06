<script setup lang="ts">
defineProps<{
  error?: string
}>()

const emit = defineEmits<{
  standalone: []
  section: []
}>()
</script>

<template>
  <div class="add-field-popover" role="menu" @click.stop>
    <p class="add-field-popover-title">添加方式</p>

    <button type="button" class="add-field-quick" role="menuitem" @click="emit('standalone')">
      <span class="add-field-quick-icon" aria-hidden="true">＋</span>
      <span class="add-field-quick-text">
        <strong>新增标题</strong>
        <span class="add-field-quick-hint">新增一行，填写标题名称</span>
      </span>
    </button>

    <button type="button" class="add-field-quick" role="menuitem" @click="emit('section')">
      <span class="add-field-quick-icon" aria-hidden="true">＋</span>
      <span class="add-field-quick-text">
        <strong>新增内容</strong>
        <span class="add-field-quick-hint">新增内容分组，可拖动排序</span>
      </span>
    </button>

    <p v-if="error" class="add-field-popover-error">{{ error }}</p>
  </div>
</template>
