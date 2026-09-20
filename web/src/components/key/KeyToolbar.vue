<template>
  <v-toolbar density="compact" class="bg-surface border-b-sm">
    <template v-slot:prepend>
      <ReadOnlyTooltip v-if="dirty" :read-only="readOnly">
        <v-btn
          @click="discardDialog = true"
          prepend-icon="mdi-trash-can-outline"
          variant="tonal"
          :disabled="readOnly"
          >Discard</v-btn
        >
      </ReadOnlyTooltip>
    </template>

    <template v-slot:append>
      <ReadOnlyTooltip v-if="dirty" :read-only="readOnly">
        <v-btn
          :prepend-icon="canQueue ? 'mdi-check' : 'mdi-check-all'"
          @click="saveDialog = true"
          variant="flat"
          color="primary"
          :disabled="readOnly"
        >
          Save
          <span v-if="props.canQueue">&nbsp;and Queue</span>
        </v-btn>
      </ReadOnlyTooltip>

      <v-divider v-if="dirty" vertical inset class="mx-1"></v-divider>

      <v-tooltip v-if="validationErrors">
        <template v-slot:activator="{ props }">
          <v-btn
            :icon="
              validationErrors.length ? 'mdi-alert-circle-outline' : 'mdi-check-circle-outline'
            "
            :color="validationErrors.length ? 'error' : 'success'"
            density="comfortable"
            v-bind="props"
          ></v-btn>
        </template>
        <div v-if="validationErrors.length">
          <div v-for="(message, i) in validationErrors" :key="i">{{ message }}</div>
        </div>
        <span v-else>No validation problems</span>
      </v-tooltip>

      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn icon="mdi-dots-vertical" density="comfortable" v-bind="props"></v-btn>
        </template>
        <v-list density="compact">
          <template v-if="subsystem && name && mode">
            <v-list-subheader>Compare</v-list-subheader>
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
            <v-tooltip
              v-for="item in group.items"
              :key="item.title"
              :disabled="!itemDisabled(item)"
              :text="itemReason(item)"
            >
              <template v-slot:activator="{ props }">
                <div v-bind="props">
                  <v-list-item
                    :title="item.title"
                    :disabled="itemDisabled(item)"
                    @click="item.onClick"
                    :prepend-icon="item.icon"
                  ></v-list-item>
                </div>
              </template>
            </v-tooltip>
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
    title="Copy to latest version"
    confirm-text="Stage"
    :initial-comment="`Copy of ${subsystem}/${name}/${mode}/v${version}`"
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
import SaveDialog from '../dialog/SaveDialog.vue'
import ForkModeDialog from '../dialog/ForkModeDialog.vue'
import CopyToModeDialog from '../dialog/CopyToModeDialog.vue'
import CompareDialog from '../dialog/CompareDialog.vue'
import { useCurrentMode, useIsArchived, useModesByPath } from '@/composables/useModes'
import { readOnlyReason, useIsDecommissioned, useReadOnly } from '@/composables/useReadOnly'
import { useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'
import { keyRoute, withDiffQuery, type DiffTarget } from '@/router'
import type { components } from '@/api-types'
import ReadOnlyTooltip from './ReadOnlyTooltip.vue'

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
}>()

const changes = useChangesStore()
const nav = useNavStore()
const router = useRouter()

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

/** Staging a copy onto this mode would replace its existing pending version, if any. */
const pendingWarning = computed(() => {
  if (!props.subsystem || !props.name || !props.mode) return undefined
  return changes.stagedForMode(props.subsystem, props.name, props.mode)
    ? 'This mode already has a pending version. Staging this copy will replace it.'
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
      title: 'Copy to Latest Version...',
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
      onClick: () => void changes.toggleDecommission(payload.id),
    })
  }
  if (currentMode.value) {
    const modeId = currentMode.value.id
    lifecycleItems.push({
      title: archived.value ? 'Unarchive Mode' : 'Archive Mode',
      icon: archived.value ? 'mdi-archive-off-outline' : 'mdi-archive-outline',
      onClick: () => void changes.toggleArchival(modeId),
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
  // Already comparing: keep the location from before that comparison started.
  if (!router.currentRoute.value.query.diff) {
    nav.preDiffLocation = router.currentRoute.value.fullPath
  }
  router.push({
    ...keyRoute(subsystem, name, mode, currentVersionTarget.value),
    query: withDiffQuery({}, target),
  })
}
</script>
