<template>
  <v-toolbar density="compact" class="px-4">
    <template v-slot:prepend>
      <v-tooltip v-if="props.payloadFileType" location="bottom">
        <template v-slot:activator="{ props: tooltipProps }">
          <v-chip
            size="small"
            density="compact"
            label
            variant="tonal"
            class="me-1"
            :color="validation.color"
            :style="validation.errors.length ? undefined : 'cursor: default'"
            :prepend-icon="validation.icon"
            @click="validation.errors.length && emit('show-problems')"
            v-bind="tooltipProps"
          >
            {{ props.payloadFileType }}
          </v-chip>
        </template>
        <div v-if="validation.errors.length">
          <div v-for="(message, i) in validation.errors" :key="i">{{ message }}</div>
        </div>
        <span v-else>{{ validation.text }}</span>
      </v-tooltip>

      <DisabledTooltip :reason="discardDisabledReason" location="bottom">
        <v-btn @click="discardDialog = true" variant="text" :disabled="!!discardDisabledReason"
          >Discard</v-btn
        >
      </DisabledTooltip>
    </template>

    <template v-slot:append>
      <DisabledTooltip :reason="saveDisabledReason" location="bottom">
        <v-btn
          :prepend-icon="canQueue ? 'mdi-tray-arrow-up' : 'mdi-content-save'"
          @click="saveDialog = true"
          variant="flat"
          color="primary"
          class="me-1"
          :disabled="!!saveDisabledReason"
        >
          Save
          <span v-if="props.canQueue">&nbsp;& Queue</span>
        </v-btn>
      </DisabledTooltip>

      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-dots-vertical"
            variant="text"
            density="comfortable"
            v-bind="props"
          ></v-btn>
        </template>
        <v-list density="compact">
          <template v-if="subsystem && name && mode">
            <v-list-item
              title="Compare with..."
              prepend-icon="mdi-compare-horizontal"
              @click="compareDialog = true"
            ></v-list-item>
            <v-divider></v-divider>
          </template>

          <template v-for="group in menuGroups" :key="group.label">
            <v-divider v-if="group.divider"></v-divider>
            <v-list-subheader>{{ group.label }}</v-list-subheader>
            <DisabledTooltip
              v-for="item in group.items"
              :key="item.title"
              :reason="itemDisabled(item) ? itemReason(item) : undefined"
            >
              <v-list-item
                :title="item.title"
                :disabled="itemDisabled(item)"
                @click="item.onClick"
                :prepend-icon="item.icon"
              ></v-list-item>
            </DisabledTooltip>
          </template>
        </v-list>
      </v-menu>
    </template>
  </v-toolbar>

  <SaveDialog
    v-model="saveDialog"
    :initial-comment="stagedComment"
    @save="onSaveConfirmed"
  ></SaveDialog>

  <ConfirmDialog
    v-model="discardDialog"
    title="Discard changes?"
    text="Do you really want to discard this draft? This action is irreversible."
    confirm-text="Discard"
    @confirm="emit('discard')"
  ></ConfirmDialog>

  <ForkModeDialog
    v-model="forkDialog"
    :existing="modes.map((m) => m.name)"
    @fork="(name, description) => emit('fork', name, description)"
  ></ForkModeDialog>

  <CopyToModeDialog
    v-model="copyDialog"
    :modes="modes"
    :current="mode ?? ''"
    @copy="(target, comment) => emit('copy-to', target, comment)"
  ></CopyToModeDialog>

  <SaveDialog
    v-model="copyLatestDialog"
    title="Restore as Latest Version"
    confirm-text="Restore"
    :initial-comment="`Restore of ${subsystem}/${name}/${mode}/v${version}`"
    :warning="pendingWarning"
    @save="(comment) => emit('copy-to', mode ?? '', comment)"
  ></SaveDialog>

  <CompareDialog
    v-if="subsystem && name"
    v-model="compareDialog"
    :subsystem="subsystem"
    :name="name"
    :current-mode="mode"
    :current-version="currentVersionTarget"
    @compare="onCompare"
  ></CompareDialog>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import { useRouter } from 'vue-router'
