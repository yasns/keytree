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

      <div
        v-if="nav.selectedSubsystemId === null"
        class="d-flex flex-grow-1 align-center justify-center text-medium-emphasis px-4"
        style="min-height: 0"
      >
        Select a subsystem to browse its keys.
      </div>

      <div v-else class="overflow-y-auto flex-grow-1" style="min-height: 0">
        <v-treeview
          :items="nav.rows"
          item-value="path"
          activatable
          slim
          density="compact"
          fluid
          indent-lines
          separate-roots
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
              density="comfortable"
              @click.stop="clearPending"
            ></v-btn>
          </template>
        </v-treeview>
      </div>
    </div>

    <div v-if="detail" class="d-flex flex-column border-t-sm" style="flex: 1 1 0; min-height: 0">
      <div class="d-flex align-center justify-space-between pa-4 ga-1">
        <span class="text-title-small">Select mode</span>

        <v-btn prepend-icon="mdi-arrow-left" variant="plain" size="small" @click="clearPending"
          >Back to Browsing</v-btn
        >
      </div>

      <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
        <v-list v-if="filteredModes.length" density="compact" class="py-0">
          <v-list-item
            v-for="mode in filteredModes"
            :key="mode.id"
            :active="isSelected(mode)"
            @click="activate(mode, defaultTarget(mode))"
          >
            <v-list-item-title class="d-flex align-center">
              {{ mode.name }}
            </v-list-item-title>
            <template v-slot:append>
              <v-menu>
                <template v-slot:activator="{ props }">
                  <v-chip
                    variant="plain"
                    append-icon="mdi-chevron-down"
                    @click.stop
                    v-bind="props"
                    density="compact"
                  >
                    v{{ selectedVersion(mode) }}
                  </v-chip>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon
                        icon="mdi-information-outline"
                        size="small"
                        class="ml-1 text-medium-emphasis"
                        v-bind="props"
                        @click.stop
                      ></v-icon>
                    </template>
                    <div class="text-label-large">{{ mode.description || 'No description.' }}</div>
                    <div>
                      Created by {{ mode.created_by_display_name }} ({{ mode.created_by }})
                      {{ relativeTime(mode.created_at) }}
                    </div>
                    <div v-if="mode.archived_at">
                      Archived by {{ mode.archived_by_display_name }} ({{ mode.archived_by }})
                      {{ relativeTime(mode.archived_at) }}
                    </div>
                  </v-tooltip>
                </template>
                <v-list density="compact">
                  <v-list-item
                    v-for="opt in versionOptions(mode)"
                    :key="opt.version"
                    :title="opt.label"
                    @click="activate(mode, opt.version)"
                  ></v-list-item>
                </v-list>
              </v-menu>
            </template>
          </v-list-item>
        </v-list>
        <p v-else class="text-medium-emphasis px-4">No {{ filter }} modes.</p>
      </div>

      <v-chip-group v-model="filter" mandatory class="px-2">
        <v-chip value="all" size="small" variant="outlined" filter>All</v-chip>
        <v-chip value="active" size="small" variant="outlined" filter>Active</v-chip>
        <v-chip value="archived" size="small" variant="outlined" filter>Archived</v-chip>
      </v-chip-group>
    </div>

    <ConfirmDialog
      v-model="aliasJumpOpen"
      :title="`Jump to ${aliasJumpTitle}?`"
      :text="`This key is edited in ${aliasJumpTitle}. Jump there?`"
      confirm-text="Jump"
      confirm-color="primary"
      @confirm="confirmAliasJump"
      @cancel="cancelAliasJump"
    ></ConfirmDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { relativeTime } from '@/format'
import { keyRoute, type VersionTarget } from '@/router'
import { useNavStore, walk, type Row } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']

const nav = useNavStore()
const router = useRouter()
const changes = useChangesStore()

const locked = computed(() => nav.pendingNodeId !== null)
const pendingPath = computed(() => nav.activatedRow[0])

