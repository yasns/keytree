<template>
  <v-alert type="warning" variant="tonal" class="rounded-0">
    <div>A key below this bundle is retired:</div>
    <div v-for="ref in refs" :key="ref.label" class="key-label">
      {{ ref.label }} — {{ ref.reason === 'decommissioned' ? 'decommissioned' : 'mode archived' }}
    </div>
  </v-alert>
</template>

<script setup lang="ts">
import type { components } from '@/api-types'

defineProps<{ refs: components['schemas']['RetiredRefOut'][] }>()
</script>
