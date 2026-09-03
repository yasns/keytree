<template>
  <v-expansion-panels variant="accordion" class="rounded-bottom border-b" flat v-model="panel">
    <v-expansion-panel>
      <v-expansion-panel-title>
        <div class="d-flex flex-column align-start ga-2" style="min-width: 0">
          <v-badge location="right center" offsetX="-15" :content="`v${version}`">
            <span class="text-title-medium">{{ mode }}</span>
          </v-badge>
          <div class="d-flex align-center ga-1" style="margin-left: -10px">
            <v-chip size="small" density="compact" label color="primary">{{ name }}</v-chip>
            <v-chip size="small" density="compact" label color="secondary">{{
              nav.subsystemDisplayName(subsystem)
            }}</v-chip>
          </div>
          <div
            v-if="payload"
            class="text-body-small text-medium-emphasis text-truncate"
            style="width: 100%"
          >
            {{ relativeTime(payload.created_at)
            }}<template v-if="payload.comment"> | {{ payload.comment }}</template>
          </div>
        </div>
      </v-expansion-panel-title>
      <v-expansion-panel-text v-if="payload" class="text-caption">
        <label class="text-body-medium">
          <div class="font-weight-medium">Key label</div>

          <div class="d-flex align-center ga-1">
            <code class="v-code text-truncate">{{ payload.label }}</code>
            <CopyButton :text="payload.label"></CopyButton>
          </div>
        </label>

        <div class="meta-grid text-body-medium mt-2">
          <v-icon icon="mdi-clock-outline" size="small"></v-icon>
          <span class="font-weight-medium">Created at:</span>
          <span>{{ new Date(payload.created_at).toLocaleString(LOCALE) }}</span>

          <v-icon icon="mdi-account-outline" size="small"></v-icon>
          <span class="font-weight-medium">Created by:</span>
          <span>{{ payload.created_by }}</span>

          <v-icon icon="mdi-comment-text-outline" size="small"></v-icon>
          <span class="font-weight-medium">Comment:</span>
          <span>{{ payload.comment }}</span>
        </div>
      </v-expansion-panel-text>
    </v-expansion-panel>
  </v-expansion-panels>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { components } from '@/api-types'
import { useNavStore } from '@/stores/nav'
import CopyButton from './CopyButton.vue'

type KeyOut = components['schemas']['KeyOut']

const LOCALE = new Intl.Locale('en-GB')
const RTF = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })
const RTF_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]

function relativeTime(iso: string): string {
  const diffSeconds = (new Date(iso).getTime() - Date.now()) / 1000
  const [unit, secs] = RTF_UNITS.find(([, secs]) => Math.abs(diffSeconds) >= secs) ?? ['second', 1]
  return RTF.format(Math.round(diffSeconds / secs), unit)
}

const props = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  payload?: KeyOut
}>()

const nav = useNavStore()
const panel = ref(undefined)
</script>

<style scoped>
.v-code {
  font-size: 0.875rem;
}

.meta-grid {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: start;
  column-gap: 4px;
  row-gap: 4px;
}
</style>
