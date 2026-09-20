import { computed, ref, shallowRef, type Ref, watch } from 'vue'
import { api, unwrap } from '@/api'
import type { components } from '@/api-types'

type PendingEditorOut = components['schemas']['PendingEditorOut']

const POLL_MS = 30_000

type Entry = {
  editors: Ref<PendingEditorOut[]>
  refcount: number
  timer: ReturnType<typeof setInterval>
}
// ponytail: module-level cache so concurrent viewers of the same mode share one poll instead of one each
const cache = new Map<number, Entry>()

function subscribe(id: number): Entry {
  let entry = cache.get(id)
  if (!entry) {
    const refresh = async () => {
      const result = unwrap(
        await api.GET('/api/staging/{mode_id}/pending-editors', {
          params: { path: { mode_id: id } },
        }),
      )
      if (cache.get(id) === entry) entry!.editors.value = result
    }
    entry = {
      editors: ref([]) as Ref<PendingEditorOut[]>,
      refcount: 0,
      timer: setInterval(refresh, POLL_MS),
    }
    cache.set(id, entry)
    refresh()
  }
  entry.refcount++
  return entry
}

function unsubscribe(id: number, entry: Entry) {
  entry.refcount--
  if (entry.refcount <= 0) {
    clearInterval(entry.timer)
    if (cache.get(id) === entry) cache.delete(id)
  }
}

/** Other users with unsaved staged edits on this mode. Polls while mounted; shares one poll per mode across callers. */
export function usePendingEditors(modeId: Ref<number | undefined>): Ref<PendingEditorOut[]> {
  const subEntry = shallowRef<Entry>()

  watch(
    modeId,
    (id, _old, onCleanup) => {
      if (id === undefined) {
        subEntry.value = undefined
        return
      }
      const entry = subscribe(id)
      subEntry.value = entry
      onCleanup(() => unsubscribe(id, entry))
    },
    { immediate: true },
  )

  return computed(() => subEntry.value?.editors.value ?? [])
}
