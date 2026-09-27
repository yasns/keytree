<template>
  <div class="d-flex flex-column flex-grow-1" style="min-height: 0">
    <DiffPayload
      v-if="showLeafDiff"
      :left="leftLeaf"
      :right="rightLeaf"
      show-back-to-split
      @back="onBack"
    ></DiffPayload>

    <div v-else class="d-flex flex-grow-1" style="min-height: 0">
      <template v-if="sides.length">
        <template v-for="(side, i) in sides" :key="side.name">
          <div
            v-if="i > 0"
            class="h-100 border-e-sm border-s-sm elevation-4 elevation-overlay"
            style="flex: 0 0 auto; width: 1rem"
          ></div>

          <div
            :ref="(el) => bindScroller(side.name, el)"
            class="d-flex h-100 overflow-x-auto"
            style="flex: 1 1 50%; min-width: 0"
          >
            <div class="h-100 border-e-sm" style="flex: 0 0 auto; width: 400px">
              <DiffColumn
                :subsystem="side.root.subsystem"
                :name="side.root.name"
                :mode="side.root.mode"
                :version="side.root.version"
                :pending="side.root.pending"
                :selected-alias="aliases[0]"
                :scroller-ref="(el) => sync.register(0, side.name, el)"
                :diff-context="{ diff, depth: 0, side: side.name }"
                v-model:panel="metaPanel"
                @select="(child) => onSelect(0, child)"
                @close="() => onClose(0)"
              ></DiffColumn>
            </div>

            <div
              v-for="slot in side.slots"
              :key="slot.index"
              class="h-100 border-e-sm"
              style="flex: 0 0 auto; width: 400px"
            >
              <DiffColumn
                v-if="slot.present"
                :subsystem="slot.locator.subsystem"
                :name="slot.locator.name"
                :mode="slot.locator.mode"
                :version="slot.locator.version"
                :pending="slot.locator.pending"
                :selected-alias="aliases[slot.index + 1]"
                :scroller-ref="(el) => sync.register(slot.index + 1, side.name, el)"
                :diff-context="{ diff, depth: slot.index + 1, side: side.name }"
                v-model:panel="metaPanel"
                @select="(child) => onSelect(slot.index + 1, child)"
                @close="() => onClose(slot.index + 1)"
              ></DiffColumn>

              <div v-else>
                <v-alert
                  class="h-100 rounded-0"
                  variant="tonal"
                  :text="
                    slot.reason === 'leaf'
                      ? 'Not a key at this version'
                      : 'Not present at this version'
                  "
                ></v-alert>
              </div>
            </div>
          </div>
        </template>
      </template>

      <template v-else>
        <div class="h-100 border-e-sm" style="flex: 0 0 auto; width: 400px">
          <v-skeleton-loader type="list-item@8" class="h-100"></v-skeleton-loader>
        </div>
        <div class="h-100 border-e-sm border-s-sm" style="flex: 0 0 auto; width: 400px">
          <v-skeleton-loader type="list-item@8" class="h-100"></v-skeleton-loader>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { type ComponentPublicInstance, computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { childLocator, useNavStore, type BundleRoot } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useSyncedScroll, type ScrollSide } from '@/composables/useSyncedScroll'
import { useDiff } from '@/composables/useDiff'
import { resolveDiffRoot, type DiffTarget } from '@/router'
import { leafLocatorFor, parseBundlePath } from '../key/KeyBrowser.vue'
import DiffColumn from './DiffColumn.vue'
import DiffPayload, { type LeafSide } from './DiffPayload.vue'
import type { components } from '@/api-types'

type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']

const props = defineProps<{ diffTarget: DiffTarget }>()

const nav = useNavStore()
const changes = useChangesStore()
const route = useRoute()
const router = useRouter()
const sync = useSyncedScroll()
const diff = useDiff()
const metaPanel = ref<number>()

const aliases = computed(() => parseBundlePath(route.query.at as string | undefined))

