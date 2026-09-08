<template>
  <div class="d-flex flex-column h-100">
    <div class="d-flex flex-column" style="flex: 1 1 0; min-height: 0">
      <div>
        <v-autocomplete
          :model-value="nav.selectedSubsystemId"
          :items="autocompleteItems"
          item-title="title"
          item-value="id"
          label="Subsystem"
          hide-details
          :disabled="locked"
          v-model:menu="nav.subsystemMenuOpen"
          @update:model-value="onSubsystemSelect"
        ></v-autocomplete>

        <v-chip-group v-if="chips.length" column class="px-2 align-center">
          <v-chip
            v-for="chip in chips"
            :key="chip.name"
            size="small"
            variant="outlined"
            :disabled="locked"
            @click="nav.goToName(chip.name)"
          >
            {{ chip.label }}
          </v-chip>
        </v-chip-group>
      </div>

      <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
        <v-treeview
          :items="nav.rows"
          item-value="path"
          activatable
          slim
          density="compact"
          class=""
          indent-lines="default"
          :item-props="itemProps"
          v-model:opened="nav.openedRow"
          v-model:activated="nav.activatedRow"
        >
          <template v-slot:prepend="{ item, isOpen }">
            <v-icon
              :icon="
                item.icon == 'mdi-folder-key-outline' && isOpen
                  ? 'mdi-folder-open-outline'
                  : item.icon
              "
              size="small"
            ></v-icon>
          </template>

          <template v-slot:append="{ item }">
            <v-btn
              v-if="locked && item.path === pendingPath"
              icon="mdi-close"
              size="small"
              variant="text"
              density="compact"
              @click.stop="clearPending"
            ></v-btn>
          </template>
        </v-treeview>
      </div>
    </div>

    <div v-if="detail" class="d-flex flex-column border-t-sm" style="flex: 1 1 0; min-height: 0">
      <div class="d-flex align-center px-4 ga-1">
        <h5>Select mode</h5>

        <v-spacer></v-spacer>

        <v-btn prepend-icon="mdi-close" size="small" variant="flat" @click="clearPending"
          >Cancel</v-btn
        >
      </div>

      <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
        <v-list v-if="filteredModes.length" density="compact">
          <v-list-item
            v-for="mode in filteredModes"
            :key="mode.id"
            :active="isSelected(mode)"
            @click="activate(mode, mode.versions[0])"
          >
            <v-list-item-title class="d-flex align-center">
              {{ mode.name }}
              <v-tooltip location="top">
                <template v-slot:activator="{ props }">
                  <v-icon
                    icon="mdi-information-outline"
                    size="x-small"
                    class="ml-1 text-medium-emphasis"
                    v-bind="props"
                    @click.stop
                  ></v-icon>
                </template>
                <div>{{ mode.description || 'No description.' }}</div>
                <div>Created by {{ mode.created_by }} on {{ formatDate(mode.created_at) }}</div>
                <div v-if="mode.archived_at">
                  archived by {{ mode.archived_by }} on
                  {{ formatDate(mode.archived_at) }}
                </div>
              </v-tooltip>
            </v-list-item-title>
            <template v-slot:append>
              <v-menu>
                <template v-slot:activator="{ props }">
                  <v-chip
                    size="small"
                    variant="outlined"
                    append-icon="mdi-chevron-down"
                    @click.stop
                    v-bind="props"
                  >
                    v{{ mode.versions[0] }}
                  </v-chip>
                </template>
                <v-list density="compact">
                  <v-list-item
                    v-for="v in mode.versions"
                    :key="v"
                    :title="`v${v}`"
                    @click="activate(mode, v)"
                  ></v-list-item>
                </v-list>
              </v-menu>
            </template>
          </v-list-item>
        </v-list>
        <p v-else class="text-medium-emphasis px-4">No {{ filter }} modes.</p>
      </div>

      <v-chip-group v-model="filter" mandatory class="px-2">
        <v-chip value="active" size="small" variant="outlined" filter>Active</v-chip>
        <v-chip value="archived" size="small" variant="outlined" filter>Archived</v-chip>
      </v-chip-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { keyRoute } from '@/router'
import { useNavStore, walk, type Row } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']

const nav = useNavStore()
const router = useRouter()
const changes = useChangesStore()
const snackbar = useSnackbarStore()

const locked = computed(() => nav.pendingNodeId !== null)
const pendingPath = computed(() => nav.activatedRow[0])

function itemProps(item: Record<string, unknown>) {
  return { disabled: locked.value && (item as Row).path !== pendingPath.value }
}

async function clearPending() {
  if (!(await changes.confirmDiscard())) return
  nav.pendingNodeId = null
  nav.bundleRoot = null
  nav.bundlePath = []
  nav.activatedRow = []
  router.push('/')
}

// In category display order
const categoryLabels: Record<string, string> = {
  top_level: 'Top-level',
  subsystem: 'L1 Subsystems',
}

type SelectItem = { type: 'subheader'; title: string } | { title: string; id: number }

onMounted(() => nav.fetchSubsystems())

watch(
  () => nav.subsystemMenuOpen,
  (open) => {
    if (!open) (document.activeElement as HTMLElement | null)?.blur()
  },
)

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
}

watch(
  () => nav.rows,
  (rows) => {
    const root = rows.length === 1 ? rows[0] : undefined
    if (root?.children && !nav.openedRow.includes(root.path)) {
      nav.openedRow = [root.path]
    }
  },
  { immediate: true },
)

watch(
  () => nav.activatedRow,
  (keys) => {
    if (!keys[0]) {
      if (locked.value) clearPending()
      return
    }
    const row = nav.findRow((r) => r.path === keys[0])
    if (!row) return
    if (row.isAlias) {
      nav.goToAlias(row.node)
      return
    }
    if (row.node.category === 'external') {
      const parent = nav.findRow((r) => r.path === row.ancestors.at(-1))
      snackbar.notify(`${row.title} is selected inside its parent key`, 'info')
      nav.activatedRow = parent ? [parent.path] : []
      return
    }
    if (row.children && !nav.openedRow.includes(row.path)) {
      nav.openedRow = [...nav.openedRow, row.path]
    }
    nav.pendingNodeId = row.node.id
  },
)

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

type ModeOut = components['schemas']['ModeOut']
type NodeOut = components['schemas']['NodeOut']

const filter = ref<'active' | 'archived'>('active')
const detail = ref<NodeOut | undefined>(undefined)

function formatDate(iso: string) {
  return new Date(iso).toLocaleString()
}

watch(
  () => nav.pendingNodeId,
  async (id) => {
    detail.value = id !== null ? await nav.fetchNodeDetail(id) : undefined
  },
  { immediate: true },
)

const filteredModes = computed(() =>
  (detail.value?.modes ?? []).filter(
    (m) => (m.archived_at === null) === (filter.value === 'active'),
  ),
)

function isSelected(mode: ModeOut) {
  const root = nav.bundleRoot
  return root !== null && root.name === detail.value?.name && root.mode === mode.name
}

async function activate(mode: ModeOut, version: number | undefined) {
  const d = detail.value
  if (!d || version === undefined) return
  if (!(await changes.confirmDiscard())) return

  nav.bundleRoot = { subsystem: d.subsystem_name, name: d.name, mode: mode.name, version }
  router.push(keyRoute(d.subsystem_name, d.name, mode.name, version))
}
</script>
