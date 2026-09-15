<template>
  <span v-for="(run, i) in runs" :key="i" :class="run.changed ? highlightClass : undefined">{{
    run.text
  }}</span>
</template>

<script setup lang="ts">
import type { DiffRun } from '@/composables/useDiff'

defineProps<{ runs: DiffRun[]; highlightClass?: string }>()
</script>
