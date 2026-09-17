import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useAuthStore } from '@/stores/auth'

export const readOnlyReason = 'Read-only: You do not have sufficient rights to edit this key.'

export function useReadOnly(subsystem: MaybeRefOrGetter<string>) {
  const auth = useAuthStore()
  return computed(() => !auth.canEdit(toValue(subsystem)))
}
