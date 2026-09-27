<template>
  <v-alert type="warning" variant="tonal" class="rounded-0">
    <div v-if="refs.length > 1">Some keys included below this one are retired:</div>
    <div v-else>A key included below this one is retired:</div>
    <ul>
      <li v-for="ref in refs" :key="ref.label">
        <span class="key-label">{{ ref.label }}</span> –
        {{ ref.reason === 'decommissioned' ? 'decommissioned' : 'mode archived' }}
      </li>
    </ul>
  </v-alert>
</template>

<script setup lang="ts">
import type { components } from '@/api-types'

defineProps<{ refs: components['schemas']['RetiredRefOut'][] }>()
</script>
