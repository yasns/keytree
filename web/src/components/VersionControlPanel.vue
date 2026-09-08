<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <div class="px-2 mt-2 text-right">
      <v-btn
        size="small"
        variant="flat"
        prepend-icon="mdi-cancel"
        :disabled="!changes.visibleEdits.length"
        @click="confirmDiscardAll = true"
      >
        Discard All Changes
      </v-btn>
    </div>

    <ConfirmDialog
      v-model="confirmDiscardAll"
      title="Discard all changes?"
      text="This will discard every staged edit in this changeset."
      confirm-text="Discard"
      @confirm="changes.discardAll"
    ></ConfirmDialog>

    <div class="overflow-y-auto flex-grow-1 mt-2" style="min-height: 0">
      <v-list v-if="changes.visibleEdits.length" density="compact" class="py-0">
        <v-list-item v-for="edit in changes.visibleEdits" :key="edit.id">
          <v-list-item-title class="text-body-medium">
            <code>
              {{ edit.subsystem_name }}/{{ edit.node_name }}/{{ edit.mode_name }}/v{{
                edit.base_version + 1
              }}
            </code>
          </v-list-item-title>
          <v-list-item-subtitle class="text-truncate">{{ edit.comment }}</v-list-item-subtitle>
        </v-list-item>
      </v-list>
      <p v-else class="text-medium-emphasis px-4">No pending changes.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useChangesStore } from '@/stores/changes'
import ConfirmDialog from './ConfirmDialog.vue'

const changes = useChangesStore()

const confirmDiscardAll = ref(false)
</script>
