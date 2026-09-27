import { useRoute, useRouter } from 'vue-router'
import { keyRoute } from '@/router'
import { useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'
import type { components } from '@/api-types'

type StagedEditOut = components['schemas']['StagedEditOut']

/** Navigates to the version a mode's staged edit will produce, for a mode with no key yet. */
export function useStagedNavigation() {
  const changes = useChangesStore()
  const nav = useNavStore()
  const snackbar = useSnackbarStore()
  const router = useRouter()
  const route = useRoute()

  async function navigateToStaged(subsystem: string, name: string, mode: string, message?: string) {
    await nav.refreshKeys()
    if (message) snackbar.notify(message, 'success')
    router.push(keyRoute(subsystem, name, mode, 'pending'))
  }

  /** Keeps the open bundle path */
  function showStaged(subsystem: string, name: string, mode: string) {
    void router.replace({ ...keyRoute(subsystem, name, mode, 'pending'), query: route.query })
  }

  /** Falls back off the pending route */
  function backToVersion(subsystem: string, name: string, mode: string, version: number) {
    void router.replace({ ...keyRoute(subsystem, name, mode, version), query: route.query })
  }

  /** Where a save lands: on its own pending route when no ancestor can carry it, else recorded in the open bundle path. */
  function routeStaged(
    subsystem: string,
    name: string,
    mode: string,
    edit: StagedEditOut | undefined,
    depth: number,
    canQueue?: boolean,
  ) {
    if (!canQueue) {
      if (depth === 0) showStaged(subsystem, name, mode)
      return
    }
    if (edit) nav.markPathStaged(depth - 1, edit.expected_version)
  }

  /** What a save actually staged; `left` marks a no-op re-stage that fell back off the pending route. */
  function afterStage(
    subsystem: string,
    name: string,
    mode: string,
    version: number,
    pending: boolean,
  ): { edit: StagedEditOut | undefined; left: boolean } {
    const edit = changes.stagedForMode(subsystem, name, mode)
    const left = pending && !edit
    if (left) backToVersion(subsystem, name, mode, version)
    else snackbar.notify(`Saved "${mode}"`, 'success')
    return { edit, left }
  }

  return { navigateToStaged, routeStaged, afterStage }
}
