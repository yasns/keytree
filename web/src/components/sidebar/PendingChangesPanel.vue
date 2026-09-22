<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <div
      v-if="!changes.pendingCount"
      class="d-flex flex-grow-1 align-center justify-center text-medium-emphasis px-4 mt-2"
      style="min-height: 0"
    >
      No pending changes.
    </div>

    <div v-else class="overflow-y-auto flex-grow-1 mt-2" style="min-height: 0">
      <v-list density="compact" class="py-0">
        <KeyChangeListItem
          v-for="edit in changes.visibleEdits"
          :key="edit.id"
          :key-label="`${edit.subsystem_name}/${edit.vertex_name}/${edit.mode_name}`"
          :from-version="edit.base_version"
          :to-version="edit.expected_version"
          :subtitle="edit.comment"
          :counts="diffCounts(edit)"
          :error-text="edit.validation_status === 'failed' ? 'Validation failed' : undefined"
          :error-lines="errorCache.get(edit.id)"
          discardable
          @click="goToEdit(edit)"
          @discard="discardEdit(edit)"
          @load-error-detail="loadErrors(edit)"
        >
          <template #append>
            <v-btn
              class="edit-btn"
              icon
              variant="text"
              density="compact"
              @click.stop="goToPayload(edit)"
            >
              <v-icon icon="mdi-pencil" size="x-small"></v-icon>
              <v-tooltip activator="parent" location="top">Edit this key</v-tooltip>
            </v-btn>
          </template>
        </KeyChangeListItem>
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
            <span :class="{ 'text-decoration-line-through': archival.archived, 'key-label': true }"
              >{{ archival.subsystem_name }}/{{ archival.vertex_name }}/{{
                archival.mode_name
              }}</span
            >
          </v-list-item-title>
          <v-list-item-subtitle>
            {{ archival.archived ? 'Archive mode' : 'Unarchive mode' }}
          </v-list-item-subtitle>
        </v-list-item>
        <v-list-item
          v-for="decommission in changes.decommissions"
          :key="`decommission-${decommission.key_id}`"
          slim
          @click="goToDecommission(decommission)"
        >
          <template #prepend>
            <v-icon
              :icon="decommission.decommissioned ? 'mdi-key-remove' : 'mdi-key-plus'"
              size="small"
            ></v-icon>
          </template>
          <v-list-item-title class="text-body-medium">
            <span
              :class="{
                'text-decoration-line-through': decommission.decommissioned,
                'key-label': true,
              }"
              >{{ decommission.label }}</span
            >
          </v-list-item-title>
          <v-list-item-subtitle>
            {{ decommission.decommissioned ? 'Decommission key' : 'Recommission key' }}
          </v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </div>

    <ConfirmDialog
      v-model="confirmInvalidCommit"
      title="Commit with validation errors?"
      text="Some staged edits failed validation. Commit anyway?"
      confirm-text="Commit"
      @confirm="commit()"
    ></ConfirmDialog>

    <CommitConflictsDialog
      v-model="conflictsOpen"
      :conflicts="conflicts"
      :rebasing="rebasing"
      :committing="committing"
      @rebase="rebase"
      @overwrite="commit(true)"
      @diff="goToConflict"
      @compare="goToCompare"
    ></CommitConflictsDialog>

    <div class="px-2 py-2 border-t-sm d-flex ga-1">
      <v-btn
        variant="tonal"
        color="error"
        class="w-auto"
        :disabled="!changes.pendingCount"
        @click="confirmDiscardAll = true"
      >
        Discard All
      </v-btn>

      <ConfirmDialog
        v-model="confirmDiscardAll"
        title="Discard all changes?"
        text="This will discard every staged edit in this changeset."
        confirm-text="Discard"
        @confirm="discardAll"
      ></ConfirmDialog>

      <v-btn
        color="primary"
        prepend-icon="mdi-source-commit"
        class="flex-grow-1"
        :disabled="!changes.pendingCount"
        :loading="committing"
        @click="onCommitClick"
      >
        Commit
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { components } from '@/api-types'
import {
  diffAgainstAncestor,
  memoizeByRef,
  useDiffCountCache,
  type KeyRef,
} from '@/composables/useDiff'
import { validatePayload } from '@/composables/useMonaco'
import { keyRoute, parseVersion, pushDiffRoute } from '@/router'
import { type Conflict, conflictsFrom, pendingSource, useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'
import ConfirmDialog from '../dialog/ConfirmDialog.vue'
import CommitConflictsDialog from '../dialog/CommitConflictsDialog.vue'
import KeyChangeListItem from '../key/KeyChangeListItem.vue'

type StagedEditOut = components['schemas']['StagedEditOut']
type StagedArchivalOut = components['schemas']['StagedArchivalOut']
type StagedDecommissionOut = components['schemas']['StagedDecommissionOut']

const changes = useChangesStore()
const nav = useNavStore()
const snackbar = useSnackbarStore()
const route = useRoute()
const router = useRouter()

const confirmDiscardAll = ref(false)
const confirmInvalidCommit = ref(false)
const committing = ref(false)
const rebasing = ref(false)
const conflicts = ref<Conflict[]>([])
const conflictsOpen = ref(false)

const fetchPayload = memoizeByRef((ref: KeyRef) =>
  nav.fetchKeyPayload(ref.subsystem_name, ref.vertex_name, ref.mode_name, ref.version),
)
const fetchChildren = memoizeByRef((ref: KeyRef) =>
  nav.fetchKeyChildren(ref.subsystem_name, ref.vertex_name, ref.mode_name, ref.version),
)

const { get: diffCounts } = useDiffCountCache(
  () => changes.visibleEdits,
  (edit) => edit.id,
  (edit) => diffAgainstAncestor(edit, fetchPayload, fetchChildren),
)

const errorCache = reactive(new Map<number, string[]>())

async function loadErrors(edit: StagedEditOut) {
  if (edit.validation_status !== 'failed' || edit.proposed_payload === null) return
  if (errorCache.has(edit.id)) return
  errorCache.set(edit.id, await validatePayload(edit.proposed_payload, edit.category))
}

async function goToEdit(edit: StagedEditOut) {
  if (!(await changes.confirmDiscard())) return
  pushDiffRoute(router, edit.subsystem_name, edit.vertex_name, edit.mode_name, edit.base_version, {
    mode: edit.mode_name,
    version: 'pending',
  })
}

async function goToPayload(edit: StagedEditOut) {
  if (!(await changes.confirmDiscard())) return
  router.push(keyRoute(edit.subsystem_name, edit.vertex_name, edit.mode_name, 'pending'))
}

async function goToConflict(conflict: Conflict, side: 'yours' | 'theirs') {
  if (!(await changes.confirmDiscard())) return
  conflictsOpen.value = false
  const target = side === 'yours' ? 'pending' : conflict.tip_version
  pushDiffRoute(
    router,
    conflict.subsystem_name,
    conflict.vertex_name,
    conflict.mode_name,
    conflict.base_version,
    { mode: conflict.mode_name, version: target },
  )
}

async function goToCompare(conflict: Conflict) {
  if (!(await changes.confirmDiscard())) return
  conflictsOpen.value = false
  pushDiffRoute(
    router,
    conflict.subsystem_name,
    conflict.vertex_name,
    conflict.mode_name,
    conflict.tip_version,
    { mode: conflict.mode_name, version: 'pending' },
  )
}

async function goToArchival(archival: StagedArchivalOut) {
  if (!(await changes.confirmDiscard())) return
  const modes = await nav.fetchModesByPath(archival.subsystem_name, archival.vertex_name)
  const tip = modes.find((m) => m.name === archival.mode_name)?.versions[0]
  if (tip !== undefined) {
    router.push(keyRoute(archival.subsystem_name, archival.vertex_name, archival.mode_name, tip))
  }
}

async function goToDecommission(decommission: StagedDecommissionOut) {
  if (!(await changes.confirmDiscard())) return
  router.push(
    keyRoute(
      decommission.subsystem_name,
      decommission.vertex_name,
      decommission.mode_name,
      decommission.version,
    ),
  )
}

function routedKey() {
  const { subsystem, name, mode, version } = route.params as Record<string, string | undefined>
  const parsed = parseVersion(version)
  if (!subsystem || !name || !mode || parsed === undefined) return undefined
  return { subsystem, name, mode, version: parsed }
}

/** Notifies and routes back to the pre-edit source, if any. Returns whether it did. */
async function returnToSource(
  subsystem: string,
  name: string,
  source: ReturnType<typeof pendingSource>,
) {
  if (!source) return false
  snackbar.notify(`Discarded. Back on "${source.mode_name}" v${source.version}`, 'info')
  const { at: _at, ...query } = route.query
  await router.replace({ ...keyRoute(subsystem, name, source.mode_name, source.version), query })
  return true
}

async function discardAll() {
  const key = routedKey()
  const staged = key && changes.stagedForMode(key.subsystem, key.name, key.mode)
  const source = pendingSource(staged)
  await changes.discardAll()

  if (key) await returnToSource(key.subsystem, key.name, source)
  await nav.refreshKeys()
}

async function discardEdit(edit: StagedEditOut) {
  const key = routedKey()
  const onThisEdit =
    key?.subsystem === edit.subsystem_name &&
    key.name === edit.vertex_name &&
    key.mode === edit.mode_name
  const source = pendingSource(edit)
  await changes.discardEdit(edit.id)

  const returned =
    onThisEdit && (await returnToSource(edit.subsystem_name, edit.vertex_name, source))
  if (!returned) snackbar.notify('Edit discarded', 'info')
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

function onCommitClick() {
  if (changes.visibleEdits.some((e) => e.validation_status === 'failed')) {
    confirmInvalidCommit.value = true
  } else {
    void commit()
  }
}

async function commit(overwriteConflicts = false) {
  committing.value = true
  // only moves if this changeset edits it; capture before commit clears the edits
  const key = routedKey()
  const staged = key && changes.stagedForMode(key.subsystem, key.name, key.mode)
  try {
    await changes.commit(overwriteConflicts)
    conflictsOpen.value = false
    snackbar.notify('Changeset committed', 'success')
    await nav.refreshKeys()
    // follows the version it landed on, which trails the tip, not the base
    const tip = key && nav.vertexDetail?.modes.find((m) => m.name === key.mode)?.versions[0]
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
      void nav.refreshKeys()
    } else {
      snackbar.notifyError(err)
    }
  } finally {
    committing.value = false
  }
}
</script>

<style scoped>
.edit-btn {
  display: none;
}
.discardable:hover .edit-btn {
  display: inline-flex;
}
:deep(.v-list-item:not(:last-child)) {
  border-bottom: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
