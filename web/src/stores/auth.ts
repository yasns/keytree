import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, unwrap } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const claims = ref<Record<string, unknown> | null>(null)

  const username = computed(() => claims.value?.cern_upn as string | undefined)
  const displayName = computed(() => claims.value?.name as string | undefined)
  const initials = computed(() => {
    const parts = (displayName.value ?? '').trim().split(/\s+/).filter(Boolean)
    return (parts[0]?.[0] ?? '') + (parts.length > 1 ? (parts.at(-1)?.[0] ?? '') : '')
  })
  const roles = computed(() => {
    const resourceAccess = claims.value?.resource_access as
      Record<string, { roles?: string[] }> | undefined
    return resourceAccess?.keytree?.roles ?? []
  })

  const writableSubsystems = ref<string[]>([])

  function canEdit(subsystem: string): boolean {
    return writableSubsystems.value.includes(subsystem)
  }

  async function checkAuth() {
    const [claimsRes, subsystemsRes] = await Promise.all([
      api.GET('/api/user/claims'),
      api.GET('/api/user/subsystems'),
    ])
    claims.value = unwrap(claimsRes)
    writableSubsystems.value = unwrap(subsystemsRes)
  }

  function logout() {
    window.location.href = '/api/auth/logout'
  }

  return {
    claims,
    username,
    displayName,
    initials,
    roles,
    writableSubsystems,
    canEdit,
    checkAuth,
    logout,
  }
})
