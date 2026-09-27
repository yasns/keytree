<template>
  <div class="d-flex flex-column h-100">
    <div class="d-flex flex-column flex-grow-1" style="min-width: 0; min-height: 0">
      <div
        v-if="detailReady && nav.vertexDetail?.category === null && diffTarget && bundleDiffRoot"
        class="d-flex flex-column h-100"
        style="min-height: 0"
      >
        <DiffToolbar :diff-target="diffTarget"></DiffToolbar>
        <DiffBrowser :diff-target="diffTarget"></DiffBrowser>
      </div>

      <KeyBrowser v-else-if="detailReady && nav.vertexDetail?.category === null"></KeyBrowser>

      <div
        v-else-if="detailReady && nav.vertexDetail && leafLeft && diffTarget && leafRight"
        class="d-flex flex-column h-100"
        style="min-height: 0"
      >
        <DiffToolbar :diff-target="diffTarget"></DiffToolbar>
        <DiffPayload :left="leafLeft" :right="leafRight"></DiffPayload>
      </div>

      <template
        v-else-if="detailReady && nav.vertexDetail && selectedMode && selectedVersion !== undefined"
      >
        <KeyPayload
          :key="nav.vertexDetail.id"
          :subsystem="nav.vertexDetail.subsystem_name"
          :name="nav.vertexDetail.name"
          :mode="selectedMode.name"
          :version="selectedVersion"
          :format="nav.vertexDetail.format"
          :category="nav.vertexDetail.category"
          :pending="isPending"
          :depth="0"
          :search-query="(route.query.q as string) || undefined"
          :search-regex="route.query.regex === '1'"
          :reveal-first-problem="route.query.problem === '1'"
        ></KeyPayload>
      </template>

      <Spinner v-else></Spinner>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { keyRoute, parseDiffTarget, parseVersion, resolveDiffRoot } from '@/router'
import { type BundleRoot, useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import KeyPayload from '@/components/key/KeyPayload.vue'
import KeyBrowser from '@/components/key/KeyBrowser.vue'
import DiffBrowser from '@/components/diff/DiffBrowser.vue'
import DiffToolbar from '@/components/diff/DiffToolbar.vue'
import DiffPayload, { type LeafSide } from '@/components/diff/DiffPayload.vue'
import BrowsePanel from '@/components/sidebar/BrowsePanel.vue'
import Spinner from '@/components/Spinner.vue'

const { subsystem, name, mode, version } = defineProps<{
  subsystem: string
  name: string
  mode?: string
  version?: string
}>()

const nav = useNavStore()
const changes = useChangesStore()
const route = useRoute()
const router = useRouter()
const snackbar = useSnackbarStore()

const detailReady = computed(
  () =>
    nav.vertexDetail?.subsystem_name === subsystem &&
    nav.vertexDetail?.name === name &&
    nav.vertexDetail?.category !== 'external',
)

const selectedMode = computed(() =>
  detailReady.value ? nav.vertexDetail!.modes.find((m) => m.name === mode) : undefined,
)
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

const diffTarget = computed(() => parseDiffTarget(route.query.diff as string | undefined))

const bundleDiffRoot = computed<BundleRoot | undefined>(() => {
  const root = nav.bundleRoot
  const target = diffTarget.value
  if (!root || !target) return undefined
  return resolveDiffRoot(
    { subsystem: root.subsystem, name: root.name },
    target,
    (mode) => changes.stagedForMode(root.subsystem, root.name, mode)?.expected_version,
  )
})

/** The routed leaf itself, as the "original" side of a comparison. */
const leafLeft = computed<LeafSide | undefined>(() => {
  const detail = nav.vertexDetail
  if (!detailReady.value || !detail || !selectedMode.value || selectedVersion.value === undefined)
    return undefined
  return {
    root: {
      subsystem: detail.subsystem_name,
      name: detail.name,
      mode: selectedMode.value.name,
      version: selectedVersion.value,
      pending: isPending.value,
    },
    format: detail.format,
    category: detail.category,
  }
})

const leafRight = computed<LeafSide | undefined>(() => {
  const detail = nav.vertexDetail
  const target = diffTarget.value
  if (!detailReady.value || !detail || !target) return undefined
  const root = resolveDiffRoot(
    { subsystem: detail.subsystem_name, name: detail.name },
    target,
    (mode) => changes.stagedForMode(detail.subsystem_name, detail.name, mode)?.expected_version,
  )
  return root && { root, format: detail.format, category: detail.category }
})

// Redirect to 404 when the routed mode is invalid for that vertex
watch(
  () => [nav.vertexDetail, mode] as const,
  ([detail, mode]) => {
    if (!detail || detail.subsystem_name !== subsystem || detail.name !== name || !mode) return
    if (detail.category === 'external') return
    if (!detail.modes.some((m) => m.name === mode)) {
      if (changes.stagedForMode(subsystem, name, mode)) return
      nav.vertexDetail = null
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
      router.replace({ ...keyRoute(subsystem, name, mode, 'pending'), query: route.query })
  } else if (requestedVersion.value !== v) {
    router.replace({ ...keyRoute(subsystem, name, mode, v), query: route.query })
  }
})

// Follow a pending route once its edit commits or is discarded
watch(
  () => nav.keysToken,
  () => {
    if (!isPending.value || pendingEdit.value) return
    const tip = selectedMode.value?.versions[0]
    if (tip !== undefined)
      router.replace({ ...keyRoute(subsystem, name, mode, tip), query: route.query })
  },
)

async function syncToRoute() {
  await nav.fetchSubsystems()
  try {
    await nav.fetchVertexByPath(subsystem, name)
  } catch (err) {
    nav.vertexDetail = null
    snackbar.notifyError(err)
    router.replace('/404')
    return
  }
  const detail = nav.vertexDetail
  if (!detail || detail.name !== name) return

  await nav.fetchTree(detail.subsystem_id)
  if (nav.selectedSubsystemId !== detail.subsystem_id) {
    nav.selectedSubsystemId = detail.subsystem_id
  }

  const row = nav.findRowByVertexId(detail.id)

  if (detail.category === 'external') {
    const parent = row && nav.findRow((r) => r.path === row.ancestors.at(-1))
    snackbar.notify(`${detail.name} is selected inside its parent key`, 'info')
    return router.replace(
      parent ? { name: 'editor', params: { subsystem, name: parent.vertex.name } } : '/',
    )
  }

  if (row) nav.activatedRow = [row.path]

  // No mode in the URL: send the user home with mode picker for this vertex
  if (!mode) {
    nav.pendingVertexId = detail.id
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
  [() => nav.vertexDetail, selectedMode, selectedVersion],
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
