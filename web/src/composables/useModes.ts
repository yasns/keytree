import { computed, ref, type Ref, watch } from 'vue'
import { useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'
import type { components } from '@/api-types'

type ModeOut = components['schemas']['ModeOut']

/** Refetches a node's modes whenever subsystem/name change. */
export function useModesByPath(
  subsystem: Ref<string | undefined>,
  name: Ref<string | undefined>,
): Ref<ModeOut[]> {
  const nav = useNavStore()
  const modes = ref<ModeOut[]>([]) as Ref<ModeOut[]>

  watch(
    [subsystem, name, () => nav.keysToken],
    ([subsystem, name]) => {
      if (!subsystem || !name) return
      nav.fetchModesByPath(subsystem, name).then((m) => (modes.value = m))
    },
    { immediate: true },
  )

  return modes
}

/** The mode matching `name` out of a `useModesByPath` list, if any. */
export function useCurrentMode(
  modes: Ref<ModeOut[]>,
  name: Ref<string | undefined>,
): Ref<ModeOut | undefined> {
  return computed(() => modes.value.find((m) => m.name === name.value))
}

export function useIsArchived(mode: Ref<ModeOut | undefined>): Ref<boolean> {
  const changes = useChangesStore()
  return computed(() => !!mode.value && changes.archived(mode.value))
}
