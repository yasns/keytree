<template>
  <v-tooltip :disabled="!readOnly" :text="readOnlyReason">
    <template v-slot:activator="{ props }">
      <div v-bind="props"><slot></slot></div>
    </template>
  </v-tooltip>
</template>

<script setup lang="ts">
import { readOnlyReason } from '@/composables/useReadOnly'

defineProps<{ readOnly?: boolean }>()
</script>
