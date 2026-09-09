<template>
  <v-toolbar density="compact">
    <template v-slot:prepend>
      <v-btn
        :disabled="!dirty"
        @click="discardDialog = true"
        prepend-icon="mdi-cancel"
        color="error"
        >Discard</v-btn
      >
    </template>

    <template v-slot:append>
      <v-btn prepend-icon="mdi-content-save" :disabled="!dirty" @click="saveDialog = true">
        Save</v-btn
      >

      <v-tooltip v-if="dirty" text="Unsaved changes">
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-cloud-alert-outline"
            color="warning"
            density="comfortable"
            :disabled="!dirty"
            @click="saveDialog = true"
            v-bind="props"
          ></v-btn>
        </template>
      </v-tooltip>
      <v-tooltip v-else-if="staged" activator="parent" text="Saved">
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-cloud-check-variant"
            density="comfortable"
            v-bind="props"
            :disabled="dirty"
          ></v-btn>
        </template>
      </v-tooltip>
    </template>
  </v-toolbar>

  <SaveDialog
    v-model="saveDialog"
    :initial-comment="stagedComment"
    @save="(comment) => emit('save', comment)"
  ></SaveDialog>

  <ConfirmDialog
    v-model="discardDialog"
    title="Discard changes?"
    text="This key has not been saved. Discard it?"
    confirm-text="Discard"
    @confirm="emit('discard')"
  ></ConfirmDialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import SaveDialog from './SaveDialog.vue'

defineProps<{ dirty: boolean; staged: boolean; stagedComment?: string }>()
const emit = defineEmits<{ save: [comment: string]; discard: [] }>()

const saveDialog = ref(false)
const discardDialog = ref(false)
</script>
