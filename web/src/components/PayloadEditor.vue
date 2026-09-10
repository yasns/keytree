<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <KeyMetadata
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :payload="key"
      :staged="staged"
    ></KeyMetadata>

    <EditorToolbar
      :dirty="dirty"
      :staged="!!staged"
      :staged-comment="staged?.comment"
      :can-queue="!!canQueue"
      @save="save"
      @save-and-queue="saveAndQueue"
      @discard="resetToBaseline"
    ></EditorToolbar>

    <div ref="editorElem" class="flex-grow-1" style="min-height: 0"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTheme } from 'vuetify'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import { useNavStore } from '@/stores/nav'
import { useChangesStore, useDirtySource } from '@/stores/changes'
import { CATEGORY } from '@/category'
import KeyMetadata from './KeyMetadata.vue'
import EditorToolbar from './EditorToolbar.vue'

;(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
}

const { subsystem, name, mode, version, category, canQueue } = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  category?: string | null
  canQueue?: boolean
}>()

const emit = defineEmits<{ queue: [] }>()

const nav = useNavStore()
const changes = useChangesStore()
const theme = useTheme()

const editorElem = ref<HTMLDivElement>()
const key = ref<Awaited<ReturnType<typeof nav.fetchKeyPayload>>>()
const dirty = ref(false)
// Always the rightmost column, so nothing is ever deeper than it
useDirtySource(dirty, Infinity)
let editor: monaco.editor.IStandaloneCodeEditor | undefined
let baseValue = ''

const staged = computed(() => changes.stagedFor(subsystem, name, mode, version))

function resetToBaseline() {
  if (!editor) return
  baseValue = staged.value?.proposed_payload ?? key.value?.payload ?? ''
  if (editor.getValue() !== baseValue) editor.setValue(baseValue)
  dirty.value = false
}

function languageFor(category: string | null | undefined): string {
  return (category ? CATEGORY[category]?.format : undefined) ?? 'plaintext'
}

onMounted(() => {
  if (!editorElem.value) return
  editor = monaco.editor.create(editorElem.value, {
    value: '',
    language: languageFor(category),
    automaticLayout: true,
    theme: theme.current.value.dark ? 'vs-dark' : 'vs',
  })
  editor.onDidChangeModelContent(() => {
    dirty.value = editor!.getValue() !== baseValue
  })
  loadPayload()
})

async function loadPayload() {
  if (!editor) return
  key.value = await nav.fetchKeyPayload(subsystem, name, mode, version)
  resetToBaseline()
  const model = editor.getModel()
  if (model) monaco.editor.setModelLanguage(model, languageFor(category))
}

watch(() => [subsystem, name, mode, version], loadPayload)

// Reload committed data after a commit, unless it would throw away an unsaved payload
watch(
  () => nav.keysToken,
  () => {
    if (!dirty.value) void loadPayload()
  },
)

watch(staged, () => {
  if (!dirty.value) resetToBaseline()
})

async function save(comment: string) {
  if (!editor) return
  await changes.stage([
    {
      subsystem_name: subsystem,
      node_name: name,
      mode_name: mode,
      base_version: version,
      proposed_payload: editor.getValue(),
      comment,
    },
  ])
  resetToBaseline()
}

async function saveAndQueue(comment: string) {
  await save(comment)
  emit('queue')
}

watch(
  () => theme.current.value.dark,
  (dark) => editor?.updateOptions({ theme: dark ? 'vs-dark' : 'vs' }),
)

onBeforeUnmount(() => editor?.dispose())
</script>
