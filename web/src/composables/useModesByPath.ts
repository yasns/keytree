import { ref, watch, type Ref } from 'vue'
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
