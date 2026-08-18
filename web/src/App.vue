<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const health = ref('checking...')
const auth = useAuthStore()

onMounted(async () => {
  await auth.checkAuth()
  if (!auth.claims) return

  try {
    const res = await fetch('/api/health')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    health.value = await res.json()
  } catch (e) {
    health.value = `unreachable: ${e instanceof Error ? e.message : e}`
  }
})
</script>

<template>
  <template v-if="auth.claims">
    <h1>Hello {{ auth.claims.given_name }}!</h1>
    <p>API health: {{ health }}</p>
    <button @click="auth.logout">Logout</button>
  </template>
</template>
