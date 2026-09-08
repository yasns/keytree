import { computed, onBeforeUnmount, reactive, ref, watch, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { api, unwrap } from '@/api'
import type { components } from '@/api-types'

type ChangesetOut = components['schemas']['ChangesetOut']
type StagedEditIn = components['schemas']['StagedEditIn']
type StagedEditOut = components['schemas']['StagedEditOut']

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
    changeset.value = unwrap(await api.GET('/api/changeset/'))
  }

  function stagedFor(
    subsystem: string,
    name: string,
    mode: string,
    baseVersion: number,
  ): StagedEditOut | undefined {
    return edits.value.find(
      (e) =>
        e.subsystem_name === subsystem &&
        e.node_name === name &&
        e.mode_name === mode &&
        e.base_version === baseVersion,
    )
  }

  async function stage(newEdits: StagedEditIn[]) {
    changeset.value = unwrap(await api.POST('/api/changeset/edits', { body: newEdits }))
  }

  async function discardAll() {
    unwrap(await api.DELETE('/api/changeset/'))
    changeset.value = null
  }

  return {
    visibleEdits,
    load,
    stagedFor,
    stage,
    discardAll,
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
