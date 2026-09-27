<template>
  <v-dialog v-model="open" max-width="960" persistent>
    <v-card title="Conflicting changes detected">
      <v-card-text>
        <p>
          Someone else committed these keys while your changes were staged. Click a row to view it
          against the base version, or compare yours and theirs directly:
        </p>
        <v-list density="compact" class="conflict-grid">
          <span class="px-4 text-body-medium text-medium-emphasis">Yours</span>
          <span></span>
          <span class="px-4 text-body-medium text-medium-emphasis">Theirs</span>
          <template v-for="conflict in conflicts" :key="conflictKey(conflict)">
            <KeyChangeListItem
              :key-label="conflictKey(conflict)"
              :from-version="conflict.base_version"
              :to-version="conflict.expected_version"
              :subtitle="conflictSubtitle(conflict)"
              :counts="yourDiffCounts(conflict)"
              @click="emit('diff', conflict, 'yours')"
            >
              <template #prepend>
                <v-icon :icon="keyIcon(conflict)" size="small"></v-icon>
              </template>
            </KeyChangeListItem>
            <div class="d-flex align-center justify-center">
              <v-btn
                prepend-icon="mdi-compare-horizontal"
                variant="tonal"
                density="comfortable"
                text="Compare"
                @click="emit('compare', conflict)"
              ></v-btn>
            </div>
            <KeyChangeListItem
              :key-label="conflictKey(conflict)"
              :from-version="conflict.base_version"
              :to-version="conflict.tip_version"
              :subtitle="theirSubtitle(conflict)"
              :counts="theirDiffCounts(conflict)"
              @click="emit('diff', conflict, 'theirs')"
            >
              <template #prepend>
                <v-icon :icon="keyIcon(conflict)" size="small"></v-icon>
              </template>
            </KeyChangeListItem>
          </template>
        </v-list>
        <p>
          Rebase re-stages your changes onto the new versions. Rebase only if you want to reconcile
          them by hand before committing.
        </p>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn variant="tonal" :loading="rebasing" @click="emit('rebase')">Rebase only</v-btn>
        <v-btn
          variant="flat"
          color="primary"
          :loading="rebasing || committing"
          @click="emit('rebaseAndCommit')"
        >
          Rebase &amp; Commit
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import {
  childrenToIdMap,
  diffAgainstAncestor,
  diffAgainstRef,
  memoizeByRef,
  useDiffCountCache,
  type KeyRef,
} from '@/composables/useDiff'
import { type Conflict, keyIcon as stagedEditKeyIcon, useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'
import KeyChangeListItem from '../key/KeyChangeListItem.vue'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  conflicts: Conflict[]
  rebasing: boolean
  committing: boolean
}>()

const emit = defineEmits<{
  rebase: []
  rebaseAndCommit: []
  diff: [Conflict, 'yours' | 'theirs']
  compare: [Conflict]
}>()

const changes = useChangesStore()
const nav = useNavStore()

function conflictKey(conflict: Conflict) {
  return `${conflict.subsystem_name}/${conflict.vertex_name}/${conflict.mode_name}`
}

function conflictCacheKey(conflict: Conflict) {
  return `${conflictKey(conflict)}@${conflict.base_version}/${conflict.expected_version}/${conflict.tip_version}`
}

function stagedEdit(conflict: Conflict) {
  return changes.stagedForMode(conflict.subsystem_name, conflict.vertex_name, conflict.mode_name)
}

function conflictSubtitle(conflict: Conflict): string {
  return stagedEdit(conflict)?.comment ?? ''
}

function keyIcon(conflict: Conflict) {
  return stagedEditKeyIcon(stagedEdit(conflict))
}

const fetchPayload = memoizeByRef((ref: KeyRef) =>
  nav.fetchKeyPayload(ref.subsystem_name, ref.vertex_name, ref.mode_name, ref.version),
)
const fetchChildren = memoizeByRef((ref: KeyRef) =>
  nav.fetchKeyChildren(ref.subsystem_name, ref.vertex_name, ref.mode_name, ref.version),
)

const { get: theirDiffCounts } = useDiffCountCache(
  () => props.conflicts,
  conflictCacheKey,
  async (conflict) => {
    const edit = stagedEdit(conflict)
    if (!edit || conflict.base_version === null) return undefined

    const baseRef: KeyRef = {
      subsystem_name: conflict.subsystem_name,
      vertex_name: conflict.vertex_name,
      mode_name: conflict.mode_name,
      version: conflict.base_version,
    }
    const tipRef: KeyRef = { ...baseRef, version: conflict.tip_version }
    const tip = await fetchPayload(tipRef)
    if (!tip) return undefined
    const subtitle = tip.decommissioned_at ? 'Decommissioned' : tip.comment

    const tipChildrenMap =
      tip.payload === null ? childrenToIdMap(await fetchChildren(tipRef)) : null
    const counts = await diffAgainstRef(
      baseRef,
      tip.payload,
      tipChildrenMap,
      fetchPayload,
      fetchChildren,
    )
    return counts && { ...counts, subtitle }
  },
)

const { get: yourDiffCounts } = useDiffCountCache(
  () => props.conflicts,
  conflictCacheKey,
  (conflict) => diffAgainstAncestor(stagedEdit(conflict), fetchPayload, fetchChildren),
)

function theirSubtitle(conflict: Conflict): string {
  return theirDiffCounts(conflict)?.subtitle ?? ''
}
</script>

<style scoped>
.conflict-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 0 16px;
}
.conflict-grid > :deep(*:not(:nth-last-child(-n + 3)):not(:nth-child(3n + 2))) {
  border-bottom: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
