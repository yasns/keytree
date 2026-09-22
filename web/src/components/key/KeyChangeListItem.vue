<template>
  <v-list-item slim :class="{ discardable }" lines="two">
    <template v-if="$slots.prepend" #prepend>
      <slot name="prepend"></slot>
    </template>
    <v-list-item-title class="text-body-medium key-label key-label-truncate">
      <span class="key-label-head">{{ headLabel }}</span
      ><span class="key-label-tail"
        >{{ modeTail }}/<template v-if="fromVersion !== null">
          <s class="text-medium-emphasis">v{{ fromVersion }}</s>
          <v-icon icon="mdi-arrow-right" size="x-small"></v-icon> </template
        >v{{ toVersion }}
      </span>
    </v-list-item-title>
    <v-list-item-subtitle class="text-truncate">{{ subtitle }}</v-list-item-subtitle>
    <v-list-item-subtitle v-if="errorText" class="text-error text-label-medium mt-1">
      <v-icon icon="mdi-alert-circle-outline" size="x-small"></v-icon>
      {{ errorText }}.
      <a
        href="#"
        class="text-error ml-1 hover-underline"
        @click.stop.prevent="emit('view-problems')"
        >View problems</a
      >
    </v-list-item-subtitle>
    <template #append>
      <v-btn
        v-if="discardable"
        class="discard-btn"
        icon="mdi-close"
        size="small"
        variant="text"
        density="comfortable"
        @click.stop="emit('discard')"
      >
        <v-icon icon="mdi-close"></v-icon>
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
import { computed } from 'vue'
import { labelTailStart, type DiffCounts } from '@/composables/useDiff'

const props = defineProps<{
  keyLabel: string
  fromVersion: number | null
  toVersion: number
  subtitle: string
  errorText?: string
  counts?: DiffCounts
  discardable?: boolean
}>()

const emit = defineEmits<{ discard: []; 'view-problems': [] }>()

const headLabel = computed(() => props.keyLabel.slice(0, labelTailStart(props.keyLabel)))
const modeTail = computed(() => props.keyLabel.slice(labelTailStart(props.keyLabel)))
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
