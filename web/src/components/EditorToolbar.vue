<template>
  <v-toolbar density="comfortable">
    <template v-slot:prepend>
      <v-tooltip text="Discard changes">
        <template v-slot:activator="{ props }">
          <v-btn
            :disabled="!dirty"
            @click="discardDialog = true"
            icon="mdi-trash-can-outline"
            v-bind="props"
          ></v-btn>
        </template>
      </v-tooltip>
    </template>

    <template v-slot:append>
      <template v-if="canQueue">
        <v-tooltip v-if="dirty" text="Save">
          <template v-slot:activator="{ props }">
            <v-btn
              icon="mdi-check"
              :disabled="!dirty"
              @click="openSave(false)"
              v-bind="props"
            ></v-btn>
          </template>
        </v-tooltip>

        <v-btn
          prepend-icon="mdi-database-arrow-left"
          :disabled="!dirty"
          @click="openSave(true)"
          variant="tonal"
          rounded
        >
          Save & Queue
        </v-btn>
      </template>

      <v-btn
        v-else
        prepend-icon="mdi-check"
        :disabled="!dirty"
        @click="openSave(false)"
        variant="tonal"
        rounded
      >
        Save
      </v-btn>

      <v-divider vertical inset class="mx-1"></v-divider>

      <v-tooltip v-if="dirty" text="Unsaved">
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-cloud-alert-outline"
            color="warning"
            @click="openSave(canQueue)"
            v-bind="props"
          ></v-btn>
        </template>
      </v-tooltip>
      <v-tooltip v-else text="Saved">
        <template v-slot:activator="{ props }">
          <v-btn icon="mdi-cloud-check-variant-outline" v-bind="props"></v-btn>
        </template>
      </v-tooltip>

      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn icon="mdi-dots-vertical" v-bind="props"></v-btn>
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
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import SaveDialog from './SaveDialog.vue'
import ForkModeDialog from './ForkModeDialog.vue'
import CopyToModeDialog from './CopyToModeDialog.vue'
import { useModesByPath } from '@/composables/useModesByPath'

const props = withDefaults(
  defineProps<{
    dirty: boolean
    staged: boolean
    stagedComment?: string
    canQueue?: boolean
    subsystem?: string
    name?: string
    mode?: string
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

const saveDialog = ref(false)
const discardDialog = ref(false)
const forkDialog = ref(false)
const copyDialog = ref(false)
const queueOnSave = ref(false)
const modes = useModesByPath(toRef(props, 'subsystem'), toRef(props, 'name'))

const kebabItems = [
  { title: 'Fork to New Mode…', icon: 'mdi-source-fork', onClick: () => (forkDialog.value = true) },
  {
    title: 'Copy to Existing Mode…',
    icon: 'mdi-source-pull',
    onClick: () => (copyDialog.value = true),
  },
]

function openSave(queue: boolean) {
  queueOnSave.value = queue
  saveDialog.value = true
}

function onSaveConfirmed(comment: string) {
  if (queueOnSave.value) emit('save-and-queue', comment)
  else emit('save', comment)
}
</script>
