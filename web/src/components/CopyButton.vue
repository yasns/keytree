<template>
  <v-btn
    :icon="copied ? 'mdi-check' : 'mdi-content-copy'"
    size="small"
    variant="text"
    density="comfortable"
    :disabled="!props.text"
    @click="copy"
  ></v-btn>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ text: string }>()

const copied = ref(false)

async function copy() {
  await navigator.clipboard.writeText(props.text)
  copied.value = true
  setTimeout(() => (copied.value = false), 3000)
}
</script>
