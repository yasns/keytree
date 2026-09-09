<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <div class="px-2 mt-2 text-right">
      <v-btn
        variant="outlined"
        color="error"
        prepend-icon="mdi-cancel"
        :disabled="!changes.visibleEdits.length"
        @click="confirmDiscardAll = true"
      >
        Discard All
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
                edit.expected_version
              }}
            </code>
          </v-list-item-title>
          <v-list-item-subtitle class="text-truncate">{{ edit.comment }}</v-list-item-subtitle>
        </v-list-item>
      </v-list>
      <p v-else class="text-medium-emphasis px-4">No pending changes.</p>
    </div>

    <v-dialog v-model="conflictsOpen" max-width="560" persistent>
      <v-card title="Versions taken since you staged">
        <v-card-text>
          <p class="mb-3">
            Someone else committed these keys while your changes were staged. Overwrite to put your
            changes on top as new versions, or rebase them onto the new versions to review first.
          </p>
          <v-list density="compact" class="py-0">
            <v-list-item
              v-for="conflict in conflicts"
              :key="`${conflict.subsystem_name}/${conflict.node_name}/${conflict.mode_name}`"
              class="px-0"
            >
              <v-list-item-title class="text-body-medium">
                <code>
                  {{ conflict.subsystem_name }}/{{ conflict.node_name }}/{{ conflict.mode_name }}
                </code>
              </v-list-item-title>
              <v-list-item-subtitle>
                staged as v{{ conflict.expected_version }} from v{{ conflict.base_version }}, now on
                v{{ conflict.tip_version }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="conflictsOpen = false">Cancel</v-btn>
          <v-btn variant="text" :loading="rebasing" @click="rebase">Rebase</v-btn>
          <v-btn variant="flat" color="warning" :loading="committing" @click="commit(true)">
            Overwrite
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <div class="px-2 py-2 border-t-sm">
      <v-textarea
        v-model="comment"
        label="Changeset comment"
        rows="2"
        maxlength="255"
        density="compact"
        hide-details
        :disabled="!changes.visibleEdits.length"
      ></v-textarea>
      <v-btn
        block
        class="mt-2"
        color="primary"
        prepend-icon="mdi-source-commit"
        :disabled="!changes.visibleEdits.length || !comment.trim()"
        :loading="committing"
        @click="commit()"
      >
        Commit
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { keyRoute, parseVersion } from '@/router'
import { conflictsFrom, useChangesStore, type Conflict } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'
import ConfirmDialog from './ConfirmDialog.vue'

const changes = useChangesStore()
const nav = useNavStore()
const snackbar = useSnackbarStore()
const route = useRoute()
const router = useRouter()

const confirmDiscardAll = ref(false)
const comment = ref('')
const committing = ref(false)
const rebasing = ref(false)
const conflicts = ref<Conflict[]>([])
const conflictsOpen = ref(false)

function routedKey() {
  const { subsystem, name, mode, version } = route.params as Record<string, string | undefined>
  const parsed = parseVersion(version)
  if (!subsystem || !name || !mode || parsed === undefined) return undefined
  return { subsystem, name, mode, version: parsed }
}

async function rebase() {
  rebasing.value = true
  try {
    await changes.rebase()
    conflictsOpen.value = false
    snackbar.notify('Staged changes rebased onto the newer versions', 'info')
  } catch (err) {
    snackbar.notifyError(err)
  } finally {
    rebasing.value = false
  }
}

async function commit(overwriteConflicts = false) {
  if (!comment.value.trim()) return
  committing.value = true
  // The routed key only moves if this changeset edits it. Capture before commit clears the edits
  const key = routedKey()
  const staged = key && changes.stagedForMode(key.subsystem, key.name, key.mode)
  try {
    await changes.commit(comment.value.trim(), overwriteConflicts)
    comment.value = ''
    conflictsOpen.value = false
    snackbar.notify('Changeset committed', 'success')
    await nav.refreshKeys()
    // Follow the routed key onto whichever version it landed on, which trails the tip, not the base
    const tip = key && nav.nodeDetail?.modes.find((m) => m.name === key.mode)?.versions[0]
    if (key && staged && tip !== undefined && tip !== key.version) {
      await router.replace({
        ...keyRoute(key.subsystem, key.name, key.mode, tip),
        query: route.query,
      })
    }
  } catch (err) {
    const found = conflictsFrom(err)
    if (found) {
      conflicts.value = found
      conflictsOpen.value = true
    } else {
      snackbar.notifyError(err)
    }
  } finally {
    committing.value = false
  }
}
</script>
