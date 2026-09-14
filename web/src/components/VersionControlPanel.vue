<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <div class="px-2 mt-2 text-right">
      <v-btn
        variant="outlined"
        color="error"
        prepend-icon="mdi-trash-can-outline"
        :disabled="!changes.pendingCount"
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
      @confirm="discardAll"
    ></ConfirmDialog>

    <div
      v-if="!changes.pendingCount"
      class="d-flex flex-grow-1 align-center justify-center text-medium-emphasis px-4 mt-2"
      style="min-height: 0"
    >
      No pending changes.
    </div>

    <div v-else class="overflow-y-auto flex-grow-1 mt-2" style="min-height: 0">
      <v-list density="compact" class="py-0">
        <v-list-item
          v-for="edit in changes.visibleEdits"
          :key="edit.id"
          slim
          @click="goToEdit(edit)"
        >
          <template #prepend>
            <v-icon :icon="keyIcon(edit)" size="small"></v-icon>
          </template>
          <v-list-item-title class="text-body-medium">
            <code>
              {{ edit.subsystem_name }}/{{ edit.node_name }}/{{ edit.mode_name }}/<template
                v-if="edit.base_version !== null"
              >
                <s class="text-medium-emphasis">v{{ edit.base_version }}</s>
                <v-icon icon="mdi-arrow-right" size="x-small"></v-icon> </template
              >v{{ edit.expected_version }}
            </code>
          </v-list-item-title>
          <v-list-item-subtitle class="text-truncate">{{ edit.comment }}</v-list-item-subtitle>
        </v-list-item>
        <v-list-item
          v-for="archival in changes.archivals"
          :key="`archival-${archival.mode_id}`"
          slim
          @click="goToArchival(archival)"
        >
          <template #prepend>
            <v-icon
              :icon="archival.archived ? 'mdi-archive-outline' : 'mdi-archive-off-outline'"
              size="small"
            ></v-icon>
          </template>
          <v-list-item-title class="text-body-medium">
            <code :class="{ 'text-decoration-line-through': archival.archived }"
              >{{ archival.subsystem_name }}/{{ archival.node_name }}/{{ archival.mode_name }}</code
            >
          </v-list-item-title>
          <v-list-item-subtitle>
            {{ archival.archived ? 'Archive mode' : 'Unarchive mode' }}
          </v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </div>

    <CommitConflictsDialog
      v-model="conflictsOpen"
      :conflicts="conflicts"
      :rebasing="rebasing"
      :committing="committing"
      @rebase="rebase"
      @overwrite="commit(true)"
    ></CommitConflictsDialog>

    <div class="px-2 py-2 border-t-sm">
      <v-textarea
        v-model="comment"
        label="Changeset comment"
        rows="2"
        maxlength="255"
        density="compact"
        hide-details
        :disabled="!changes.pendingCount"
      ></v-textarea>
      <v-btn
        block
        class="mt-2"
        color="primary"
        prepend-icon="mdi-source-commit"
        :disabled="!changes.pendingCount || !comment.trim()"
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
import type { components } from '@/api-types'
import { keyRoute, parseVersion } from '@/router'
import { type Conflict, conflictsFrom, pendingSource, useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'
import ConfirmDialog from './ConfirmDialog.vue'
import CommitConflictsDialog from './CommitConflictsDialog.vue'

type StagedEditOut = components['schemas']['StagedEditOut']
type StagedArchivalOut = components['schemas']['StagedArchivalOut']

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

function keyIcon(edit: StagedEditOut) {
  return edit.base_version === null && edit.copied_from ? 'mdi-source-fork' : 'mdi-key-plus'
}

async function goToEdit(edit: StagedEditOut) {
  if (!(await changes.confirmDiscard())) return
  router.push(keyRoute(edit.subsystem_name, edit.node_name, edit.mode_name, 'pending'))
}

async function goToArchival(archival: StagedArchivalOut) {
  if (!(await changes.confirmDiscard())) return
  const modes = await nav.fetchModesByPath(archival.subsystem_name, archival.node_name)
  const tip = modes.find((m) => m.name === archival.mode_name)?.versions[0]
  if (tip !== undefined) {
    router.push(keyRoute(archival.subsystem_name, archival.node_name, archival.mode_name, tip))
  }
}

function routedKey() {
  const { subsystem, name, mode, version } = route.params as Record<string, string | undefined>
  const parsed = parseVersion(version)
  if (!subsystem || !name || !mode || parsed === undefined) return undefined
  return { subsystem, name, mode, version: parsed }
}

async function discardAll() {
  const key = routedKey()
  const staged = key && changes.stagedForMode(key.subsystem, key.name, key.mode)
  const source = pendingSource(staged)
  await changes.discardAll()

  if (key && source) {
    snackbar.notify(`Discarded. Back on "${source.mode_name}" v${source.version}`, 'info')
    const { at: _at, ...query } = route.query
    await router.replace({
      ...keyRoute(key.subsystem, key.name, source.mode_name, source.version),
      query,
    })
  }
  await nav.refreshKeys()
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
  // only moves if this changeset edits it; capture before commit clears the edits
  const key = routedKey()
  const staged = key && changes.stagedForMode(key.subsystem, key.name, key.mode)
  try {
    await changes.commit(comment.value.trim(), overwriteConflicts)
    comment.value = ''
    conflictsOpen.value = false
    snackbar.notify('Changeset committed', 'success')
    await nav.refreshKeys()
    // follows the version it landed on, which trails the tip, not the base
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
