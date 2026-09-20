<template>
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
          v-for="row in filteredModes"
          :key="row.mode.id"
          :active="isSelected(row.mode)"
          @click="activate(row.mode, defaultTarget(row.mode))"
        >
          <v-list-item-title class="d-flex align-center ga-1">
            {{ row.mode.name }}
            <v-chip
              v-if="row.archived || row.pending"
              size="small"
              density="compact"
              label
              variant="tonal"
              :color="row.pending ? 'warning' : undefined"
            >
              {{
                row.pending ? (row.archived ? 'archive pending' : 'unarchive pending') : 'archived'
              }}
            </v-chip>
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
                  v{{ selectedVersion(row.mode) }}
                </v-chip>
              </template>
              <v-list density="compact">
                <v-list-item
                  v-for="opt in versionOptions(row.mode)"
                  :key="opt.version"
                  :title="opt.label"
                  @click="activate(row.mode, opt.version)"
                ></v-list-item>
              </v-list>
            </v-menu>

            <v-menu>
              <template v-slot:activator="{ props }">
                <v-btn
                  icon="mdi-dots-vertical"
                  size="small"
                  variant="plain"
                  density="compact"
                  @click.stop
                  v-bind="props"
                ></v-btn>
              </template>
              <v-list density="compact">
                <v-list-item
                  title="Get Info"
                  prepend-icon="mdi-information-outline"
                  @click="infoMode = row.mode"
                ></v-list-item>
                <v-list-item
                  :title="row.archived ? 'Unarchive Mode' : 'Archive Mode'"
                  :prepend-icon="row.archived ? 'mdi-archive-off-outline' : 'mdi-archive-outline'"
                  @click="changes.toggleArchival(row.mode.id)"
                ></v-list-item>
              </v-list>
            </v-menu>
          </template>
        </v-list-item>
      </v-list>
      <p v-else class="text-medium-emphasis px-4">No {{ filter === 'all' ? '' : filter }} modes.</p>
    </div>

    <div v-if="pendingEditors.length" class="flex-shrink-0">
      <PendingEditorsAlert :editors="pendingEditors"></PendingEditorsAlert>
    </div>

    <div class="d-flex flex-wrap align-center ga-2">
      <v-text-field
        v-model="search"
        label="Search modes..."
        density="compact"
        hide-details
        clearable
        style="min-width: 180px"
      ></v-text-field>

      <v-chip-group v-model="filter" mandatory>
        <v-chip value="all" size="small" variant="outlined" filter>All</v-chip>
        <v-chip value="active" size="small" variant="outlined" filter>Active</v-chip>
        <v-chip value="archived" size="small" variant="outlined" filter>Archived</v-chip>
      </v-chip-group>
    </div>
  </div>

  <v-dialog :model-value="!!infoMode" @update:model-value="infoMode = undefined" width="auto">
    <v-card v-if="infoMode" :title="infoMode.name" min-width="320">
      <v-card-text class="text-caption text-body-medium">
        <div class="meta-grid">
          <span class="font-weight-medium">Subsystem:</span>
          <span>{{ detail?.subsystem_name }}</span>

          <span class="font-weight-medium">Path:</span>
          <span>{{ detail?.name }}</span>
        </div>

        <v-divider class="my-2"></v-divider>

        <div class="meta-grid">
          <span class="font-weight-medium">Created at:</span>
          <span>{{ new Date(infoMode.created_at).toLocaleString(LOCALE) }}</span>

          <span class="font-weight-medium">Created by:</span>
          <span>{{ infoMode.created_by_display_name }} ({{ infoMode.created_by }})</span>
        </div>

        <template v-if="infoMode.description">
          <div class="comment-block mt-2">
            <div class="font-weight-medium">Comment</div>
            <div class="text-body-medium">{{ infoMode.description }}</div>
          </div>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { LOCALE } from '@/format'
import { keyRoute, type VersionTarget } from '@/router'
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useClearPending } from '@/composables/usePendingNode'
import { usePendingEditors } from '@/composables/usePendingEditors'
import { goodTip, versionLabel } from '@/mode'
import type { components } from '@/api-types'
import PendingEditorsAlert from '../key/PendingEditorsAlert.vue'

type ModeOut = components['schemas']['ModeOut']
type NodeOut = components['schemas']['NodeOut']

const nav = useNavStore()
const router = useRouter()
const changes = useChangesStore()
const { clearPending } = useClearPending()

const filter = ref<'active' | 'archived' | 'all'>('active')
const search = ref('')
const detail = ref<NodeOut | undefined>(undefined)
const infoMode = ref<ModeOut | undefined>(undefined)

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
  (detail.value?.modes ?? [])
    .map((mode) => {
      const staged = changes.stagedArchival(mode.id)
      return {
        mode,
        archived: staged?.archived ?? mode.archived_at !== null,
        pending: !!staged,
      }
    })
    .filter(
      (row) =>
        (filter.value === 'all' || !row.archived === (filter.value === 'active')) &&
        row.mode.name.toLowerCase().includes((search.value ?? '').trim().toLowerCase()),
    ),
)

function isSelected(mode: ModeOut) {
  const root = nav.bundleRoot
  return root !== null && root.name === detail.value?.name && root.mode === mode.name
}

const selectedMode = computed(() => detail.value?.modes.find(isSelected))
const pendingEditors = usePendingEditors(computed(() => selectedMode.value?.id))

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
  return goodTip(mode) ?? pendingVersion(mode)
}

function defaultTarget(mode: ModeOut): VersionTarget | undefined {
  if (mode.versions.length) return goodTip(mode)
  return pendingVersion(mode) !== undefined ? 'pending' : undefined
}

function versionOptions(mode: ModeOut): { version: VersionTarget; label: string }[] {
  const committed = mode.versions.map((v, i) => ({
    version: v,
    label: versionLabel(mode, v, i === 0),
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
:deep(.v-list-item) {
  min-height: 28px;
  font-size: 0.8125rem;
}
</style>
