<template>
  <v-toolbar density="compact">
    <template v-slot:prepend>
      <v-tooltip v-if="dirty" text="Discard changes">
        <template v-slot:activator="{ props }">
          <v-btn
            @click="discardDialog = true"
            icon="mdi-trash-can-outline"
            density="comfortable"
            color="error"
            v-bind="props"
          ></v-btn>
        </template>
      </v-tooltip>
    </template>

    <template v-slot:append>
      <v-btn
        v-if="dirty"
        :prepend-icon="canQueue ? 'mdi-tray-plus' : 'mdi-tray-full'"
        @click="saveDialog = true"
        variant="flat"
        color="primary"
        rounded
      >
        Save
        <span v-if="props.canQueue">&nbsp;and Queue</span>
      </v-btn>

      <v-divider v-if="dirty" vertical inset class="mx-1"></v-divider>

      <v-tooltip v-if="dirty" text="Unsaved (click to stage)">
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-cloud-alert-outline"
            color="warning"
            @click="saveDialog = true"
            density="comfortable"
            v-bind="props"
          ></v-btn>
        </template>
      </v-tooltip>
      <v-tooltip v-else text="Saved">
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-cloud-check-variant-outline"
            density="comfortable"
            v-bind="props"
          ></v-btn>
        </template>
      </v-tooltip>

      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn icon="mdi-dots-vertical" density="comfortable" v-bind="props"></v-btn>
        </template>
        <v-list density="compact">
          <v-tooltip
            v-for="item in kebabItems"
            :key="item.title"
            :disabled="committed"
            text="Commit the changes first"
          >
            <template v-slot:activator="{ props }">
              <div v-bind="props">
                <v-list-item
                  :title="item.title"
                  :disabled="!committed"
                  @click="item.onClick"
                  :prepend-icon="item.icon"
                ></v-list-item>
              </div>
            </template>
          </v-tooltip>
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
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import SaveDialog from './SaveDialog.vue'
import ForkModeDialog from './ForkModeDialog.vue'
import CopyToModeDialog from './CopyToModeDialog.vue'
import { useCurrentMode, useIsArchived, useModesByPath } from '@/composables/useModes'
import { useChangesStore } from '@/stores/changes'

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
  }>(),
  { committed: true },
)
const emit = defineEmits<{
  save: [comment: string]
  'save-and-queue': [comment: string]
  discard: []
  fork: [name: string, description: string]
  'copy-to': [mode: string, comment: string]
}>()

const changes = useChangesStore()

const saveDialog = ref(false)
const discardDialog = ref(false)
const forkDialog = ref(false)
const copyDialog = ref(false)
const copyLatestDialog = ref(false)
const modes = useModesByPath(toRef(props, 'subsystem'), toRef(props, 'name'))

const currentMode = useCurrentMode(modes, toRef(props, 'mode'))
const archived = useIsArchived(currentMode)
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

type KebabItem = { title: string; icon: string; onClick: () => void }

const kebabItems = computed(() => {
  const items: KebabItem[] = [
    {
      title: 'Fork to New Mode…',
      icon: 'mdi-source-fork',
      onClick: () => (forkDialog.value = true),
    },
    {
      title: 'Copy to Existing Mode…',
      icon: 'mdi-source-pull',
      onClick: () => (copyDialog.value = true),
    },
  ]
  if (isOldVersion.value) {
    items.push({
      title: 'Copy to Latest Version…',
      icon: 'mdi-arrow-up-bold-box-outline',
      onClick: () => (copyLatestDialog.value = true),
    })
  }
  if (currentMode.value) {
    const modeId = currentMode.value.id
    items.push({
      title: archived.value ? 'Unarchive Mode' : 'Archive Mode',
      icon: archived.value ? 'mdi-archive-off-outline' : 'mdi-archive-outline',
      onClick: () => void changes.toggleArchival(modeId),
    })
  }
  return items
})

function onSaveConfirmed(comment: string) {
  if (props.canQueue) emit('save-and-queue', comment)
  else emit('save', comment)
}
</script>
