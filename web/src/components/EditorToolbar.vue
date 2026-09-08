<template>
  <v-toolbar density="compact">
    <template v-slot:prepend>
      <v-btn
        :disabled="!dirty"
        @click="discardDialog = true"
        icon="mdi-arrow-u-left-top"
        size="small"
      ></v-btn>
    </template>
    <template v-slot:append>
      <v-btn prepend-icon="mdi-check" :disabled="!dirty" @click="saveDialog = true"> Save</v-btn>
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

defineProps<{ dirty: boolean; stagedComment?: string }>()
const emit = defineEmits<{ save: [comment: string]; discard: [] }>()

const saveDialog = ref(false)
const discardDialog = ref(false)
</script>
