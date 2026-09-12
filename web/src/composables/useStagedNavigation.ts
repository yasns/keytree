import { useRouter } from 'vue-router'
import { keyRoute } from '@/router'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'

/** Navigates to the version a mode's staged edit will produce, for a mode with no key yet. */
export function useStagedNavigation() {
  const nav = useNavStore()
  const snackbar = useSnackbarStore()
  const router = useRouter()

  async function navigateToStaged(subsystem: string, name: string, mode: string, message?: string) {
    await nav.refreshKeys()
    if (message) snackbar.notify(message, 'success')
    router.push(keyRoute(subsystem, name, mode, 'pending'))
  }

  return { navigateToStaged }
}
