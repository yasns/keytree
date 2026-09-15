<template>
  <v-card class="d-flex flex-column h-100 elevation-overlay" style="min-height: 0">
    <KeyMetadata
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :payload="payload"
      :staged="staged"
      :pending="pending"
      :side="diffContext?.side"
      :counterpart="counterpart"
      v-model:panel="panel"
    ></KeyMetadata>

    <div class="overflow-y-auto flex-grow-1" style="min-height: 0" :ref="bindScroller">
      <v-list v-if="children" activatable slim>
        <v-list-item
          v-for="child in children"
          :key="child.alias"
          :active="child.alias === selectedAlias"
          :ripple="child.category !== 'external'"
          :class="rowClasses(child)"
          @click="onRowClick(child)"
          class="py-4"
        >
          <template v-slot:prepend>
            <v-icon
              :icon="iconFor(child, child.subsystem_name !== subsystem)"
              size="small"
            ></v-icon>
          </template>

          <template v-slot:title>
            <div class="d-flex flex-column">
              <span class="text-body-small text-medium-emphasis">{{ child.alias }}</span>
              <span class="key-label text-truncate"
                ><DiffText
                  :runs="targetLabelRuns(child)"
                  :highlight-class="diffHighlightClass"
                ></DiffText
              ></span>
            </div>
          </template>
        </v-list-item>
      </v-list>

      <Spinner v-else></Spinner>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { type ComponentPublicInstance, computed, onBeforeUnmount, ref, watch } from 'vue'
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { iconFor } from '@/category'
import type { ScrollSide } from '@/composables/useSyncedScroll'
import {
  useDiff,
  runsFor,
  sideHighlightClass,
  type ColumnDiffData,
} from '@/composables/useDiff'
import type { components } from '@/api-types'
import KeyMetadata from '../key/KeyMetadata.vue'
import Spinner from '../Spinner.vue'
import DiffText from './DiffText.vue'

type KeyOut = components['schemas']['KeyOut']
type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']

const props = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  pending?: boolean
  selectedAlias?: string
  /** Template-ref callback for the scrollable list, so a parent can sync its scroll position. */
  scrollerRef?: (el: Element | null) => void
  diffContext?: { diff: ReturnType<typeof useDiff>; depth: number; side: ScrollSide }
}>()

const emit = defineEmits<{ select: [child: KeyChildMetaOut]; close: [] }>()

const panel = defineModel<number | undefined>('panel')

const nav = useNavStore()
const changes = useChangesStore()

const payload = ref<KeyOut>()
const children = ref<KeyChildMetaOut[]>()

const staged = computed(() =>
  changes.stagedForColumn(props.subsystem, props.name, props.mode, props.version, props.pending),
)

function targetLabel(child: KeyChildMetaOut): string {
  if (child.category === 'external') return child.payload || '(none)'
  if (!child.mode_name || child.version === null) return '(none)'
  return `${child.subsystem_name}/${child.node_name}/${child.mode_name}/v${child.version}`
}

function bindScroller(el: Element | ComponentPublicInstance | null) {
  props.scrollerRef?.(el instanceof Element ? el : null)
}

function onRowClick(child: KeyChildMetaOut) {
  if (child.category === 'external') return
  if (child.alias !== props.selectedAlias) {
    emit('select', child)
    return
  }
  emit('close')
}

let loadToken = 0

async function load() {
  payload.value = undefined
  children.value = undefined
  const token = ++loadToken
  // Pending version has no key of its own: read rows from the committed source.
  const source = staged.value?.based_on
  const sourceMode = source?.mode_name ?? props.mode
  const sourceVersion = source?.version ?? props.version
  try {
    const [p, c] = await Promise.all([
      nav.fetchKeyPayload(props.subsystem, props.name, sourceMode, sourceVersion),
      nav.fetchKeyChildren(props.subsystem, props.name, sourceMode, sourceVersion),
    ])
    if (token !== loadToken) return
    payload.value = p
    children.value = c
  } catch {
    // e.g. a freshly forked mode with nothing committed yet: nothing to load
    if (token !== loadToken) return
    children.value = []
  }
}

watch(
  () =>
    [props.subsystem, props.name, props.mode, props.version, props.pending, staged.value] as const,
  load,
  { immediate: true },
)

watch(() => nav.keysToken, load)

watch(
  // Track diffContext's fields, not its identity: it's a fresh object on every parent render.
  () =>
    [
      props.diffContext?.diff,
      props.diffContext?.depth,
      props.diffContext?.side,
      payload.value,
      children.value,
      staged.value,
      props.pending,
    ] as const,
  ([diffInstance, depth, side]) => {
    if (diffInstance === undefined || depth === undefined || side === undefined) return
    if (payload.value === undefined && children.value === undefined) return
    diffInstance.publish(depth, side, {
      subsystem: props.subsystem,
      name: props.name,
      mode: props.mode,
      version: props.version,
      pending: !!props.pending,
      payload: payload.value,
      staged: staged.value,
      children: children.value,
    })
  },
)

onBeforeUnmount(() => {
  const ctx = props.diffContext
  if (ctx !== undefined) ctx.diff.clear(ctx.depth, ctx.side)
})

const counterpart = computed<ColumnDiffData | undefined>(() => {
  const ctx = props.diffContext
  return ctx && ctx.diff.counterpart(ctx.depth, ctx.side)
})

/** Memoized so each row doesn't re-scan the counterpart's full child list. */
const counterpartByAlias = computed(() => {
  const map = new Map<string, KeyChildMetaOut>()
  for (const c of counterpart.value?.children ?? []) map.set(c.alias, c)
  return map
})

function counterpartChild(child: KeyChildMetaOut): KeyChildMetaOut | undefined {
  return counterpartByAlias.value.get(child.alias)
}

function rowStatus(child: KeyChildMetaOut): 'changed' | 'only-here' | undefined {
  if (counterpart.value?.children === undefined) return undefined
  const match = counterpartChild(child)
  if (match === undefined) return 'only-here'
  return targetLabel(child) === targetLabel(match) ? undefined : 'changed'
}

function rowClasses(child: KeyChildMetaOut) {
  const status = rowStatus(child)
  return {
    'row-external': child.category === 'external',
    'row-diff-changed': status === 'changed',
    'row-diff-only-here': status === 'only-here',
    [`row-diff-${props.diffContext?.side}`]: status !== undefined,
  }
}

function targetLabelRuns(child: KeyChildMetaOut) {
  const match = counterpartChild(child)
  return runsFor(targetLabel(child), match && targetLabel(match))
}

const diffHighlightClass = computed(() => sideHighlightClass(props.diffContext?.side))
</script>

<style scoped>
.v-list-item + .v-list-item {
  border-top: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.row-diff-left {
  background-color: rgba(var(--v-theme-error), 0.12);
}
.row-diff-right {
  background-color: rgba(var(--v-theme-success), 0.12);
}
.row-diff-changed.row-diff-left {
  border-left: 3px solid rgb(var(--v-theme-error));
}
.row-diff-changed.row-diff-right {
  border-left: 3px solid rgb(var(--v-theme-success));
}
.row-diff-only-here.row-diff-left {
  border-left: 3px dashed rgb(var(--v-theme-error));
}
.row-diff-only-here.row-diff-right {
  border-left: 3px dashed rgb(var(--v-theme-success));
}
</style>
