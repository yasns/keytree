<template>
  <div class="d-flex flex-grow-1" style="min-height: 0">
    <div
      v-if="showBackToSplit"
      v-ripple
      class="d-flex align-center justify-center cursor-pointer back-strip elevation-5 elevation-overlay"
      style="width: 2rem"
      @click="emit('back')"
    >
      <v-icon icon="mdi-arrow-left" size="small"></v-icon>
      <v-tooltip activator="parent" location="right">Back</v-tooltip>
    </div>

    <div class="d-flex flex-column flex-grow-1" style="min-height: 0; min-width: 0">
      <div class="d-flex align-stretch">
        <div v-for="s in sides" :key="s.side" style="flex: 1; min-width: 0">
          <KeyMetadata
            v-if="s.leaf"
            class="h-100"
            v-model:panel="panel"
            :subsystem="s.leaf.root.subsystem"
            :name="s.leaf.root.name"
            :mode="s.leaf.root.mode"
            :version="s.leaf.root.version"
            :payload="s.payload"
            :staged="s.staged"
            :pending="s.leaf.root.pending"
            :side="s.side"
            :counterpart="
              s.other.leaf && {
                subsystem: s.other.leaf.root.subsystem,
                name: s.other.leaf.root.name,
                mode: s.other.leaf.root.mode,
                version: s.other.leaf.root.version,
                payload: s.other.payload,
                staged: s.other.staged,
                pending: s.other.leaf.root.pending,
              }
            "
          ></KeyMetadata>
          <v-alert
            v-else
            variant="tonal"
            text="Not present at this version"
            class="rounded-0 h-100"
          ></v-alert>
        </div>
      </div>

      <div class="flex-grow-1 position-relative" style="min-height: 0">
        <div ref="editorElem" class="h-100"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'
import { useNavStore, type BundleRoot } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import { useMonacoTheme, createPayloadModel } from '@/composables/useMonaco'
import { pendingSourceRef } from '@/composables/useDiff'
import type { components } from '@/api-types'
import KeyMetadata from '../key/KeyMetadata.vue'

type KeyOut = components['schemas']['KeyOut']
type StagedEditOut = components['schemas']['StagedEditOut']

export type LeafSide = { root: BundleRoot; format?: string | null; category?: string | null }

const props = defineProps<{
  left?: LeafSide
  right?: LeafSide
  /** Hide when there's no split to go back to (a leaf-only comparison). */
  showBackToSplit?: boolean
}>()

const emit = defineEmits<{ back: [] }>()

const nav = useNavStore()
const changes = useChangesStore()
const snackbar = useSnackbarStore()

const panel = ref<number>()
const editorElem = ref<HTMLDivElement>()
let diffEditor: monaco.editor.IStandaloneDiffEditor | undefined
let originalModel: monaco.editor.ITextModel | undefined
let modifiedModel: monaco.editor.ITextModel | undefined

const leftPayload = ref<KeyOut>()
const rightPayload = ref<KeyOut>()

const leftStaged = computed(() =>
  props.left?.root.pending
    ? changes.stagedForMode(props.left.root.subsystem, props.left.root.name, props.left.root.mode)
    : undefined,
)
const rightStaged = computed(() =>
  props.right?.root.pending
    ? changes.stagedForMode(
        props.right.root.subsystem,
        props.right.root.name,
        props.right.root.mode,
      )
    : undefined,
)

type SideView = {
  side: 'left' | 'right'
  leaf?: LeafSide
  payload?: KeyOut
  staged?: StagedEditOut
}

const sides = computed<(SideView & { other: SideView })[]>(() => {
  const left: SideView = {
    side: 'left',
    leaf: props.left,
    payload: leftPayload.value,
    staged: leftStaged.value,
  }
  const right: SideView = {
    side: 'right',
    leaf: props.right,
    payload: rightPayload.value,
    staged: rightStaged.value,
  }
  return [
    { ...left, other: right },
    { ...right, other: left },
  ]
})

async function keyOf(
  side: LeafSide | undefined,
  staged: StagedEditOut | undefined,
): Promise<KeyOut | undefined> {
  if (!side) return undefined
  if (side.root.pending && !staged?.based_on) return undefined
  const { root } = side
  const { mode, version } = pendingSourceRef(root.pending, staged, root.mode, root.version)
  return nav.fetchKeyPayload(root.subsystem, root.name, mode, version)
}

function textOf(
  side: LeafSide | undefined,
  staged: string | null | undefined,
  key: KeyOut | undefined,
): string {
  if (!side) return ''
  if (!side.root.pending) return key?.payload ?? ''
  // An edit that only restages children leaves the payload untouched: show the ancestor's.
  return staged ?? key?.payload ?? ''
}

let loadToken = 0

async function load() {
  if (!diffEditor) return
  const token = ++loadToken
  let keys: [KeyOut | undefined, KeyOut | undefined]
  try {
    keys = await Promise.all([
      keyOf(props.left, leftStaged.value),
      keyOf(props.right, rightStaged.value),
    ])
  } catch (e) {
    if (token === loadToken) snackbar.notifyError(e)
    return
  }
  if (token !== loadToken || !diffEditor) return
  const [leftKey, rightKey] = keys
  leftPayload.value = leftKey
  rightPayload.value = rightKey
  const originalValue = textOf(props.left, leftStaged.value?.proposed_payload, leftKey)
  const modifiedValue = textOf(props.right, rightStaged.value?.proposed_payload, rightKey)
  originalModel?.dispose()
  modifiedModel?.dispose()
  originalModel = createPayloadModel(originalValue, props.left?.format, props.left?.category)
  modifiedModel = createPayloadModel(modifiedValue, props.right?.format, props.right?.category)
  diffEditor.setModel({ original: originalModel, modified: modifiedModel })
}

onMounted(() => {
  if (!editorElem.value) return
  const initialTheme = useMonacoTheme()
  diffEditor = monaco.editor.createDiffEditor(editorElem.value, {
    readOnly: true,
    renderValidationDecorations: 'on',
    renderSideBySide: true,
    automaticLayout: true,
    theme: initialTheme,
  })
  void load()
})

watch(() => [props.left, props.right, leftStaged.value, rightStaged.value], load, { deep: true })
watch(() => nav.keysToken, load)

onBeforeUnmount(() => {
  diffEditor?.dispose()
  originalModel?.dispose()
  modifiedModel?.dispose()
})
</script>

<style scoped>
.back-strip:hover {
  background: rgba(var(--v-theme-on-surface), 0.25);
}
</style>