function itemProps(item: Record<string, unknown>) {
  const row = item as Row
  return {
    disabled: row.node.category === 'external' || (locked.value && row.path !== pendingPath.value),
  }
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

const aliasJumpOpen = ref(false)
const aliasJumpRow = ref<Row | undefined>(undefined)
let aliasJumpPrevious: string[] = []
const aliasJumpTitle = computed(() => {
  const subsystemId = aliasJumpRow.value?.node.subsystem_id
  const target = subsystemId !== undefined ? nav.subsystemName(subsystemId) : undefined
  return target ? nav.subsystemDisplayName(target) : 'another subsystem'
})

function confirmAliasJump() {
  if (aliasJumpRow.value) nav.goToAlias(aliasJumpRow.value.node)
  aliasJumpRow.value = undefined
}

function cancelAliasJump() {
  nav.activatedRow = aliasJumpPrevious
  aliasJumpRow.value = undefined
}

watch(
  () => nav.rows,
  (rows) => {
    nav.openedRow = [...walk(rows)].filter((r) => r.children).map((r) => r.path)
  },
  { immediate: true },
)

watch(
  () => nav.activatedRow,
  (keys, oldKeys) => {
    if (!keys[0]) {
      if (locked.value) clearPending()
      return
    }
    const row = nav.findRow((r) => r.path === keys[0])
    if (!row) return
    if (row.isAlias) {
      aliasJumpRow.value = row
      aliasJumpPrevious = oldKeys ?? []
      aliasJumpOpen.value = true
      return
    }
    nav.openedRow = row.children ? [...row.ancestors, row.path] : [...row.ancestors]
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

const filter = ref<'active' | 'archived' | 'all'>('active')
const detail = ref<NodeOut | undefined>(undefined)

watch(
  () => nav.pendingNodeId,
  async (id) => {
    detail.value = id !== null ? await nav.fetchNodeDetail(id) : undefined
  },
  { immediate: true },
)

// Reload committed data after a commit
watch(
  () => nav.keysToken,
  async () => {
    if (nav.pendingNodeId !== null) detail.value = await nav.fetchNodeDetail(nav.pendingNodeId)
  },
)

const filteredModes = computed(() =>
  (detail.value?.modes ?? []).filter(
    (m) => filter.value === 'all' || (m.archived_at === null) === (filter.value === 'active'),
  ),
)

function isSelected(mode: ModeOut) {
  const root = nav.bundleRoot
  return root !== null && root.name === detail.value?.name && root.mode === mode.name
}

function pendingVersion(mode: ModeOut): number | undefined {
  const d = detail.value
  const staged = d && changes.stagedForMode(d.subsystem_name, d.name, mode.name)
  if (!staged || mode.versions.includes(staged.expected_version)) return undefined
  return staged.expected_version
}

function selectedVersion(mode: ModeOut) {
  return isSelected(mode) ? nav.bundleRoot!.version : defaultVersion(mode)
}

function defaultVersion(mode: ModeOut): number | undefined {
  return mode.versions[0] ?? pendingVersion(mode)
}

function defaultTarget(mode: ModeOut): VersionTarget | undefined {
  if (mode.versions.length) return mode.versions[0]
  return pendingVersion(mode) !== undefined ? 'pending' : undefined
}

function versionOptions(mode: ModeOut): { version: VersionTarget; label: string }[] {
  const committed = mode.versions.map((v, i) => ({
    version: v,
    label: i === 0 ? `v${v} (latest)` : `v${v}`,
  }))
  const pending = pendingVersion(mode)
  return pending === undefined
    ? committed
    : [{ version: 'pending' as const, label: `v${pending} (pending)` }, ...committed]
}

async function activate(mode: ModeOut, target: VersionTarget | undefined) {
  const d = detail.value
  if (!d || target === undefined) return
  if (!(await changes.confirmDiscard())) return

  const version = target === 'pending' ? pendingVersion(mode) : target
  if (version === undefined) return

  nav.bundleRoot = {
    subsystem: d.subsystem_name,
    name: d.name,
    mode: mode.name,
    version,
    pending: target === 'pending',
  }
  router.push(keyRoute(d.subsystem_name, d.name, mode.name, target))
}
</script>

<style scoped>
:deep(.v-treeview-item),
:deep(.v-list-item) {
  min-height: 28px;
  font-size: 0.8125rem;
}
</style>
