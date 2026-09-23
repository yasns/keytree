<template>
  <div class="d-flex h-100">
    <template v-if="nav.bundleRoot">
      <div
        v-show="!collapsed"
        ref="scroller"
        class="d-flex h-100 flex-grow-1 overflow-x-auto"
        style="min-width: 0"
      >
        <div class="h-100 border-e-sm" style="flex: 0 0 auto; width: 400px">
          <KeyColumn
            ref="rootColumnRef"
            :subsystem="nav.bundleRoot.subsystem"
            :name="nav.bundleRoot.name"
            :mode="nav.bundleRoot.mode"
            :version="nav.bundleRoot.version"
            :pending="nav.bundleRoot.pending"
            :depth="0"
            :selected-alias="nav.bundlePath[0]?.alias"
            :can-queue="false"
            @select="(child) => onSelect(0, child)"
            @close="() => onClose(0)"
          ></KeyColumn>
        </div>

        <div
          v-for="column in columns"
          :key="column.index"
          class="h-100 border-e-sm"
          style="flex: 0 0 auto; width: 400px"
        >
          <KeyColumn
            :ref="(el) => setColumnRef(column.index, el)"
            :subsystem="column.subsystem"
            :name="column.name"
            :mode="column.mode"
            :version="column.version"
            :pending="column.pending"
            :depth="column.index + 1"
            :selected-alias="nav.bundlePath[column.index + 1]?.alias"
            :can-queue="canQueueAt(column.index)"
            @select="(child) => onSelect(column.index + 1, child)"
            @close="() => onClose(column.index + 1)"
            @queue="() => rippleTo(column.index)"
          ></KeyColumn>
        </div>
      </div>

      <template v-if="leafEntry">
        <v-tooltip :text="collapsed ? 'Collapse editor' : 'Expand editor'" location="end">
          <template v-slot:activator="{ props: tooltipProps }">
            <div
              v-ripple
              v-bind="tooltipProps"
              class="collapse-strip h-100 d-flex align-center justify-center cursor-pointer elevation-5 elevation-overlay"
              style="flex: 0 0 auto; width: 2rem"
              @click="collapsed = !collapsed"
            >
              <v-icon
                :icon="collapsed ? 'mdi-arrow-collapse-right' : 'mdi-arrow-expand-left'"
                size="small"
              ></v-icon>
            </div>
          </template>
        </v-tooltip>

        <div class="h-100" style="flex: 1 1 auto; min-width: 33.3333vw">
          <KeyPayload
            :subsystem="leafEntry.subsystem"
            :name="leafEntry.name"
            :mode="leafEntry.mode"
            :version="leafEntry.version"
            :pending="leafEntry.pending"
            :format="leafEntry.format"
            :category="leafEntry.category"
            :depth="nav.bundlePath.length"
            :can-queue="canQueueAt(nav.bundlePath.length - 1)"
            @queue="() => rippleTo(nav.bundlePath.length - 1)"
          ></KeyPayload>
        </div>
      </template>
    </template>

    <div v-else class="h-100 border-e-sm" style="flex: 0 0 auto; width: 400px">
      <v-skeleton-loader type="list-item@8" class="h-100"></v-skeleton-loader>
    </div>
  </div>
</template>

<script lang="ts">
import type { components } from '@/api-types'

type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']

export function encodeBundlePath(path: KeyChildMetaOut[]): string {
  return path.map((c) => encodeURIComponent(c.alias)).join('/')
}

export function parseBundlePath(at: string | undefined): string[] {
  return at ? at.split('/').map((s) => decodeURIComponent(s)) : []
}

export function leafLocatorFor(entry: KeyChildMetaOut | undefined) {
  if (!entry || entry.category === null || entry.category === 'external') return undefined
  const locator = childLocator(entry)
  return locator && { locator, format: entry.format, category: entry.category }
}
</script>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { childLocator, useNavStore } from '@/stores/nav'
import { useAuthStore } from '@/stores/auth'
import KeyColumn from './KeyColumn.vue'
import KeyPayload from './KeyPayload.vue'

const nav = useNavStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

/** A column can queue into its parent (root when i===0, else column i-1) iff the parent is editable. */
function canQueueAt(i: number): boolean {
  const subsystem = i === 0 ? nav.bundleRoot?.subsystem : nav.bundlePath[i - 1]?.subsystem_name
  return !!subsystem && auth.canEdit(subsystem)
}

const rootColumnRef = ref<InstanceType<typeof KeyColumn>>()
const columnRefs = new Map<number, InstanceType<typeof KeyColumn>>()

function setColumnRef(index: number, el: unknown) {
  if (el) columnRefs.set(index, el as InstanceType<typeof KeyColumn>)
  else columnRefs.delete(index)
}

// A column's alias-in-parent is bundlePath[p]; its parent is the root when p===0, else loop-column p-1
function rippleTo(p: number) {
  const alias = nav.bundlePath[p]?.alias
  if (alias === undefined) return
  const parent = p === 0 ? rootColumnRef.value : columnRefs.get(p - 1)
  void parent?.updateAliasToLatest(alias)
}

// A path entry only opens a column or an editor once the key actually fills its alias
const columns = computed(() =>
  nav.bundlePath.flatMap((entry, index) => {
    const locator = entry.category === null ? childLocator(entry) : undefined
    return locator ? [{ index, ...locator }] : []
  }),
)

const leafEntry = computed(() => {
  const leaf = leafLocatorFor(nav.bundlePath.at(-1))
  return leaf && { ...leaf.locator, format: leaf.format, category: leaf.category }
})

function pushPath() {
  const query = { ...route.query } as Record<string, string>
  const at = encodeBundlePath(nav.bundlePath)
  if (at) query.at = at
  else delete query.at
  router.replace({ name: 'editor', params: route.params, query })
}

function onSelect(i: number, child: KeyChildMetaOut) {
  nav.bundlePath.splice(i, Infinity, child)
  pushPath()
}

function onClose(i: number) {
  nav.bundlePath.splice(i, Infinity)
  pushPath()
}

// Rebuild the column stack from the URL
let resolveToken = 0

watch(
  () => [nav.bundleRoot, route.query.at as string | undefined] as const,
  async ([root, at]) => {
    if (!root) return
    if (encodeBundlePath(nav.bundlePath) === (at ?? '')) return
    const token = ++resolveToken
    const path = await nav.resolveBundlePath(root, parseBundlePath(at))
    if (token !== resolveToken) return
    nav.bundlePath = path
  },
  { immediate: true },
)

const scroller = ref<HTMLDivElement>()

watch(
  () => nav.bundlePath.length,
  async () => {
    await nextTick()
    if (scroller.value) scroller.value.scrollLeft = scroller.value.scrollWidth
  },
)
</script>

<style scoped>
.collapse-strip:hover {
  background: rgba(var(--v-theme-on-surface), 0.25);
}
</style>
