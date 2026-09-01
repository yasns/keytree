import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const claims = ref<Record<string, unknown> | null>(null)

  const username = computed(() => claims.value?.cern_upn as string | undefined)
  const firstName = computed(() => claims.value?.given_name as string | undefined)
  const lastName = computed(() => claims.value?.family_name as string | undefined)
  const email = computed(() => claims.value?.email as string | undefined)
  const initials = computed(() => (firstName.value?.[0] ?? '') + (lastName.value?.[0] ?? ''))

  async function checkAuth() {
    const { data, error, response } = await api.GET('/api/user/claims', { redirect: 'manual' })
    if (response.type === 'opaqueredirect') {
      const returnTo = encodeURIComponent(window.location.href)
      window.location.href = `/api/auth/token_request?redirect_uri=${returnTo}`
      return
    }
    if (error) throw error
    claims.value = data
  }

  function logout() {
    window.location.href = '/api/auth/logout'
  }

  return { claims, username, firstName, lastName, email, initials, checkAuth, logout }
})
