<template>
  <v-alert
    type="info"
    variant="tonal"
    density="compact"
    :text="reason ?? readOnlyReason"
    class="rounded-0"
  ></v-alert>
</template>

<script setup lang="ts">
import { readOnlyReason } from '@/composables/useReadOnly'

defineProps<{ reason?: string }>()
</script>
