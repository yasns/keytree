<template>
  <div class="d-flex h-100">
    <template v-if="nav.bundleRoot">
      <div
        v-show="!collapsed"
        ref="scroller"
        class="d-flex h-100 flex-grow-1"
        style="min-width: 0; overflow-x: auto"
      >
        <div class="h-100 border-e-sm" style="flex: 0 0 auto; width: 400px">
          <BundleColumn
            :subsystem="nav.bundleRoot.subsystem"
            :name="nav.bundleRoot.name"
            :mode="nav.bundleRoot.mode"
            :version="nav.bundleRoot.version"
            :selected-alias="nav.bundlePath[0]?.alias"
            @select="(child) => onSelect(0, child)"
          ></BundleColumn>
        </div>

        <div
          v-for="column in columns"
          :key="column.index"
          class="h-100 border-e-sm"
          style="flex: 0 0 auto; width: 400px"
        >
          <BundleColumn
            :subsystem="column.subsystem"
            :name="column.name"
            :mode="column.mode"
            :version="column.version"
            :selected-alias="nav.bundlePath[column.index + 1]?.alias"
            @select="(child) => onSelect(column.index + 1, child)"
          ></BundleColumn>
        </div>
      </div>

      <template v-if="leafEntry">
        <v-tooltip :text="collapsed ? 'Collapse editor' : 'Expand editor'" location="end">
          <template v-slot:activator="{ props: tooltipProps }">
            <div
              v-ripple
              v-bind="tooltipProps"
              class="collapse-strip h-100 border-e-sm d-flex align-center justify-center cursor-pointer"
              style="flex: 0 0 auto; width: 1rem"
              @click="collapsed = !collapsed"
            >
              <v-icon
                icon="mdi-chevron-left"
                size="small"
                :style="{
                  transform: collapsed ? 'rotate(180deg)' : 'none',
                  transition: 'transform 0.2s',
                }"
              ></v-icon>
            </div>
          </template>
        </v-tooltip>

        <div class="h-100" style="flex: 1 1 auto; min-width: 33.3333vw">
          <PayloadEditor
            :subsystem="leafEntry.subsystem"
            :name="leafEntry.name"
            :mode="leafEntry.mode"
            :version="leafEntry.version"
            :category="leafEntry.category"
          ></PayloadEditor>
        </div>
      </template>
    </template>

    <Spinner v-else></Spinner>
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
</script>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { childLocator, useNavStore } from '@/stores/nav'
import BundleColumn from './BundleColumn.vue'
import PayloadEditor from './PayloadEditor.vue'
import Spinner from './Spinner.vue'

const nav = useNavStore()
const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

// A path entry only opens a column or an editor once the key actually fills its alias
const columns = computed(() =>
  nav.bundlePath.flatMap((entry, index) => {
    const locator = entry.category === null ? childLocator(entry) : undefined
    return locator ? [{ index, ...locator }] : []
  }),
)

const leafEntry = computed(() => {
  const last = nav.bundlePath.at(-1)
  if (!last || last.category === null || last.category === 'external') return undefined
  const locator = childLocator(last)
  return locator && { ...locator, category: last.category }
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
  background: rgba(var(--v-theme-on-surface), 0.08);
}
</style>
