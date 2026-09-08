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

  async function checkAuth() {
    claims.value = unwrap(await api.GET('/api/user/claims'))
  }

  function logout() {
    window.location.href = '/api/auth/logout'
  }

  return { claims, username, displayName, initials, checkAuth, logout }
})
