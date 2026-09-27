<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <div class="d-flex flex-column px-4 py-3 ga-1 border-b-sm">
      <div class="text-title-medium">Pending Changes</div>
    </div>

    <v-empty-state
      v-if="!changes.pendingCount"
      class="flex-grow-1"
      style="min-height: 0"
      icon="mdi-source-branch"
      text="No pending changes."
    ></v-empty-state>

    <div v-else class="overflow-y-auto flex-grow-1" style="min-height: 0">
      <v-list density="compact">
        <KeyChangeListItem
          v-for="edit in changes.visibleEdits"
          :key="edit.id"
          :key-label="`${edit.subsystem_name}/${edit.vertex_name}/${edit.mode_name}`"
          :from-version="edit.base_version"
          :to-version="edit.expected_version"
          :subtitle="edit.comment"
          :counts="diffCounts(edit)"
          :error-text="edit.validation_status === 'failed' ? 'Validation failed' : undefined"
          discardable
          @click="goToEdit(edit)"
          @discard="discardEdit(edit)"
          @view-problems="viewProblems(edit)"
        >
          <template #prepend>
            <v-icon :icon="keyIcon(edit)" size="small"></v-icon>
          </template>
          <template #append>
            <v-btn
              class="edit-btn"
              icon
              size="small"
              variant="text"
              density="comfortable"
              @click.stop="goToPayload(edit)"
            >
              <v-icon icon="mdi-pencil" size="small"></v-icon>
              <v-tooltip activator="parent" location="top">Edit this key</v-tooltip>
            </v-btn>
          </template>
        </KeyChangeListItem>
        <v-list-item
          v-for="archival in changes.archivals"
          :key="`archival-${archival.mode_id}`"
          slim
          class="discardable"
          @click="goToArchival(archival)"
        >
          <template #prepend>
            <v-icon
              :icon="archival.archived ? 'mdi-archive-outline' : 'mdi-archive-off-outline'"
              size="small"
            ></v-icon>
          </template>
          <v-list-item-title class="text-body-medium">
            <span
              :class="{
                'text-decoration-line-through': archival.archived,
                'key-label': true,
                'key-label-truncate': true,
              }"
              ><span class="key-label-head"
                >{{ archival.subsystem_name }}/{{ archival.vertex_name }}</span
              ><span class="key-label-tail">/{{ archival.mode_name }}</span></span
            >
          </v-list-item-title>
          <v-list-item-subtitle>
            {{ archival.archived ? 'Archive mode' : 'Unarchive mode' }}
          </v-list-item-subtitle>
          <template #append>
            <v-btn
              class="discard-btn"
              icon="mdi-close"
              size="small"
              variant="text"
              density="comfortable"
              @click.stop="discardArchival(archival)"
            >
              <v-icon icon="mdi-close"></v-icon>
              <v-tooltip activator="parent" location="top">Discard this change</v-tooltip>
            </v-btn>
          </template>
        </v-list-item>
        <v-list-item
          v-for="decommission in changes.decommissions"
          :key="`decommission-${decommission.key_id}`"
          slim
          class="discardable"
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
                'key-label-truncate': true,
              }"
              ><span class="key-label-head"
                >{{ decommission.subsystem_name }}/{{ decommission.vertex_name }}</span
              ><span class="key-label-tail"
                >/{{ decommission.mode_name }}/v{{ decommission.version }}</span
              ></span
            >
          </v-list-item-title>
          <v-list-item-subtitle>
            {{ decommission.decommissioned ? 'Decommission key' : 'Recommission key' }}
          </v-list-item-subtitle>
          <template #append>
            <v-btn
              class="discard-btn"
              icon="mdi-close"
              size="small"
              variant="text"
              density="comfortable"
              @click.stop="discardDecommission(decommission)"
            >
              <v-icon icon="mdi-close"></v-icon>
              <v-tooltip activator="parent" location="top">Discard this change</v-tooltip>
            </v-btn>
          </template>
        </v-list-item>
      </v-list>
    </div>

    <ConfirmDialog
      v-model="confirmCommit"
      :title="hasInvalidEdits ? 'Commit with validation errors?' : 'Commit changes?'"
      :text="
        hasInvalidEdits ? `Some saved edits failed validation. ${commitSummary}` : commitSummary
      "
      :confirm-text="hasInvalidEdits ? 'Accept Risk & Commit' : 'Commit'"
      :confirm-color="hasInvalidEdits ? 'error' : 'primary'"
      @confirm="commit()"
    ></ConfirmDialog>

    <CommitConflictsDialog
      v-model="conflictsOpen"
      :conflicts="conflicts"
      :rebasing="rebasing"
      :committing="committing"
      @rebase="rebaseOnly"
      @rebase-and-commit="rebaseAndCommit"
      @diff="goToConflict"
      @compare="goToCompare"
    ></CommitConflictsDialog>

    <div class="px-4 py-3 border-t-sm d-flex ga-1">
      <v-btn
        variant="tonal"
        class="w-auto"
        :disabled="!changes.pendingCount"
        @click="confirmDiscardAll = true"
      >
        Discard All
      </v-btn>

      <ConfirmDialog
        v-model="confirmDiscardAll"
        title="Discard all changes?"
        text="This will discard every saved edit in this changeset."
        confirm-text="Discard"
        @confirm="discardAll"
      ></ConfirmDialog>

      <v-btn
        variant="flat"
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
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { components } from '@/api-types'
import {
  diffAgainstAncestor,
  memoizeByRef,
  useDiffCountCache,
  type KeyRef,
} from '@/composables/useDiff'
import { formatList, pluralize } from '@/format'
import { keyRoute, parseVersion, pushDiffRoute } from '@/router'
import {
  type Conflict,
  conflictsFrom,
  keyIcon,
  pendingSource,
  useChangesStore,
} from '@/stores/changes'
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
const confirmCommit = ref(false)
const committing = ref(false)
const rebasing = ref(false)
const rawConflicts = ref<Conflict[]>([])
// Drops entries whose edit was since discarded, so callers don't have to scrub the cache themselves.
const conflicts = computed(() =>
  rawConflicts.value.filter((c) =>
    changes.visibleEdits.some(
      (e) =>
        e.subsystem_name === c.subsystem_name &&
        e.vertex_name === c.vertex_name &&
        e.mode_name === c.mode_name,
    ),
  ),
)
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

