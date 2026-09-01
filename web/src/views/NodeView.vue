<template>
  <div class="d-flex flex-column h-100">
    <v-toolbar
      flat
      density="comfortable"
      class="position-sticky top-0 border-b-sm"
      style="z-index: 1"
    >
      <Breadcrumbs></Breadcrumbs>

      <v-spacer></v-spacer>

      <template v-if="nav.nodeDetail">
        <v-autocomplete
          ref="modeInput"
          :model-value="selectedMode?.name"
          :items="nav.nodeDetail.modes.map((m) => m.name)"
          label="mode"
          hide-details
          style="max-width: 340px"
          class="mr-2"
          density="compact"
          @update:model-value="onModeChange"
        ></v-autocomplete>

        <v-autocomplete
          :model-value="selectedVersion"
          :items="(selectedMode?.versions ?? []).map((v) => ({ title: `v${v}`, value: v }))"
          :disabled="!selectedMode"
          label="version"
          hide-details
          style="max-width: 120px"
          class="mr-2"
          density="compact"
          @update:model-value="onVersionChange"
        ></v-autocomplete>

        <CopyButton :text="keyLabel ?? ''" class="mr-2"></CopyButton>
      </template>
    </v-toolbar>

    <div class="flex-grow-1">
      <BundleEditor
        v-if="nav.nodeDetail?.category === null"
        :enabled="!!selectedMode"
      ></BundleEditor>
      <template v-else-if="nav.nodeDetail">
        <PayloadEditor
          v-if="selectedMode && selectedVersion !== undefined"
          :key="nav.nodeDetail.id"
          :subsystem="nav.nodeDetail.subsystem_name"
          :name="nav.nodeDetail.name"
          :mode="selectedMode.name"
          :version="selectedVersion"
        ></PayloadEditor>
        <EmptyState
          v-else
          icon="mdi-cursor-default-click-outline"
          :title="`${nav.nodeDetail.subsystem_name}/${nav.nodeDetail.name}`"
          text="Select a mode above to view this key."
        ></EmptyState>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNavStore } from '@/stores/nav'
import Breadcrumbs from '@/components/Breadcrumbs.vue'
import CopyButton from '@/components/CopyButton.vue'
import BundleEditor from '@/components/BundleEditor.vue'
import PayloadEditor from '@/components/PayloadEditor.vue'
import EmptyState from '@/components/EmptyState.vue'

const { subsystem, name, mode, version } = defineProps<{
  subsystem: string
  name: string
  mode?: string
  version?: string
}>()

const nav = useNavStore()
const route = useRoute()
const router = useRouter()
const modeInput = ref<{ focus: () => void; menu: boolean } | null>(null)

function parseVersion(v: string | undefined): number | undefined {
  if (!v || v[0] !== 'v') return undefined
  const n = Number(v.slice(1))
  return Number.isFinite(n) ? n : undefined
}

const selectedMode = computed(() => nav.nodeDetail?.modes.find((m) => m.name === mode))

const selectedVersion = computed(() => {
  const m = selectedMode.value
  if (!m) return undefined
  const requested = parseVersion(version)
  return requested !== undefined && m.versions.includes(requested) ? requested : m.versions[0]
})

const keyLabel = computed(() => {
  const detail = nav.nodeDetail
  const m = selectedMode.value
  const v = selectedVersion.value
  if (!detail || !m || v === undefined) return undefined
  return `${detail.subsystem_name}/${detail.name}/${m.name}/v${v}`
})

function onModeChange(newMode: string) {
  const v = nav.nodeDetail?.modes.find((m) => m.name === newMode)?.versions[0]
  router.push({
    name: 'node',
    params: { subsystem, name, mode: newMode, version: v !== undefined ? `v${v}` : undefined },
    hash: route.hash,
  })
}

function onVersionChange(newVersion: number) {
  router.push({
    name: 'node',
    params: { subsystem, name, mode, version: `v${newVersion}` },
    hash: route.hash,
  })
}

async function syncToRoute() {
  await nav.fetchSubsystems()
  await nav.fetchNodeByPath(subsystem, name)
  const detail = nav.nodeDetail
  if (!detail || detail.name !== name) return

  if (nav.selectedSubsystemId !== detail.subsystem_id) {
    nav.selectedSubsystemId = detail.subsystem_id
  }
  await nav.fetchTree(detail.subsystem_id)

  const row = nav.findRowByNodeId(detail.id)

  if (detail.category === 'scalar') {
    const target = row && nav.routeForRow(row)
    if (target) {
      await router.replace({
        name: 'node',
        params: { subsystem: target.subsystem, name: target.name },
        hash: target.hash,
      })
    }
    return
  }

  if (row) {
    const hashRow = route.hash
      ? row.children?.find((c) => c.title === route.hash.slice(1))
      : undefined
    const activeRow = hashRow ?? row
    nav.openedRow = activeRow.children
      ? [...activeRow.ancestors, activeRow.path]
      : [...activeRow.ancestors]
    nav.activatedRow = [activeRow.path]
  }
}

watch(() => [subsystem, name], syncToRoute, { immediate: true })

watch(
  () => [nav.nodeDetail, selectedMode.value] as const,
  async ([detail, mode]) => {
    if (!detail || mode) return
    await nextTick()
    modeInput.value?.focus()
    if (modeInput.value) modeInput.value.menu = true
  },
)
</script>
