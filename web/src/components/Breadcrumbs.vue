<template>
  <v-breadcrumbs v-if="crumbs" density="compact">
    <v-breadcrumbs-item :to="crumbs.subsystemTo">{{ crumbs.subsystemLabel }}</v-breadcrumbs-item>
    <template v-for="ancestor in crumbs.ancestors" :key="ancestor.path">
      <v-breadcrumbs-divider></v-breadcrumbs-divider>
      <v-breadcrumbs-item :to="ancestor.to">{{ ancestor.title }}</v-breadcrumbs-item>
    </template>
    <v-breadcrumbs-divider></v-breadcrumbs-divider>
    <v-breadcrumbs-item disabled>{{ crumbs.currentTitle }}</v-breadcrumbs-item>
  </v-breadcrumbs>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useNavStore } from '@/stores/nav'

const nav = useNavStore()

const crumbs = computed(() => {
  const detail = nav.nodeDetail
  if (!detail) return null
  const row = nav.findRowByNodeId(detail.id)
  if (!row) return null

  const subsystemLabel =
    nav.subsystems.find((s) => s.id === detail.subsystem_id)?.display_name ?? detail.subsystem_name

  const ancestors = row.ancestors
    .map((path) => nav.findRow((r) => r.path === path))
    .filter((r) => r !== undefined)
    .map((r) => ({
      path: r.path,
      title: r.title,
      to: {
        name: 'node',
        params: { subsystem: nav.subsystemName(r.node.subsystem_id) ?? '', name: r.node.name },
      },
    }))

  return {
    subsystemLabel,
    subsystemTo: { name: 'subsystem', params: { subsystem: detail.subsystem_name } },
    ancestors,
    currentTitle: row.title,
  }
})
</script>
