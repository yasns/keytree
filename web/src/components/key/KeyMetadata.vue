<template>
  <v-expansion-panels variant="accordion" class="rounded-bottom border-b" flat v-model="panel">
    <v-expansion-panel>
      <v-expansion-panel-title>
        <div class="d-flex flex-column align-start ga-2" style="min-width: 0">
          <div class="text-body-small text-medium-emphasis">{{ subsystem }} / {{ name }}</div>
          <div class="d-flex align-center ga-1">
            <span class="text-title-medium"
              ><DiffText :runs="modeRuns" :highlight-class="diffHighlightClass"></DiffText
            ></span>
            <v-chip size="small" density="compact" label variant="outlined"
              >v<DiffText :runs="versionRuns" :highlight-class="diffHighlightClass"></DiffText
            ></v-chip>
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
              v-if="archived || archivalPending"
              size="small"
              density="compact"
              label
              variant="tonal"
              :color="archivalPending ? 'warning' : 'error'"
              >{{
                archivalPending ? (archived ? 'archive pending' : 'unarchive pending') : 'archived'
              }}</v-chip
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
            <CopyButton :text="ownFields.displayLabel"></CopyButton>
            <span class="key-label text-truncate"
              ><DiffText :runs="displayLabelRuns" :highlight-class="diffHighlightClass"></DiffText
            ></span>
          </div>
        </label>

        <template v-if="pendingEdit?.comment ?? payload?.comment">
          <div class="comment-block mt-2">
            <div class="font-weight-medium">Comment</div>
            <div class="text-body-medium">
              <DiffText :runs="commentRuns" :highlight-class="diffHighlightClass"></DiffText>
            </div>
          </div>
        </template>

        <v-divider class="my-2"></v-divider>

        <div class="meta-grid">
          <span class="font-weight-medium">Subsystem:</span>
          <span>{{ subsystem }}</span>

          <span class="font-weight-medium">Path:</span>
          <span>{{ name }}</span>

          <span class="font-weight-medium">Mode:</span>
          <span><DiffText :runs="modeRuns" :highlight-class="diffHighlightClass"></DiffText></span>

          <span class="font-weight-medium">Version:</span>
          <span
            ><DiffText :runs="versionRuns" :highlight-class="diffHighlightClass"></DiffText
          ></span>
        </div>

        <v-divider class="my-2"></v-divider>

        <div class="meta-grid">
          <span class="font-weight-medium">Validation:</span>
          <span
            ><DiffText :runs="validationStatusRuns" :highlight-class="diffHighlightClass"></DiffText
          ></span>

          <template v-if="!pendingEdit">
            <span class="font-weight-medium">Created at:</span>
            <span
              ><DiffText :runs="createdAtRuns" :highlight-class="diffHighlightClass"></DiffText
            ></span>

            <span class="font-weight-medium">Created by:</span>
            <span
              ><DiffText :runs="createdByRuns" :highlight-class="diffHighlightClass"></DiffText
            ></span>
          </template>
        </div>

        <template v-if="archived">
          <v-divider class="my-2"></v-divider>

          <div class="meta-grid">
            <span class="font-weight-medium">Archived at:</span>
            <span>{{ archivedAtText }}</span>

            <span class="font-weight-medium">Archived by:</span>
            <span>{{ archivedByText }}</span>
          </div>
        </template>

        <template v-if="basedOn">
          <v-divider class="my-2"></v-divider>

          <div>
            <div class="font-weight-medium">Based on</div>
            <div class="d-flex align-center ga-1">
              <v-btn
                icon="mdi-open-in-new"
                size="small"
                variant="text"
                density="comfortable"
                :href="basedOnHref"
                target="_blank"
                rel="noopener"
              ></v-btn>
              <span class="key-label text-truncate"
                ><DiffText :runs="basedOnRuns" :highlight-class="diffHighlightClass"></DiffText
              ></span>
            </div>
          </div>
        </template>
      </v-expansion-panel-text>
    </v-expansion-panel>
  </v-expansion-panels>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useRouter } from 'vue-router'
