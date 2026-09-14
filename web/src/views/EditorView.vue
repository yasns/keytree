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
          :category="nav.nodeDetail.category"
          :pending="isPending"
        ></PayloadEditor>
      </template>

      <Spinner v-else></Spinner>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { keyRoute, parseVersion } from '@/router'
import { type BundleRoot, useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import PayloadEditor from '@/components/PayloadEditor.vue'
import BundleBrowser from '@/components/BundleBrowser.vue'
import BrowsePanel from '@/components/BrowsePanel.vue'
import Spinner from '@/components/Spinner.vue'

const { subsystem, name, mode, version } = defineProps<{
  subsystem: string
  name: string
  mode?: string
  version?: string
}>()

const nav = useNavStore()
const changes = useChangesStore()
const router = useRouter()
const snackbar = useSnackbarStore()

const selectedMode = computed(() => nav.nodeDetail?.modes.find((m) => m.name === mode))
const requestedVersion = computed(() => parseVersion(version))

const pendingEdit = computed(() => {
  const m = selectedMode.value
  return m ? changes.stagedForMode(subsystem, name, m.name) : undefined
})

// route asks for the staged edit, or there's no committed key to fall back to
const isPending = computed(() => {
  const m = selectedMode.value
  if (m?.versions.length === 0) return true
  return requestedVersion.value === 'pending' && pendingEdit.value !== undefined
})

const selectedVersion = computed(() => {
  const m = selectedMode.value
  if (!m) return undefined
  if (isPending.value) return pendingEdit.value?.expected_version
  const requested = requestedVersion.value
  if (typeof requested === 'number' && m.versions.includes(requested)) return requested
  return m.versions[0]
})

// Redirect to 404 when the routed mode is invalid for that node
watch(
  () => [nav.nodeDetail, mode] as const,
  ([detail, mode]) => {
    if (!detail || detail.name !== name || !mode) return
    if (!detail.modes.some((m) => m.name === mode)) {
      if (changes.stagedForMode(subsystem, name, mode)) return
      nav.nodeDetail = null
      snackbar.notify(`"${mode}" is not a mode of ${name}`, 'error')
      router.replace('/404')
    }
  },
  { immediate: true },
)

// Point a missing or invalid version at the version actually being rendered
watch(selectedVersion, (v) => {
  if (v === undefined) return
  if (isPending.value) {
    if (requestedVersion.value !== 'pending')
      router.replace(keyRoute(subsystem, name, mode, 'pending'))
  } else if (requestedVersion.value !== v) {
    router.replace(keyRoute(subsystem, name, mode, v))
  }
})

// Follow a pending route once its edit commits or is discarded
watch(
  () => nav.keysToken,
  () => {
    if (!isPending.value || pendingEdit.value) return
    const tip = selectedMode.value?.versions[0]
    if (tip !== undefined) router.replace(keyRoute(subsystem, name, mode, tip))
  },
)

async function syncToRoute() {
  await nav.fetchSubsystems()
  try {
    await nav.fetchNodeByPath(subsystem, name)
  } catch (err) {
    nav.nodeDetail = null
    snackbar.notifyError(err)
    router.replace('/404')
    return
  }
  const detail = nav.nodeDetail
  if (!detail || detail.name !== name) return

  if (nav.selectedSubsystemId !== detail.subsystem_id) {
    nav.selectedSubsystemId = detail.subsystem_id
  }
  await nav.fetchTree(detail.subsystem_id)

  const row = nav.findRowByNodeId(detail.id)

  if (detail.category === 'external') {
    const parent = row && nav.findRow((r) => r.path === row.ancestors.at(-1))
    snackbar.notify(`${detail.name} is selected inside its parent key`, 'info')
    return router.replace(
      parent ? { name: 'editor', params: { subsystem, name: parent.node.name } } : '/',
    )
  }

  if (row) {
    nav.openedRow = [
      ...new Set([...nav.openedRow, ...row.ancestors, ...(row.children ? [row.path] : [])]),
    ]
    nav.activatedRow = [row.path]
  }

  // No mode in the URL: send the user home with mode picker for this node
  if (!mode) {
    nav.pendingNodeId = detail.id
    nav.activePanel = BrowsePanel
    router.replace('/')
  }
}

watch(() => [subsystem, name], syncToRoute, { immediate: true })

function sameBundleRoot(a: BundleRoot | null, b: BundleRoot): boolean {
  return (
    a !== null &&
    a.subsystem === b.subsystem &&
    a.name === b.name &&
    a.mode === b.mode &&
    a.version === b.version &&
    a.pending === b.pending
  )
}

// Keep bundleRoot in sync with the route whenever mode/version are already present in it
watch(
  [() => nav.nodeDetail, selectedMode, selectedVersion],
  ([detail, mode, version]) => {
    if (!detail || detail.category !== null || !mode || version === undefined) return
    const root: BundleRoot = {
      subsystem: detail.subsystem_name,
      name: detail.name,
      mode: mode.name,
      version,
      pending: isPending.value,
    }
    if (!sameBundleRoot(nav.bundleRoot, root)) nav.bundleRoot = root
  },
  { immediate: true },
)
</script>
