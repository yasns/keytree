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
            :disabled="!dirty"
            @click="openSave(canQueue)"
            v-bind="props"
          ></v-btn>
        </template>
      </v-tooltip>
      <v-tooltip v-else text="Saved">
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-cloud-check-variant-outline"
            v-bind="props"
            :disabled="!dirty && !staged"
          ></v-btn>
        </template>
      </v-tooltip>
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
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import SaveDialog from './SaveDialog.vue'

defineProps<{ dirty: boolean; staged: boolean; stagedComment?: string; canQueue?: boolean }>()
const emit = defineEmits<{
  save: [comment: string]
  'save-and-queue': [comment: string]
  discard: []
}>()

const saveDialog = ref(false)
const discardDialog = ref(false)
const queueOnSave = ref(false)

function openSave(queue: boolean) {
  queueOnSave.value = queue
  saveDialog.value = true
}

function onSaveConfirmed(comment: string) {
  if (queueOnSave.value) emit('save-and-queue', comment)
  else emit('save', comment)
}
</script>
