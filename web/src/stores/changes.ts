import { computed, onBeforeUnmount, reactive, ref, watch, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { api, unwrap, type ApiError } from '@/api'
import type { components } from '@/api-types'

type ChangesetOut = components['schemas']['ChangesetOut']
type StagedEditIn = components['schemas']['StagedEditIn']
type StagedEditOut = components['schemas']['StagedEditOut']
export type Conflict = components['schemas']['ConflictOut']

/** A commit rejected because someone else committed these modes since they were staged. */
export function conflictsFrom(err: unknown): Conflict[] | undefined {
  if (!err || typeof err !== 'object') return undefined
  const { status, detail } = err as ApiError
  return status === 409 && Array.isArray(detail) ? (detail as Conflict[]) : undefined
}

export const useChangesStore = defineStore('changes', () => {
  const changeset = ref<ChangesetOut | null>(null)

  const dirtySources = reactive(new Set<symbol>())
  const dirty = computed(() => dirtySources.size > 0)

  function setDirty(key: symbol, value: boolean) {
    if (value) dirtySources.add(key)
    else dirtySources.delete(key)
  }

  const confirmOpen = ref(false)
  let resolveConfirmOpen: ((leave: boolean) => void) | null = null

  function confirmDiscard(): Promise<boolean> {
    if (!dirty.value) return Promise.resolve(true)
    confirmOpen.value = true
    return new Promise((resolve) => {
      resolveConfirmOpen = (leave) => {
        if (leave) dirtySources.clear()
        resolve(leave)
      }
    })
  }

  function resolveConfirm(leave: boolean) {
    confirmOpen.value = false
    resolveConfirmOpen?.(leave)
    resolveConfirmOpen = null
  }

  const edits = computed(() => changeset.value?.edits ?? [])

  // Hide external leaf edits
  const visibleEdits = computed(() => edits.value.filter((e) => e.category !== 'external'))

  async function load() {
    changeset.value = unwrap(await api.GET('/api/staging/'))
  }

  /** Any staged edit on a node, whichever mode. This is how a null proposed child resolves to a key. */
  function stagedForNode(subsystem: string, name: string): StagedEditOut | undefined {
    return edits.value.find((e) => e.subsystem_name === subsystem && e.node_name === name)
  }

  /** A changeset holds at most one edit per mode, whatever version it was based on. */
  function stagedForMode(subsystem: string, name: string, mode: string): StagedEditOut | undefined {
    return edits.value.find(
      (e) => e.subsystem_name === subsystem && e.node_name === name && e.mode_name === mode,
    )
  }

  /** The edit on a mode, but only when it was based on the given version. */
  function stagedFor(
    subsystem: string,
    name: string,
    mode: string,
    baseVersion: number,
  ): StagedEditOut | undefined {
    const edit = stagedForMode(subsystem, name, mode)
    return edit?.base_version === baseVersion ? edit : undefined
  }

  async function stage(newEdits: StagedEditIn[]) {
    changeset.value = unwrap(await api.POST('/api/staging/', { body: newEdits }))
  }

  async function discardAll() {
    unwrap(await api.DELETE('/api/staging/'))
    changeset.value = null
  }

  async function commit(comment: string, overwriteConflicts = false) {
    unwrap(
      await api.POST('/api/commit/', {
        body: { comment, overwrite_conflicts: overwriteConflicts },
      }),
    )
    changeset.value = null
  }

  /** Moves conflicting edits onto the versions committed since, keeping their proposed content. */
  async function rebase() {
    changeset.value = unwrap(await api.POST('/api/commit/rebase'))
  }

  return {
    visibleEdits,
    load,
    stagedFor,
    stagedForNode,
    stagedForMode,
    stage,
    discardAll,
    commit,
    rebase,
    setDirty,
    confirmOpen,
    confirmDiscard,
    resolveConfirm,
  }
})

/** Registers a component's unsaved-changes flag with the changes store. */
export function useDirtySource(dirty: Ref<boolean>) {
  const changes = useChangesStore()
  const source = Symbol('dirty-source')
  watch(dirty, (value) => changes.setDirty(source, value), { immediate: true })
  onBeforeUnmount(() => changes.setDirty(source, false))
}
