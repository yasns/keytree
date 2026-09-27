<template>
  <div class="h-100">
    <div v-if="!locked" class="d-flex flex-column h-100">
      <div class="d-flex flex-column px-4 py-3 ga-1 border-b-sm">
        <div class="text-title-medium">Browse</div>

        <v-autocomplete
          ref="fieldRef"
          :model-value="nav.selectedSubsystemId"
          :items="autocompleteItems"
          item-title="title"
          item-value="id"
          label="Subsystem"
          density="comfortable"
          hide-details
          :menu-props="{ maxHeight: menuMaxHeight }"
          v-model:menu="nav.subsystemMenuOpen"
          @update:model-value="onSubsystemSelect"
        ></v-autocomplete>

        <v-chip-group v-if="chips.length" column class="pb-0">
          <span class="align-self-center mr-2 text-body-small">Go to:</span>
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
      </div>

      <v-empty-state
        v-if="nav.selectedSubsystemId === null"
        class="flex-grow-1"
        style="min-height: 0"
        icon="mdi-folder-key-outline"
        text="Select a subsystem to browse its keys."
      ></v-empty-state>

      <div v-else class="overflow-y-auto flex-grow-1" style="min-height: 0">
        <v-treeview
          :items="nav.rows"
          item-value="path"
          activatable
          slim
          density="compact"
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
        </v-treeview>
      </div>
    </div>

    <ModePanel></ModePanel>

    <ConfirmDialog
      v-model="aliasGoToOpen"
      :title="`Go to ${aliasGoToTitle}?`"
      :text="`This key is edited in ${aliasGoToTitle}. Go there?`"
      confirm-text="Go"
      confirm-color="primary"
      @confirm="confirmAliasGoTo"
      @cancel="cancelAliasGoTo"
    ></ConfirmDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { type Row, useNavStore, walk } from '@/stores/nav'
import { useClearPending } from '@/composables/usePendingKey'
import ConfirmDialog from '@/components/dialog/ConfirmDialog.vue'
import ModePanel from './ModePanel.vue'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']

const nav = useNavStore()
const { clearPending } = useClearPending()

const locked = computed(() => nav.pendingNamespaceId !== null)

const fieldRef = ref<{ $el: HTMLElement } | null>(null)
const menuMaxHeight = ref(320)

function updateMenuMaxHeight() {
  const rect = fieldRef.value?.$el.getBoundingClientRect()
  if (rect) menuMaxHeight.value = Math.max(100, window.innerHeight - rect.bottom - 8)
}

function itemProps(item: Record<string, unknown>) {
  return { disabled: (item as Row).namespace.category === 'external' }
}

// In category display order
const categoryLabels: Record<string, string> = {
  top_level: 'Top-level',
  subsystem: 'L1 Subsystems',
}

type SelectItem =
  { type: 'subheader'; title: string } | { type: 'divider' } | { title: string; id: number }

onMounted(() => nav.fetchSubsystems())

watch(
  () => nav.subsystemMenuOpen,
  (open) => {
    if (open) updateMenuMaxHeight()
    else (document.activeElement as HTMLElement | null)?.blur()
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
    if (items.length) items.push({ type: 'divider' })
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

const aliasGoToOpen = ref(false)
const aliasGoToRow = ref<Row | undefined>(undefined)
let aliasGoToPrevious: string[] = []
const aliasGoToTitle = computed(() => {
  const subsystemId = aliasGoToRow.value?.namespace.subsystem_id
  const target = subsystemId !== undefined ? nav.subsystemName(subsystemId) : undefined
  return target ? nav.subsystemDisplayName(target) : 'another subsystem'
})

function confirmAliasGoTo() {
  if (aliasGoToRow.value) nav.goToAlias(aliasGoToRow.value.namespace)
  aliasGoToRow.value = undefined
}

function cancelAliasGoTo() {
  nav.activatedRow = aliasGoToPrevious
  aliasGoToRow.value = undefined
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
      aliasGoToRow.value = row
      aliasGoToPrevious = oldKeys ?? []
      aliasGoToOpen.value = true
      return
    }
    nav.pendingNamespaceId = row.namespace.id
  },
)

// In chip display order
const namespaceLabels: Record<string, string> = {
  conf: 'Configuration',
  rs: 'Run Settings',
  algo: 'Algo',
  infra: 'Infra',
  hw: 'Hardware',
  l1_menu: 'L1 Menu',
  tcds: 'TCDS',
}

const chips = computed(() => {
  const names = new Set([...walk(nav.rows)].filter((r) => !r.isAlias).map((r) => r.namespace.name))
  return Object.entries(namespaceLabels)
    .filter(([name]) => names.has(name))
    .map(([name, label]) => ({ name, label }))
})
</script>

<style scoped>
:deep(.v-treeview-item) {
  min-height: 28px;
  font-size: 0.8125rem;
}
</style>