const commitSummary = computed(() => {
  const parts = [
    changes.visibleEdits.length && pluralize(changes.visibleEdits.length, 'key version'),
    changes.archivals.length && pluralize(changes.archivals.length, 'mode archival'),
    changes.decommissions.length && pluralize(changes.decommissions.length, 'key decommission'),
  ].filter((p) => typeof p === 'string')
  const subsystems = [
    ...new Set(
      [...changes.visibleEdits, ...changes.archivals, ...changes.decommissions].map((e) =>
        nav.subsystemDisplayName(e.subsystem_name),
      ),
    ),
  ].sort()
  return `Writes ${formatList(parts)} to ${formatList(subsystems)}. This cannot be undone.`
})

const hasInvalidEdits = computed(() =>
  changes.visibleEdits.some((e) => e.validation_status === 'failed'),
)

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

async function viewProblems(edit: StagedEditOut) {
  if (!(await changes.confirmDiscard())) return
  router.push({
    ...keyRoute(edit.subsystem_name, edit.vertex_name, edit.mode_name, 'pending'),
    query: { problem: '1' },
  })
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
  const count = changes.pendingCount
  await changes.discardAll()

  const returned = key && (await returnToSource(key.subsystem, key.name, source))
  if (!returned) snackbar.notify(`Discarded ${pluralize(count, 'change')}`, 'info')
  await nav.refreshKeys()
}

async function discardToggle(toggle: Promise<void>, label: string) {
  await toggle
  snackbar.notify(`Discarded ${label}`, 'info')
  await nav.refreshKeys()
}

function discardArchival(archival: StagedArchivalOut) {
  return discardToggle(
    changes.toggleArchival(archival.mode_id),
    `archival change on "${archival.vertex_name}/${archival.mode_name}"`,
  )
}

function discardDecommission(decommission: StagedDecommissionOut) {
  return discardToggle(
    changes.toggleDecommission(decommission.key_id),
    `decommission change on "${decommission.vertex_name}/${decommission.mode_name}"`,
  )
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
  if (!returned)
    snackbar.notify(`Discarded edit on "${edit.vertex_name}/${edit.mode_name}"`, 'info')
  await nav.refreshKeys()
}

async function rebase(): Promise<boolean> {
  rebasing.value = true
  try {
    await changes.rebase()
    conflictsOpen.value = false
    rawConflicts.value = []
    return true
  } catch (err) {
    snackbar.notifyError(err)
    return false
  } finally {
    rebasing.value = false
  }
}

async function rebaseOnly() {
  if (await rebase()) snackbar.notify('Saved changes re-staged onto the newer versions', 'info')
}

async function rebaseAndCommit() {
  if (!(await rebase())) return
  confirmCommit.value = true
}

function onCommitClick() {
  if (conflicts.value.length) conflictsOpen.value = true
  else confirmCommit.value = true
}

async function commit() {
  committing.value = true
  // only moves if this changeset edits it; capture before commit clears the edits
  const key = routedKey()
  const staged = key && changes.stagedForMode(key.subsystem, key.name, key.mode)
  const count = changes.pendingCount
  try {
    await changes.commit()
    conflictsOpen.value = false
    snackbar.notify(`Committed ${pluralize(count, 'change')}. Job well done.`, 'success')
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
      rawConflicts.value = found
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
.edit-btn,
.discard-btn {
  display: none;
}
.discardable:hover .edit-btn,
.discardable:hover .discard-btn {
  display: inline-flex;
}
:deep(.v-list-item:not(:last-child)) {
  border-bottom: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
