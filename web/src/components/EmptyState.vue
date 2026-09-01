<template>
  <div class="d-flex flex-column align-center justify-center h-100">
    <v-icon :icon="icon" size="48" class="text-medium-emphasis mb-4"></v-icon>
    <div v-if="title" class="text-h6">{{ title }}</div>
    <div v-if="text" class="text-body-small text-medium-emphasis mt-1">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ icon: string; title?: string; text?: string }>()
</script>
