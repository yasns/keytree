<template>
  <v-autocomplete
    :model-value="nav.selectedSubsystemId"
    :items="autocompleteItems"
    item-title="title"
    item-value="id"
    label="Subsystem"
    hide-details
    v-model:menu="menuOpen"
    @update:model-value="onSubsystemSelect"
  ></v-autocomplete>

  <v-chip-group v-if="chips.length" column class="px-2">
    <v-chip
      v-for="chip in chips"
      :key="chip.name"
      size="small"
      variant="outlined"
      @click="nav.goToName(chip.name)"
    >
      {{ chip.label }}
    </v-chip>
  </v-chip-group>

  <v-treeview
    :items="nav.rows"
    item-value="path"
    item-title="title"
    activatable
    slim
    density="compact"
    v-model:opened="nav.openedRow"
    v-model:activated="nav.activatedRow"
  >
    <template v-slot:prepend="{ item, isOpen }">
      <v-icon
        :icon="item.icon == 'mdi-folder-outline' && isOpen ? 'mdi-folder-open-outline' : item.icon"
        size="small"
      ></v-icon>
    </template>
  </v-treeview>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNavStore, walk } from '@/stores/nav'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']

const nav = useNavStore()
const route = useRoute()
const router = useRouter()

//
// Subsystem selector
//

// In category display order
const categoryLabels: Record<string, string> = {
  top_level: 'Top-level',
  subsystem: 'L1 Subsystems',
}

type SelectItem = { type: 'subheader'; title: string } | { title: string; id: number }

const menuOpen = ref(false)

onMounted(() => nav.fetchSubsystems())

watch(menuOpen, (open) => {
  if (!open) (document.activeElement as HTMLElement | null)?.blur()
})

const autocompleteItems = computed<SelectItem[]>(() => {
  const groups = new Map<string, Subsystem[]>()
  for (const subsystem of nav.subsystems) {
    const group = groups.get(subsystem.category)
    if (group) group.push(subsystem)
    else groups.set(subsystem.category, [subsystem])
  }

  const known = Object.keys(categoryLabels).filter((c) => groups.has(c)) // known categories in categoryLabels order
  const rest = [...groups.keys()].filter((c) => !(c in categoryLabels)) // anything the API adds later

  const items: SelectItem[] = []
  for (const category of [...known, ...rest]) {
    items.push({ type: 'subheader', title: categoryLabels[category] ?? category })
    for (const s of groups.get(category) ?? []) {
      items.push({ title: s.display_name ?? s.name, id: s.id })
    }
  }
  return items
})

function onSubsystemSelect(id: number | null) {
  nav.selectedSubsystemId = id
  if (id === null) return
  const subsystem = nav.subsystemName(id)
  if (subsystem) router.push({ name: 'subsystem', params: { subsystem } })
}

//
// Tree navigation
//

function routeModeParams(target: { subsystem: string; name: string }) {
  if (route.params.subsystem !== target.subsystem || route.params.name !== target.name) return {}
  return { mode: route.params.mode, version: route.params.version }
}

watch(
  () => nav.activatedRow,
  (keys) => {
    const row = keys[0] ? nav.findRow((r) => r.path === keys[0]) : undefined
    const target = row && nav.routeForRow(row)
    if (!target) return
    if (
      route.params.subsystem === target.subsystem &&
      route.params.name === target.name &&
      route.hash === (target.hash ?? '')
    )
      return
    router.push({
      name: 'node',
      params: { subsystem: target.subsystem, name: target.name, ...routeModeParams(target) },
      hash: target.hash,
    })
  },
)

//
// Section chips
//

// In chip display order
const nodeLabels: Record<string, string> = {
  conf: 'Configuration',
  rs: 'Run Settings',
  algo: 'Algo',
  infra: 'Infra',
  hw: 'Hardware',
  l1_menu: 'L1 Menu',
  tcds: 'TCDS',
}

const chips = computed(() => {
  const names = new Set([...walk(nav.rows)].filter((r) => !r.isAlias).map((r) => r.node.name))
  return Object.entries(nodeLabels)
    .filter(([name]) => names.has(name))
    .map(([name, label]) => ({ name, label }))
})
</script>