import ConfirmDialog from '../dialog/ConfirmDialog.vue'
import DisabledTooltip from './DisabledTooltip.vue'
import SaveDialog from '../dialog/SaveDialog.vue'
import ForkModeDialog from '../dialog/ForkModeDialog.vue'
import CopyToModeDialog from '../dialog/CopyToModeDialog.vue'
import CompareDialog from '../dialog/CompareDialog.vue'
import {
  useCurrentMode,
  useIsArchived,
  useModesByPath,
  useToggleArchival,
} from '@/composables/useModes'
import { readOnlyReason, useIsDecommissioned, useReadOnly } from '@/composables/useReadOnly'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import { pushDiffRoute, type DiffTarget } from '@/router'
import type { components } from '@/api-types'

type KeyOut = components['schemas']['KeyOut']

const props = withDefaults(
  defineProps<{
    dirty: boolean
    staged: boolean
    stagedComment?: string
    canQueue?: boolean
    subsystem?: string
    name?: string
    mode?: string
    version?: number
    committed?: boolean
    readOnly?: boolean
    /** Live Monaco marker messages for this key's own payload editor; undefined where not applicable. */
    validationErrors?: string[]
    payload?: KeyOut
    hasPayloadEditor?: boolean
    payloadFileType?: string
  }>(),
  { committed: true },
)
const emit = defineEmits<{
  save: [comment: string]
  'save-and-queue': [comment: string]
  discard: []
  fork: [name: string, description: string]
  'copy-to': [mode: string, comment: string]
  'export-payload': []
  'import-payload': []
  'show-problems': []
}>()

const changes = useChangesStore()
const snackbar = useSnackbarStore()
const router = useRouter()

// Absent errors mean validation never ran (non-YAML formats), which must not read as a clean result.
const validation = computed(() => {
  const errors = props.validationErrors
  if (!errors) return { icon: undefined, color: undefined, errors: [], text: 'Not validated' }
  if (errors.length) return { icon: 'mdi-alert-circle-outline', color: 'error', errors, text: '' }
  return {
    icon: 'mdi-check-circle-outline',
    color: undefined,
    errors: [],
    text: 'No validation problems',
  }
})

async function toggleDecommission(keyId: number) {
  await changes.toggleDecommission(keyId)
  snackbar.notify(
    decommissioned.value ? 'Key decommission staged' : 'Key recommission staged',
    'info',
  )
}

const toggleArchival = useToggleArchival()

const saveDialog = ref(false)
const discardDialog = ref(false)
const forkDialog = ref(false)
const copyDialog = ref(false)
const copyLatestDialog = ref(false)
const compareDialog = ref(false)
const modes = useModesByPath(toRef(props, 'subsystem'), toRef(props, 'name'))

const currentMode = useCurrentMode(modes, toRef(props, 'mode'))
const archived = useIsArchived(currentMode)
const decommissioned = useIsDecommissioned(toRef(props, 'payload'))
const authReadOnly = useReadOnly(() => props.subsystem ?? '')
const isOldVersion = computed(() => {
  const versions = currentMode.value?.versions
  return props.committed && !!versions?.length && props.version !== versions[0]
})

const discardDisabledReason = computed(() => {
  if (authReadOnly.value || props.readOnly) return readOnlyReason
  if (!props.dirty) return 'No changes to discard'
  return undefined
})

const saveDisabledReason = computed(() => {
  if (authReadOnly.value || props.readOnly) return readOnlyReason
  if (!props.dirty) return 'No changes to save'
  return undefined
})

