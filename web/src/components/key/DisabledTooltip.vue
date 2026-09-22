<template>
  <v-tooltip :disabled="!reason" :text="reason">
    <template v-slot:activator="{ props }">
      <div v-bind="props"><slot></slot></div>
    </template>
  </v-tooltip>
</template>

<script setup lang="ts">
defineProps<{ reason?: string }>()
</script>
