import { computed, toValue, type MaybeRefOrGetter, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useChangesStore } from '@/stores/changes'

export const readOnlyReason = 'Read-only: You do not have sufficient rights to edit this key.'
export const decommissionedReadOnlyReason =
  'Read-only: This key is decommissioned. Recommission it, or copy its content elsewhere.'
export const archivedReadOnlyReason =
  'Read-only: This mode is archived. Unarchive it, or copy its content elsewhere.'

export function useReadOnly(subsystem: MaybeRefOrGetter<string>) {
  const auth = useAuthStore()
  return computed(() => !auth.canEdit(toValue(subsystem)))
}

/** Blocks building a new version on top of a decommissioned key; forking/copying it elsewhere stays allowed. */
export function useIsDecommissioned(
  key: Ref<{ id: number; decommissioned_at: string | null } | undefined>,
) {
  const changes = useChangesStore()
  return computed(() => !!key.value && changes.decommissioned(key.value))
}

/** `archived` gates the mode currently shown in this editor, not a referenced child's mode. */
export function useKeyReadOnly(
  subsystem: MaybeRefOrGetter<string>,
  key: Ref<{ id: number; decommissioned_at: string | null } | undefined>,
  archived: Ref<boolean>,
) {
  const authReadOnly = useReadOnly(subsystem)
  const decommissioned = useIsDecommissioned(key)
  return {
    readOnly: computed(() => authReadOnly.value || decommissioned.value || archived.value),
    readOnlyText: computed(() => {
      if (decommissioned.value) return decommissionedReadOnlyReason
      if (archived.value) return archivedReadOnlyReason
      return readOnlyReason
    }),
  }
}
