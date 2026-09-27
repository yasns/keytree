import { useRouter } from 'vue-router'
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'

/** Exits the current pending key selection, discarding it after confirmation. */
export function useClearPending() {
  const nav = useNavStore()
  const changes = useChangesStore()
  const router = useRouter()

  async function clearPending() {
    if (!(await changes.confirmDiscard())) return
    nav.pendingVertexId = null
    nav.bundleRoot = null
    nav.bundlePath = []
    nav.activatedRow = []
    router.push('/')
  }

  return { clearPending }
}
