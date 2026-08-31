<template>
  <v-autocomplete
    v-model="nav.selectedSubsystemId"
    :items="autocompleteItems"
    item-title="title"
    item-value="id"
    label="Subsystem"
    density="comfortable"
    :menu-props="{ maxHeight: undefined }"
    v-model:menu="menuOpen"
  ></v-autocomplete>

  <v-chip-group v-if="chips.length" column class="px-2">
    <v-chip
      v-for="chip in chips"
      :key="chip.name"
      size="small"
      variant="outlined"
      @click="goToName(chip.name)"
    >
      {{ chip.label }}
    </v-chip>
  </v-chip-group>

  <v-treeview
    :items="rows"
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
import { useNavStore } from '@/stores/nav'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']
type NodeOut = components['schemas']['NodeOut']

const nav = useNavStore()

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

// Unfocus the autocomplete after menu close
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

//
// Tree
//

type Row = {
  path: string
  title: string
  icon: string
  node: NodeOut
  isAlias: boolean
  ancestors: string[] // paths of this row's parents
  children?: Row[]
}

let pendingName: string | null = null // name to jump to once the newly selected subsystem's tree has loaded

// fetch tree on subsystem selection, jump to a certain path if pending
watch(
  () => nav.selectedSubsystemId,
  async (id) => {
    if (id === null) {
      nav.tree = []
      nav.treeSubsystemId = null
      nav.openedRow = []
      nav.activatedRow = []
      return
    }
    if (id === nav.treeSubsystemId) return // skip wipe & fetch if we're already there
    nav.openedRow = []
    nav.activatedRow = []
    await nav.fetchTree(id)
    if (pendingName) {
      goToName(pendingName)
      pendingName = null
    }
  },
  { immediate: true },
)

function iconFor(node: NodeOut, isAlias: boolean): string {
  if (isAlias) return 'mdi-link-variant'
  if (node.format === null) return 'mdi-folder-outline'
  switch (node.category) {
    case 'run_settings':
      return 'mdi-tune-variant'
    case 'algo':
      return 'mdi-function-variant'
    case 'infra':
      return 'mdi-server-network'
    case 'hardware':
      return 'mdi-memory'
    case 'tcds':
      return 'mdi-clock-outline'
    default:
      return 'mdi-file-outline'
  }
}

function buildRows(nodes: NodeOut[], ancestors: string[], subsystemId: number): Row[] {
  return nodes.map((node) => {
    const path = `${ancestors.at(-1) ?? ''}/${node.alias}`
    const isAlias = node.subsystem_id !== subsystemId
    return {
      path,
      title: node.alias,
      icon: iconFor(node, isAlias),
      node,
      isAlias,
      ancestors,
      children:
        !isAlias && node.children.length
          ? buildRows(node.children, [...ancestors, path], subsystemId)
          : undefined,
    }
  })
}

const rows = computed<Row[]>(() =>
  nav.selectedSubsystemId ? buildRows(nav.tree, [], nav.selectedSubsystemId) : [],
)

function* walk(list: Row[]): Generator<Row> {
  for (const row of list) {
    yield row
    if (row.children) yield* walk(row.children)
  }
}

function findRow(predicate: (row: Row) => boolean): Row | undefined {
  for (const row of walk(rows.value)) if (predicate(row)) return row
}

// alias switches the subsystem selector and opens the tree to the real node
watch(
  () => nav.activatedRow,
  (keys) => {
    const path = keys[0]
    const row = path ? findRow((r) => r.path === path) : undefined
    if (row?.isAlias) {
      pendingName = row.node.name
      nav.selectedSubsystemId = row.node.subsystem_id
    }
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
  const names = new Set([...walk(rows.value)].filter((r) => !r.isAlias).map((r) => r.node.name))
  return Object.entries(nodeLabels)
    .filter(([name]) => names.has(name))
    .map(([name, label]) => ({ name, label }))
})

function goToName(name: string) {
  const row = findRow((r) => !r.isAlias && r.node.name === name)
  if (!row) return
  const opened = [...row.ancestors] // copy because v-treeview mutates `opened`
  if (row.children) opened.push(row.path) // reveal the target's own children too
  nav.openedRow = opened
  nav.activatedRow = [row.path]
}
</script>
