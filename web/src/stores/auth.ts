import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', () => {
  const claims = ref<Record<string, unknown> | null>(null)

  async function checkAuth() {
    // redirect: 'manual' stops fetch from following the SSO redirect (cross-origin, would fail)
    const res = await fetch('/api/user/claims', { redirect: 'manual' })
    if (res.type === 'opaqueredirect') {
      const returnTo = encodeURIComponent(window.location.href)
      window.location.href = `/api/auth/token_request?redirect_uri=${returnTo}`
      return
    }
    claims.value = (await res.json()).claims
  }

  function logout() {
    window.location.href = '/api/auth/logout'
  }

  return { claims, checkAuth, logout }
})