const diffRoot = computed<BundleRoot | undefined>(() => {
  const root = nav.bundleRoot
  if (!root) return undefined
  return resolveDiffRoot(
    root,
    props.diffTarget,
    (mode) => changes.stagedForMode(root.subsystem, root.name, mode)?.expected_version,
  )
})

const leftPath = ref<KeyChildMetaOut[]>([])
const rightPath = ref<KeyChildMetaOut[]>([])

let resolveToken = 0
watch(
  () => [nav.bundleRoot, diffRoot.value, aliases.value] as const,
  async ([left, right, path]) => {
    const token = ++resolveToken
    const [l, r] = await Promise.all([
      left ? nav.resolveBundlePath(left, path) : Promise.resolve([]),
      right ? nav.resolveBundlePath(right, path) : Promise.resolve([]),
    ])
    if (token !== resolveToken) return
    leftPath.value = l
    rightPath.value = r
  },
  { immediate: true },
)

type ColumnSlot = { index: number } & (
  | { present: true; locator: BundleRoot }
  // 'leaf': this side has a key here, it's just not a bundle to drill into further.
  | { present: false; reason: 'absent' | 'leaf' }
)

/** One slot per open alias, index-aligned with the other side even where this side has nothing. */
function slotsFor(path: KeyChildMetaOut[], depth: number): ColumnSlot[] {
  const slots: ColumnSlot[] = []
  let stopped = false
  for (let i = 0; i < depth; i++) {
    const entry = stopped ? undefined : path[i]
    if (!entry) {
      slots.push({ index: i, present: false, reason: 'absent' })
      continue
    }
    const locator = entry.category === null ? childLocator(entry) : undefined
    if (!locator) stopped = true
    slots.push(
      locator ? { index: i, present: true, locator } : { index: i, present: false, reason: 'leaf' },
    )
  }
  return slots
}

const leftSlots = computed(() => slotsFor(leftPath.value, aliases.value.length))
const rightSlots = computed(() => slotsFor(rightPath.value, aliases.value.length))

type Side = { name: ScrollSide; root: BundleRoot; slots: ColumnSlot[] }

/** Both columns share identical rendering; this drives the template's single v-for. */
const sides = computed<Side[]>(() => {
  const left = nav.bundleRoot
  const right = diffRoot.value
  if (!left || !right) return []
  return [
    { name: 'left', root: left, slots: leftSlots.value },
    { name: 'right', root: right, slots: rightSlots.value },
  ]
})

/** A side counts as reaching the leaf only if it resolved the full requested path. */
function leafAt(path: KeyChildMetaOut[], depth: number): LeafSide | undefined {
  if (path.length !== depth) return undefined
  const leaf = leafLocatorFor(path.at(-1))
  return leaf && { root: leaf.locator, format: leaf.format, category: leaf.category }
}

const leftLeaf = computed(() => leafAt(leftPath.value, aliases.value.length))
const rightLeaf = computed(() => leafAt(rightPath.value, aliases.value.length))
const showLeafDiff = computed(() => !!leftLeaf.value || !!rightLeaf.value)

function navigateTo(next: string[]) {
  const query = { ...route.query } as Record<string, string>
  const at = next.map((s) => encodeURIComponent(s)).join('/')
  if (at) query.at = at
  else delete query.at
  router.replace({ name: 'editor', params: route.params, query })
}

function onSelect(depth: number, child: KeyChildMetaOut) {
  navigateTo([...aliases.value.slice(0, depth), child.alias])
}

function onClose(depth: number) {
  navigateTo(aliases.value.slice(0, depth))
}

function onBack() {
  navigateTo(aliases.value.slice(0, -1))
}

const scrollers: Partial<Record<ScrollSide, HTMLElement>> = {}

function bindScroller(side: ScrollSide, el: Element | ComponentPublicInstance | null) {
  const target = el instanceof HTMLElement ? el : null
  scrollers[side] = target ?? undefined
  sync.registerRow(side, target)
}

watch(
  () => aliases.value.length,
  async () => {
    await nextTick()
    for (const el of Object.values(scrollers)) if (el) el.scrollLeft = el.scrollWidth
  },
)
</script>
