<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <KeyMetadata
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :payload="key"
      :staged="staged"
      :pending="pending"
    ></KeyMetadata>

    <KeyToolbar
      :dirty="dirty"
      :staged="!!staged"
      :staged-comment="staged?.comment"
      :can-queue="!!canQueue"
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :committed="!pending"
      @save="save"
      @save-and-queue="saveAndQueue"
      @discard="resetToBaseline"
      @fork="fork"
      @copy-to="copyTo"
    ></KeyToolbar>

    <div ref="editorElem" class="flex-grow-1" style="min-height: 0"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'
import { useNavStore } from '@/stores/nav'
import { useChangesStore, useDirtySource } from '@/stores/changes'
import { useStagedNavigation } from '@/composables/useStagedNavigation'
import { useMonacoTheme } from '@/composables/useMonaco'
import { languageFor } from '@/category'
import KeyMetadata from './KeyMetadata.vue'
import KeyToolbar from './KeyToolbar.vue'

const { subsystem, name, mode, version, category, canQueue, pending, depth } = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  category?: string | null
  canQueue?: boolean
  pending?: boolean
  /** Bundle-path index when rendered inside a bundle, not as the routed key. */
  depth?: number
}>()

const emit = defineEmits<{ queue: [] }>()

const nav = useNavStore()
const changes = useChangesStore()
const { navigateToStaged, showStaged } = useStagedNavigation()

const editorElem = ref<HTMLDivElement>()
const key = ref<Awaited<ReturnType<typeof nav.fetchKeyPayload>>>()
const dirty = ref(false)
// Always the rightmost column, so nothing is ever deeper than it
useDirtySource(dirty, Infinity)
let editor: monaco.editor.IStandaloneCodeEditor | undefined
let baseValue = ''

const staged = computed(() =>
  pending
    ? changes.stagedForMode(subsystem, name, mode)
    : changes.stagedFor(subsystem, name, mode, version),
)

function resetToBaseline() {
  if (!editor) return
  baseValue = staged.value?.proposed_payload ?? key.value?.payload ?? ''
  if (editor.getValue() !== baseValue) editor.setValue(baseValue)
  dirty.value = false
}

onMounted(() => {
  if (!editorElem.value) return
  const initialTheme = useMonacoTheme()
  editor = monaco.editor.create(editorElem.value, {
    value: '',
    language: languageFor(category),
    automaticLayout: true,
    theme: initialTheme,
  })
  editor.onDidChangeModelContent(() => {
    dirty.value = editor!.getValue() !== baseValue
  })
  loadPayload()
})

async function loadPayload() {
  if (!editor) return
  key.value = pending ? undefined : await nav.fetchKeyPayload(subsystem, name, mode, version)
  resetToBaseline()
  const model = editor.getModel()
  if (model) monaco.editor.setModelLanguage(model, languageFor(category))
}

watch(() => [subsystem, name, mode, version, pending], loadPayload)

// reload after commit, unless it would discard an unsaved payload
watch(
  () => nav.keysToken,
  () => {
    if (!dirty.value) void loadPayload()
  },
)

watch(staged, () => {
  if (!dirty.value) resetToBaseline()
})

function baseEdit(comment: string) {
  return {
    subsystem_name: subsystem,
    node_name: name,
    mode_name: mode,
    base_version: version,
    proposed_payload: editor!.getValue(),
    comment,
  }
}

async function save(comment: string) {
  if (!editor) return
  await changes.stage([baseEdit(comment)])
  resetToBaseline()
  if (pending) return
  if (!canQueue) {
    showStaged(subsystem, name, mode)
    return
  }
  if (depth === undefined) return
  const edit = changes.stagedForMode(subsystem, name, mode)
  if (edit) nav.markPathStaged(depth - 1, edit.expected_version)
}

async function saveAndQueue(comment: string) {
  await save(comment)
  emit('queue')
}

async function fork(newModeName: string, description: string) {
  if (!editor) return
  await changes.fork({ ...baseEdit(description), new_mode_name: newModeName, description })
  resetToBaseline()
  await navigateToStaged(subsystem, name, newModeName, `Forked to mode "${newModeName}"`)
}

async function copyTo(targetMode: string, comment: string) {
  if (!editor) return
  await changes.copyTo({ ...baseEdit(comment), target_mode_name: targetMode })
  resetToBaseline()
  await navigateToStaged(subsystem, name, targetMode, `Copied to mode "${targetMode}"`)
}

onBeforeUnmount(() => editor?.dispose())
</script>
