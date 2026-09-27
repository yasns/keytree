<template>
  <v-tooltip :disabled="!reason" :text="reason" :location="location">
    <template v-slot:activator="{ props }">
      <div v-bind="props"><slot></slot></div>
    </template>
  </v-tooltip>
</template>

<script setup lang="ts">
import type { Anchor } from 'vuetify/lib/util/anchor.mjs'

defineProps<{ reason?: string; location?: Anchor }>()
</script>
