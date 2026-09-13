<template>
  <v-expansion-panels variant="accordion" class="rounded-bottom border-b" flat v-model="panel">
    <v-expansion-panel>
      <v-expansion-panel-title>
        <div class="d-flex flex-column align-start ga-2" style="min-width: 0">
          <div class="text-body-small text-medium-emphasis">{{ subsystem }} / {{ name }}</div>
          <div class="d-flex align-center ga-1">
            <span class="text-title-medium">{{ mode }}</span>
            <v-chip size="small" density="compact" label variant="outlined">v{{ version }}</v-chip>
            <v-chip
              v-if="pendingEdit"
              size="small"
              density="compact"
              label
              variant="tonal"
              color="info"
              >pending</v-chip
            >
            <v-chip
              v-if="isLatest !== undefined && !pendingEdit"
              size="small"
              density="compact"
              label
              variant="tonal"
              :color="isLatest ? 'success' : undefined"
              >{{ isLatest ? 'latest' : 'old' }}</v-chip
            >
            <v-chip
              v-if="archived"
              size="small"
              density="compact"
              label
              variant="tonal"
              :color="archivalPending ? 'warning' : 'error'"
              >{{ archivalPending ? 'archive pending' : 'archived' }}</v-chip
            >
          </div>
          <div
            v-if="hasDetail"
            class="text-body-small text-medium-emphasis text-truncate"
            style="width: 100%"
          >
            <template v-if="!pendingEdit">{{ relativeTime(payload?.created_at!) }}</template
            ><template v-if="pendingEdit?.comment ?? payload?.comment"
              >{{ pendingEdit ? '' : ' | '
              }}{{ pendingEdit?.comment ?? payload?.comment }}</template
            >
          </div>
        </div>
      </v-expansion-panel-title>
      <v-expansion-panel-text v-if="hasDetail" class="text-caption text-body-medium">
        <label>
          <div class="font-weight-medium">Key label</div>
          <div class="d-flex align-center ga-1">
            <CopyButton :text="displayLabel!"></CopyButton>
            <code class="v-code text-truncate">{{ displayLabel }}</code>
          </div>
        </label>

        <div class="meta-grid mt-2">
          <template v-if="!pendingEdit">
            <span class="font-weight-medium">Created at:</span>
            <span>{{ new Date(payload?.created_at!).toLocaleString(LOCALE) }}</span>

            <span class="font-weight-medium">Created by:</span>
            <span>
              <template v-if="createdByDisplayName"
                >{{ createdByDisplayName }} ({{ createdBy }})</template
              >
              <template v-else>
                {{ createdBy }}
              </template>
            </span>
          </template>

          <span class="font-weight-medium">Comment:</span>
          <span>{{ pendingEdit?.comment ?? payload?.comment }}</span>
        </div>

        <template v-if="basedOn">
          <div class="font-weight-medium mt-2">Based on</div>
          <a :href="basedOnHref" target="_blank" rel="noopener">
            <code class="v-code">{{ basedOn.label }}</code>
          </a>
        </template>
      </v-expansion-panel-text>
    </v-expansion-panel>
  </v-expansion-panels>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import { useRouter } from 'vue-router'
import type { components } from '@/api-types'
import { useCurrentMode, useIsArchived, useModesByPath } from '@/composables/useModes'
import { LOCALE, relativeTime } from '@/format'
import { keyRoute } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useChangesStore } from '@/stores/changes'
import CopyButton from './CopyButton.vue'

type KeyOut = components['schemas']['KeyOut']
type StagedEditOut = components['schemas']['StagedEditOut']

const props = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  payload?: KeyOut
  staged?: StagedEditOut
  pending?: boolean
}>()

const panel = ref(undefined)

const auth = useAuthStore()
const changes = useChangesStore()
const router = useRouter()

const pendingEdit = computed(() => (props.pending ? props.staged : undefined))

const createdBy = computed(() => pendingEdit.value?.created_by ?? props.payload?.created_by)
const createdByDisplayName = computed(() =>
  pendingEdit.value ? auth.displayName : props.payload?.created_by_display_name,
)

const basedOn = computed(() => pendingEdit.value?.based_on ?? props.payload?.based_on)
const basedOnHref = computed(() => {
  const b = basedOn.value
  if (!b) return undefined
  return router.resolve(keyRoute(props.subsystem, props.name, b.mode_name, b.version)).href
})

const modes = useModesByPath(toRef(props, 'subsystem'), toRef(props, 'name'))
const currentMode = useCurrentMode(modes, toRef(props, 'mode'))

const isLatest = computed(() => {
  const latest = currentMode.value?.versions[0]
  return latest === undefined ? undefined : latest === props.version
})

const archived = useIsArchived(currentMode)
const archivalPending = computed(
  () => !!currentMode.value && !!changes.stagedArchival(currentMode.value.id),
)

const displayLabel = computed(() =>
  pendingEdit.value
    ? `${props.subsystem}/${props.name}/${props.mode}/v${props.version}`
    : props.payload?.label,
)
const hasDetail = computed(() => !!pendingEdit.value || !!props.payload)
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
