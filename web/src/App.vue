<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const live = ref('checking...')
const ready = ref('checking...')
const auth = useAuthStore()

async function probe(path: string) {
  try {
    const res = await fetch(path)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return JSON.stringify(await res.json())
  } catch (e) {
    return `unreachable: ${e instanceof Error ? e.message : e}`
  }
}

onMounted(async () => {
  await auth.checkAuth()
  if (!auth.claims) return

  live.value = await probe('/api/health/live')
  ready.value = await probe('/api/health/ready')
})
</script>

<template>
  <template v-if="auth.claims">
    <h1>Hello {{ auth.claims.given_name }}!</h1>
    <p><b>API live?</b> {{ live }}</p>
    <p><b>API ready?</b> {{ ready }}</p>
    <button @click="auth.logout">Logout</button>
  </template>
</template>
