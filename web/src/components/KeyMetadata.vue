<template>
  <v-expansion-panels variant="accordion" class="rounded-bottom border-b" flat v-model="panel">
    <v-expansion-panel>
      <v-expansion-panel-title>
        <div class="d-flex flex-column align-start ga-2" style="min-width: 0">
          <div class="text-body-small text-medium-emphasis">{{ subsystem }} / {{ name }}</div>
          <div class="d-flex align-center ga-1">
            <span class="text-title-medium">{{ mode }}</span>
            <v-chip size="small" density="compact" label variant="outlined"
              >v{{ displayVersion }}</v-chip
            >
            <v-chip v-if="staged" size="small" density="compact" label variant="tonal"
              >draft</v-chip
            >
          </div>
          <div
            v-if="hasDetail"
            class="text-body-small text-medium-emphasis text-truncate"
            style="width: 100%"
          >
            {{ relativeTime((staged?.created_at ?? payload?.created_at)!)
            }}<template v-if="staged?.comment ?? payload?.comment">
              | {{ staged?.comment ?? payload?.comment }}</template
            >
          </div>
        </div>
      </v-expansion-panel-title>
      <v-expansion-panel-text v-if="hasDetail" class="text-caption">
        <label class="text-body-medium">
          <div class="font-weight-medium">Key label</div>

          <div class="d-flex align-center ga-1">
            <code class="v-code text-truncate">{{ displayLabel }}</code>
            <CopyButton :text="displayLabel!"></CopyButton>
          </div>
        </label>

        <div class="meta-grid text-body-medium mt-2">
          <span class="font-weight-medium">Created at:</span>
          <span>{{
            new Date((staged?.created_at ?? payload?.created_at)!).toLocaleString(LOCALE)
          }}</span>

          <span class="font-weight-medium">Created by:</span>
          <span>{{ staged?.created_by ?? payload?.created_by }}</span>

          <span class="font-weight-medium">Comment:</span>
          <span>{{ staged?.comment ?? payload?.comment }}</span>
        </div>
      </v-expansion-panel-text>
    </v-expansion-panel>
  </v-expansion-panels>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { components } from '@/api-types'
import { useNavStore } from '@/stores/nav'
import CopyButton from './CopyButton.vue'

type KeyOut = components['schemas']['KeyOut']
type StagedEditOut = components['schemas']['StagedEditOut']

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
  staged?: StagedEditOut
}>()

const nav = useNavStore()
const panel = ref(undefined)

const displayVersion = computed(() =>
  props.staged ? props.staged.base_version + 1 : props.version,
)
const displayLabel = computed(() =>
  props.staged
    ? `${props.subsystem}/${props.name}/${props.mode}/v${displayVersion.value}`
    : props.payload?.label,
)
const hasDetail = computed(() => !!props.staged || !!props.payload)
</script>

<style scoped>
.v-code {
  font-size: 0.875rem;
}

.meta-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: start;
  column-gap: 4px;
  row-gap: 4px;
}
</style>
