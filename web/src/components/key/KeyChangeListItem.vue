<template>
  <v-list-item slim :class="{ discardable }">
    <v-list-item-title class="text-body-medium key-label text-wrap">
      {{ keyLabel }}/<template v-if="fromVersion !== null">
        <s class="text-medium-emphasis">v{{ fromVersion }}</s>
        <v-icon icon="mdi-arrow-right" size="x-small"></v-icon> </template
      >v{{ toVersion }}
    </v-list-item-title>
    <v-list-item-subtitle class="text-truncate">{{ subtitle }}</v-list-item-subtitle>
    <v-list-item-subtitle v-if="errorText" class="text-error text-label-medium">
      <v-icon icon="mdi-alert-circle-outline" size="x-small"></v-icon>
      {{ errorText }}
      <v-tooltip
        activator="parent"
        location="bottom"
        @update:model-value="(open) => open && emit('load-error-detail')"
      >
        <div v-for="(line, i) in errorLines?.length ? errorLines : [errorText]" :key="i">
          {{ line }}
        </div>
      </v-tooltip>
    </v-list-item-subtitle>
    <template #append>
      <v-btn
        v-if="discardable"
        class="discard-btn"
        icon="mdi-close"
        variant="text"
        density="compact"
        @click.stop="emit('discard')"
      >
        <v-icon icon="mdi-close" size="small"></v-icon>
        <v-tooltip activator="parent" location="top">Discard this edit</v-tooltip>
      </v-btn>
      <span v-if="counts" class="text-body-medium counts">
        <span class="text-success key-label">+{{ counts.added }}</span>
        <span class="text-error key-label ml-1">-{{ counts.removed }}</span>
      </span>
      <slot name="append"></slot>
    </template>
  </v-list-item>
</template>

<script setup lang="ts">
import type { DiffCounts } from '@/composables/useDiff'

defineProps<{
  keyLabel: string
  fromVersion: number | null
  toVersion: number
  subtitle: string
  errorText?: string
  errorLines?: string[]
  counts?: DiffCounts
  discardable?: boolean
}>()

const emit = defineEmits<{ discard: []; 'load-error-detail': [] }>()
</script>

<style scoped>
.discard-btn {
  display: none;
}
.discardable:hover .discard-btn {
  display: inline-flex;
}
.discardable:hover .counts {
  display: none;
}
</style>
