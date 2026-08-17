<script setup lang="ts">
import { ref, onMounted } from 'vue'

const health = ref('checking…')

onMounted(async () => {
  try {
    const res = await fetch('/api/health')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    health.value = data
  } catch (e) {
    health.value = `unreachable: ${e instanceof Error ? e.message : e}`
  }
})
</script>

<template>
  <h1>Hello World!</h1>
  <p>API health: {{ health }}</p>
</template>
