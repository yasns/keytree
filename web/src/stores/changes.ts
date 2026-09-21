import { computed, onBeforeUnmount, reactive, ref, type Ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { api, type ApiError, unwrap } from '@/api'
import type { components } from '@/api-types'

type ChangesetOut = components['schemas']['ChangesetOut']
type StagedEditIn = components['schemas']['StagedEditIn']
type StagedEditOut = components['schemas']['StagedEditOut']
type StagedArchivalOut = components['schemas']['StagedArchivalOut']
type StagedDecommissionOut = components['schemas']['StagedDecommissionOut']
type ForkIn = components['schemas']['ForkIn']
type CopyIn = components['schemas']['CopyIn']
export type Conflict = components['schemas']['ConflictOut']

/** Commit rejected: someone else committed these modes since staging. */
export function conflictsFrom(err: unknown): Conflict[] | undefined {
  if (!err || typeof err !== 'object') return undefined
  const { status, detail } = err as ApiError
  return status === 409 && Array.isArray(detail) ? (detail as Conflict[]) : undefined
}

/** Fork/copy source, until it has a key of its own. */
export function pendingSource(edit: StagedEditOut | undefined) {
  return edit?.base_version === null ? edit.copied_from : null
}

export const useChangesStore = defineStore('changes', () => {
  const changeset = ref<ChangesetOut | null>(null)

  // depth per dirty source, so a column can check whether anything deeper is dirty
  const dirtyDepths = reactive(new Map<symbol, number>())

  function setDirty(key: symbol, value: boolean, depth: number) {
    if (value) dirtyDepths.set(key, depth)
    else dirtyDepths.delete(key)
  }

  function dirtyBeyond(depth: number): boolean {
    for (const d of dirtyDepths.values()) if (d > depth) return true
    return false
  }

  const confirmOpen = ref(false)
  let resolveConfirmOpen: ((leave: boolean) => void) | null = null

  /** Default `depth`: any depth, i.e. anything dirty at all. */
  function confirmDiscardBeyond(depth: number = -Infinity): Promise<boolean> {
    if (!dirtyBeyond(depth)) return Promise.resolve(true)
    confirmOpen.value = true
    return new Promise((resolve) => {
      resolveConfirmOpen = (leave) => {
        if (leave) {
          for (const [key, d] of dirtyDepths) if (d > depth) dirtyDepths.delete(key)
        }
        resolve(leave)
      }
    })
  }

  const confirmDiscard = () => confirmDiscardBeyond()

  function resolveConfirm(leave: boolean) {
    confirmOpen.value = false
    resolveConfirmOpen?.(leave)
    resolveConfirmOpen = null
  }

  const edits = computed(() => changeset.value?.edits ?? [])
  const archivals = computed(() => changeset.value?.archivals ?? [])
  const decommissions = computed(() => changeset.value?.decommissions ?? [])

  const visibleEdits = computed(() => edits.value.filter((e) => e.visible))

  const pendingCount = computed(
    () => visibleEdits.value.length + archivals.value.length + decommissions.value.length,
  )

  async function load() {
    changeset.value = unwrap(await api.GET('/api/staging/'))
  }

  /** Any staged edit on a node, whichever mode. */
  function stagedForNode(subsystem: string, name: string): StagedEditOut | undefined {
    return edits.value.find((e) => e.subsystem_name === subsystem && e.node_name === name)
  }

  /** At most one edit per mode, whatever version it's based on. */
  function stagedForMode(subsystem: string, name: string, mode: string): StagedEditOut | undefined {
    return edits.value.find(
      (e) => e.subsystem_name === subsystem && e.node_name === name && e.mode_name === mode,
    )
  }

  /** Edit on a mode based on the given version. Forks match on their produced version instead. */
  function stagedFor(
    subsystem: string,
    name: string,
    mode: string,
    baseVersion: number,
  ): StagedEditOut | undefined {
    const edit = stagedForMode(subsystem, name, mode)
    if (!edit) return undefined
    return (edit.base_version ?? edit.expected_version) === baseVersion ? edit : undefined
  }

  /** Pending version has no committed key of its own: read the mode's changeset instead. */
  function stagedForColumn(
    subsystem: string,
    name: string,
    mode: string,
    version: number,
    pending: boolean | undefined,
  ): StagedEditOut | undefined {
    return pending
      ? stagedForMode(subsystem, name, mode)
      : stagedFor(subsystem, name, mode, version)
  }

  function stagedArchival(modeId: number): StagedArchivalOut | undefined {
    return archivals.value.find((a) => a.mode_id === modeId)
  }

  function archived(mode: { id: number; archived_at: string | null }): boolean {
    return stagedArchival(mode.id)?.archived ?? mode.archived_at !== null
  }

  async function toggleArchival(modeId: number) {
    changeset.value = unwrap(await api.POST('/api/staging/archive', { body: { mode_id: modeId } }))
  }

  function stagedDecommission(keyId: number): StagedDecommissionOut | undefined {
    return decommissions.value.find((d) => d.key_id === keyId)
  }

  function decommissioned(key: { id: number; decommissioned_at: string | null }): boolean {
    return stagedDecommission(key.id)?.decommissioned ?? key.decommissioned_at !== null
  }

  async function toggleDecommission(keyId: number) {
    changeset.value = unwrap(
      await api.POST('/api/staging/decommission', { body: { key_id: keyId } }),
    )
  }

  async function stage(newEdits: StagedEditIn[]) {
    changeset.value = unwrap(await api.POST('/api/staging/', { body: newEdits }))
  }

  async function fork(body: ForkIn) {
    changeset.value = unwrap(await api.POST('/api/staging/fork', { body }))
  }

  async function copyTo(body: CopyIn) {
    changeset.value = unwrap(await api.POST('/api/staging/copy', { body }))
  }

  async function discardAll() {
    unwrap(await api.DELETE('/api/staging/'))
    changeset.value = null
  }

  async function commit(overwriteConflicts = false) {
    unwrap(
      await api.POST('/api/commit/', {
        body: { overwrite_conflicts: overwriteConflicts },
      }),
    )
    changeset.value = null
  }

  /** Keeps proposed content; moves onto versions committed since. */
  async function rebase() {
    changeset.value = unwrap(await api.POST('/api/commit/rebase'))
  }

  return {
    visibleEdits,
    archivals,
    decommissions,
    pendingCount,
    load,
    stagedFor,
    stagedForNode,
    stagedForMode,
    stagedForColumn,
    stagedArchival,
    archived,
    toggleArchival,
    stagedDecommission,
    decommissioned,
    toggleDecommission,
    stage,
    fork,
    copyTo,
    discardAll,
    commit,
    rebase,
    setDirty,
    dirtyBeyond,
    confirmOpen,
    confirmDiscard,
    confirmDiscardBeyond,
    resolveConfirm,
  }
})

/** Tags the flag with its bundle-path depth. */
export function useDirtySource(dirty: Ref<boolean>, depth: number) {
  const changes = useChangesStore()
  const source = Symbol('dirty-source')
  watch(dirty, (value) => changes.setDirty(source, value, depth), { immediate: true })
  onBeforeUnmount(() => changes.setDirty(source, false, depth))
}
