<template>
  <div class="d-flex flex-column h-100 elevation-1 elevation-overlay" style="min-height: 0">
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
          v-for="child in effectiveChildren"
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
              <span class="key-label key-label-truncate"
                ><span class="key-label-head"
                  ><DiffText
                    :runs="targetLabelRuns(child)[0]"
                    :highlight-class="diffHighlightClass"
                  ></DiffText></span
                ><span class="key-label-tail"
                  ><DiffText
                    :runs="targetLabelRuns(child)[1]"
                    :highlight-class="diffHighlightClass"
                  ></DiffText></span
              ></span>
            </div>
          </template>

          <template v-if="child.category !== 'external'" v-slot:append>
            <v-icon icon="mdi-chevron-right" size="small"></v-icon>
          </template>
        </v-list-item>
      </v-list>

      <v-skeleton-loader v-else type="list-item@6"></v-skeleton-loader>
    </div>
  </div>
</template>

<script setup lang="ts">
import { type ComponentPublicInstance, computed, onBeforeUnmount, ref, watch } from 'vue'
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import { iconFor } from '@/category'
import type { ScrollSide } from '@/composables/useSyncedScroll'
import {
  useDiff,
  runsForLabel,
  sideHighlightClass,
  pendingSourceRef,
  type DiffRun,
  type ColumnDiffData,
} from '@/composables/useDiff'
import type { components } from '@/api-types'
import KeyMetadata from '../key/KeyMetadata.vue'
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
const snackbar = useSnackbarStore()

const payload = ref<KeyOut>()
const children = ref<KeyChildMetaOut[]>()

const staged = computed(() =>
  changes.stagedForColumn(props.subsystem, props.name, props.mode, props.version, props.pending),
)

function targetLabel(child: KeyChildMetaOut): string {
  if (child.category === 'external') return child.payload || '(none)'
  if (!child.mode_name || child.version === null) return '(none)'
  return `${child.subsystem_name}/${child.namespace_name}/${child.mode_name}/v${child.version}`
}

const effectiveChildren = computed(() =>
  children.value?.map((child) =>
    changes.overlayStagedChild(props.pending ? staged.value : undefined, child),
  ),
)

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
  const { mode: sourceMode, version: sourceVersion } = pendingSourceRef(
    props.pending,
    staged.value,
    props.mode,
    props.version,
  )
  try {
    const [p, c] = await Promise.all([
      nav.fetchKeyPayload(props.subsystem, props.name, sourceMode, sourceVersion),
      nav.fetchKeyChildren(props.subsystem, props.name, sourceMode, sourceVersion),
    ])
    if (token !== loadToken) return
    payload.value = p
    children.value = c
  } catch (e) {
    if (token !== loadToken) return
    snackbar.notifyError(e)
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
      effectiveChildren.value,
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
      children: effectiveChildren.value,
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

function targetLabelRuns(child: KeyChildMetaOut): [DiffRun[], DiffRun[]] {
  const match = counterpartChild(child)
  return runsForLabel(targetLabel(child), match && targetLabel(match))
}

const diffHighlightClass = computed(() => sideHighlightClass(props.diffContext?.side))
</script>

<style scoped>
.v-list-item + .v-list-item {
  border-top: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
}
:deep(.v-list-item__append) {
  margin-inline-start: 4px;
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
