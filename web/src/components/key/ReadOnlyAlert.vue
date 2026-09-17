<template>
  <v-alert
    type="info"
    variant="tonal"
    density="compact"
    :text="readOnlyReason"
    class="rounded-0"
  ></v-alert>
</template>

<script setup lang="ts">
import { readOnlyReason } from '@/composables/useReadOnly'
</script>