import type { components } from '@/api-types'
import { useCurrentMode, useIsArchived, useModesByPath } from '@/composables/useModes'
import { LOCALE, relativeTime } from '@/format'
import { keyRoute } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useChangesStore } from '@/stores/changes'
import type { ScrollSide } from '@/composables/useSyncedScroll'
import { runsFor, sideHighlightClass, type ColumnDiffData } from '@/composables/useDiff'
import CopyButton from '../CopyButton.vue'
import DiffText from '../diff/DiffText.vue'

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
  side?: ScrollSide
  counterpart?: ColumnDiffData
}>()

type FieldsInput = {
  subsystem?: string
  name?: string
  mode: string
  version: number
  payload?: KeyOut
  staged?: StagedEditOut
  pending?: boolean
}

/** Extracted so "own" and "counterpart" fields are derived identically for diffing. */
function fieldsOf(input: FieldsInput, authDisplayName: string | undefined) {
  const { payload, staged, pending, subsystem, name, mode, version } = input
  const pendingEdit = pending ? staged : undefined
  const displayLabel = pendingEdit
    ? `${subsystem}/${name}/${mode}/v${version}`
    : (payload?.label ?? '')
  const comment = pendingEdit?.comment ?? payload?.comment ?? ''
  const basedOnLabel = (pendingEdit?.based_on ?? payload?.based_on)?.label ?? ''
  const createdBy = pendingEdit?.created_by ?? payload?.created_by
  const createdByDisplayName = pendingEdit ? authDisplayName : payload?.created_by_display_name
  const createdByText = createdBy
    ? createdByDisplayName
      ? `${createdByDisplayName} (${createdBy})`
      : createdBy
    : ''
  const createdAt = pendingEdit ? undefined : payload?.created_at
  const createdAtText = createdAt ? new Date(createdAt).toLocaleString(LOCALE) : ''
  const validationStatus = pendingEdit?.validation_status ?? payload?.validation_status ?? ''
  return {
    displayLabel,
    mode,
    version: String(version),
    comment,
    basedOnLabel,
    createdByText,
    createdAtText,
    validationStatus,
  }
}

const panel = defineModel<number | undefined>('panel')

const auth = useAuthStore()
const changes = useChangesStore()
const router = useRouter()

const pendingEdit = computed(() => (props.pending ? props.staged : undefined))

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
const archivedAtText = computed(() => {
  const at = currentMode.value?.archived_at
  return at ? new Date(at).toLocaleString(LOCALE) : ''
})
const archivedByText = computed(() => {
  const by = currentMode.value?.archived_by
  if (!by) return ''
  const displayName = currentMode.value?.archived_by_display_name
  return displayName ? `${displayName} (${by})` : by
})

const hasDetail = computed(() => !!pendingEdit.value || !!props.payload)

const ownFields = computed(() => fieldsOf(props, auth.displayName))
const counterpartFields = computed(
  () => props.counterpart && fieldsOf(props.counterpart, auth.displayName),
)

const displayLabelRuns = computed(() =>
  runsFor(ownFields.value.displayLabel, counterpartFields.value?.displayLabel),
)
const modeRuns = computed(() => runsFor(ownFields.value.mode, counterpartFields.value?.mode))
const versionRuns = computed(() =>
  runsFor(ownFields.value.version, counterpartFields.value?.version),
)
const commentRuns = computed(() =>
  runsFor(ownFields.value.comment, counterpartFields.value?.comment),
)
const basedOnRuns = computed(() =>
  runsFor(ownFields.value.basedOnLabel, counterpartFields.value?.basedOnLabel),
)
const createdByRuns = computed(() =>
  runsFor(ownFields.value.createdByText, counterpartFields.value?.createdByText),
)
const createdAtRuns = computed(() =>
  runsFor(ownFields.value.createdAtText, counterpartFields.value?.createdAtText),
)
const validationStatusRuns = computed(() =>
  runsFor(ownFields.value.validationStatus, counterpartFields.value?.validationStatus),
)
const diffHighlightClass = computed(() => sideHighlightClass(props.side))
</script>
