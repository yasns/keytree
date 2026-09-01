<template>
  <v-container fluid class="h-100">
    <EmptyState
      icon="mdi-file-tree-outline"
      :title="subsystemLabel"
      text="Select a node in the tree to view its key."
    ></EmptyState>
  </v-container>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useNavStore } from '@/stores/nav'
import EmptyState from '@/components/EmptyState.vue'

const { subsystem } = defineProps<{ subsystem: string }>()

const nav = useNavStore()

const subsystemLabel = computed(
  () => nav.subsystems.find((s) => s.name === subsystem)?.display_name ?? subsystem,
)

async function syncToRoute() {
  await nav.fetchSubsystems()
  const id = nav.subsystems.find((s) => s.name === subsystem)?.id
  if (id === undefined) return

  if (nav.selectedSubsystemId !== id) {
    nav.selectedSubsystemId = id
  }
  await nav.fetchTree(id)
  nav.openedRow = []
  nav.activatedRow = []
}

watch(() => subsystem, syncToRoute, { immediate: true })
</script>
