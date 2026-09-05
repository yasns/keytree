<template>
  <div class="d-flex flex-column h-100">
    <div class="flex-grow-1" style="min-width: 0; min-height: 0">
      <BundleBrowser v-if="nav.nodeDetail?.category === null"></BundleBrowser>

      <template v-else-if="nav.nodeDetail && selectedMode && selectedVersion !== undefined">
        <PayloadEditor
          :key="nav.nodeDetail.id"
          :subsystem="nav.nodeDetail.subsystem_name"
          :name="nav.nodeDetail.name"
          :mode="selectedMode.name"
          :version="selectedVersion"
        ></PayloadEditor>
      </template>

      <Spinner v-else></Spinner>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { keyRoute } from '@/router'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'
import PayloadEditor from '@/components/PayloadEditor.vue'
import BundleBrowser from '@/components/BundleBrowser.vue'

const { subsystem, name, mode, version } = defineProps<{
  subsystem: string
  name: string
  mode?: string
  version?: string
}>()

const nav = useNavStore()
const router = useRouter()
const snackbar = useSnackbarStore()

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

// Point invalid URL at the version actually being rendered
watch(selectedVersion, (v) => {
  const requested = parseVersion(version)
  if (v !== undefined && requested !== undefined && requested !== v) {
    router.replace(keyRoute(subsystem, name, mode, v))
  }
})

//
// Route
//

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
    const parent = row && nav.findRow((r) => r.path === row.ancestors.at(-1))
    snackbar.notify(`${detail.name} is selected inside its parent key`, 'info')
    return router.replace(
      parent ? { name: 'editor', params: { subsystem, name: parent.node.name } } : '/',
    )
  }

  if (row) {
    nav.openedRow = row.children ? [...row.ancestors, row.path] : [...row.ancestors]
    nav.activatedRow = [row.path]
  }

  // Bypass mode selection if mode/version are already in the route
  if (detail.category === null && selectedMode.value && selectedVersion.value !== undefined) {
    nav.bundleRoot = {
      subsystem: detail.subsystem_name,
      name: detail.name,
      mode: selectedMode.value.name,
      version: selectedVersion.value,
    }
  }
}

watch(() => [subsystem, name], syncToRoute, { immediate: true })
</script>