/** Staging a copy onto this mode would replace its existing pending version, if any. */
const pendingWarning = computed(() => {
  if (!props.subsystem || !props.name || !props.mode) return undefined
  return changes.stagedForMode(props.subsystem, props.name, props.mode)
    ? 'This mode already has a pending version. Copying this will replace it.'
    : undefined
})

type KebabItem = {
  title: string
  icon: string
  onClick: () => void
  disabled?: boolean
  disabledReason?: string
  ignoreGroupDisabled?: boolean
}
type MenuGroup = { label: string; divider: boolean; items: KebabItem[] }

const menuDisabledReason = computed(() => {
  if (authReadOnly.value) return readOnlyReason
  if (!props.committed) return 'Commit the changes first'
  return undefined
})

function itemDisabled(item: KebabItem): boolean {
  if (item.ignoreGroupDisabled) return !!item.disabled
  return !!item.disabled || !!menuDisabledReason.value
}

function itemReason(item: KebabItem): string | undefined {
  if (item.disabled) return item.disabledReason
  if (item.ignoreGroupDisabled) return undefined
  return menuDisabledReason.value
}

const menuGroups = computed(() => {
  const versionControlItems: KebabItem[] = [
    {
      title: 'Fork to New Mode...',
      icon: 'mdi-source-fork',
      onClick: () => (forkDialog.value = true),
    },
    {
      title: 'Copy to Existing Mode...',
      icon: 'mdi-source-pull',
      onClick: () => (copyDialog.value = true),
    },
    {
      title: 'Restore as Latest Version...',
      icon: 'mdi-update',
      onClick: () => (copyLatestDialog.value = true),
      disabled: !isOldVersion.value,
      disabledReason: isOldVersion.value ? undefined : 'Already at the latest version',
    },
  ]

  const groups: MenuGroup[] = [{ label: 'Duplicate', divider: false, items: versionControlItems }]

  if (props.hasPayloadEditor) {
    groups.push({
      label: 'File',
      divider: true,
      items: [
        {
          title: props.payloadFileType
            ? `Import ${props.payloadFileType} File...`
            : 'Import File...',
          icon: 'mdi-import',
          onClick: () => emit('import-payload'),
          disabled: props.readOnly,
          disabledReason: props.readOnly ? readOnlyReason : undefined,
        },
        {
          title: props.payloadFileType
            ? `Export to ${props.payloadFileType} File`
            : 'Export to File',
          icon: 'mdi-download',
          onClick: () => emit('export-payload'),
          ignoreGroupDisabled: true,
        },
      ],
    })
  }

  const lifecycleItems: KebabItem[] = []
  if (props.payload) {
    const payload = props.payload
    lifecycleItems.push({
      title: decommissioned.value ? 'Recommission Key' : 'Decommission Key',
      icon: decommissioned.value ? 'mdi-key-plus' : 'mdi-key-remove',
      onClick: () => void toggleDecommission(payload.id),
    })
  }
  if (currentMode.value) {
    const mode = currentMode.value
    lifecycleItems.push({
      title: archived.value ? 'Unarchive Mode' : 'Archive Mode',
      icon: archived.value ? 'mdi-archive-off-outline' : 'mdi-archive-outline',
      onClick: () => void toggleArchival(mode),
    })
  }
  if (lifecycleItems.length) {
    groups.push({ label: 'Lifecycle', divider: true, items: lifecycleItems })
  }

  return groups
})

function onSaveConfirmed(comment: string) {
  if (props.canQueue) emit('save-and-queue', comment)
  else emit('save', comment)
}

const currentVersionTarget = computed<DiffTarget['version'] | undefined>(() => {
  if (props.version === undefined) return undefined
  return props.committed ? props.version : ('pending' as const)
})

async function onCompare(target: DiffTarget) {
  const { subsystem, name, mode } = props
  if (!subsystem || !name || !mode || currentVersionTarget.value === undefined) return
  if (!(await changes.confirmDiscard())) return
  pushDiffRoute(router, subsystem, name, mode, currentVersionTarget.value, target)
}
</script>
