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

    <div v-if="readOnly" class="flex-shrink-0">
      <ReadOnlyAlert :reason="readOnlyText"></ReadOnlyAlert>
    </div>
    <div v-if="key?.retired_descendants.length" class="flex-shrink-0">
      <RetiredDescendantsAlert :refs="key.retired_descendants"></RetiredDescendantsAlert>
    </div>
    <div v-if="pendingEditors.length" class="flex-shrink-0">
      <PendingEditorsAlert :editors="pendingEditors"></PendingEditorsAlert>
    </div>

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
      :read-only="readOnly"
      :payload="key"
      :validation-errors="validationErrors"
      has-payload-editor
      :payload-file-type="payloadFileType"
      @save="save"
      @save-and-queue="saveAndQueue"
      @discard="resetToBaseline"
      @fork="fork"
      @copy-to="copyTo"
      @export-payload="exportPayload"
      @import-payload="importPayload"
      @show-problems="showFirstProblem"
    ></KeyToolbar>

    <div ref="editorElem" class="flex-grow-1" style="min-height: 0"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'
import { useNavStore } from '@/stores/nav'
import { useChangesStore, useDirtySource } from '@/stores/changes'
import { useKeyReadOnly } from '@/composables/useReadOnly'
import { useCurrentMode, useIsArchived, useModesByPath } from '@/composables/useModes'
import { useStagedNavigation } from '@/composables/useStagedNavigation'
import { usePendingEditors } from '@/composables/usePendingEditors'
import {
  useMonacoTheme,
  createPayloadModel,
  formatMarkers,
  waitForMarkers,
} from '@/composables/useMonaco'
import { languageFor } from '@/category'
import KeyMetadata from './KeyMetadata.vue'
import KeyToolbar from './KeyToolbar.vue'
import ReadOnlyAlert from './ReadOnlyAlert.vue'
import RetiredDescendantsAlert from './RetiredDescendantsAlert.vue'
import PendingEditorsAlert from './PendingEditorsAlert.vue'

const {
  subsystem,
  name,
  mode,
  version,
  category,
  canQueue,
  pending,
  depth,
  searchQuery,
  searchRegex,
  revealFirstProblem,
} = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  category?: string | null
  canQueue?: boolean
  pending?: boolean
  /** Bundle-path index when rendered inside a bundle */
  depth?: number
  /** Prefills Monaco's find widget when arriving from a search. */
  searchQuery?: string
  searchRegex?: boolean
  revealFirstProblem?: boolean
}>()

const emit = defineEmits<{ queue: [] }>()

const nav = useNavStore()
const changes = useChangesStore()
const { navigateToStaged, showStaged, afterStage } = useStagedNavigation()

const editorElem = ref<HTMLDivElement>()
const key = ref<Awaited<ReturnType<typeof nav.fetchKeyPayload>>>()
const modes = useModesByPath(
  computed(() => subsystem),
  computed(() => name),
)
const currentMode = useCurrentMode(
  modes,
  computed(() => mode),
)
const archived = useIsArchived(currentMode)
const { readOnly, readOnlyText } = useKeyReadOnly(() => subsystem, key, archived)
const pendingEditors = usePendingEditors(computed(() => currentMode.value?.id))
const dirty = ref(false)
// Always the rightmost column, so nothing is ever deeper than it
useDirtySource(dirty, Infinity)
let editor: monaco.editor.IStandaloneCodeEditor | undefined
let baseValue = ''
let modelCategory: string | null | undefined
let loadToken = 0
let markerListener: monaco.IDisposable | undefined

const isYaml = computed(() => languageFor(category) === 'yaml')
const markers = ref<monaco.editor.IMarker[]>([])
const validationErrors = computed(() => (isYaml.value ? formatMarkers(markers.value) : undefined))

function refreshMarkers() {
  const model = editor?.getModel()
  markers.value =
    model && isYaml.value
      ? monaco.editor.getModelMarkers({ resource: model.uri, owner: 'yaml' })
      : []
}

const staged = computed(() =>
  pending
    ? changes.stagedForMode(subsystem, name, mode)
    : changes.stagedFor(subsystem, name, mode, version),
)

function resetToBaseline() {
  if (!editor) return
  baseValue = pending ? (staged.value?.proposed_payload ?? '') : (key.value?.payload ?? '')
  if (editor.getValue() !== baseValue) editor.setValue(baseValue)
  dirty.value = false
}

onMounted(() => {
  if (!editorElem.value) return
  const initialTheme = useMonacoTheme()
  modelCategory = category
  editor = monaco.editor.create(editorElem.value, {
    model: createPayloadModel('', category),
    automaticLayout: true,
    theme: initialTheme,
    readOnly: readOnly.value,
  })
  editor.onDidChangeModelContent(() => {
    dirty.value = editor!.getValue() !== baseValue
  })
  markerListener = monaco.editor.onDidChangeMarkers((uris) => {
    const model = editor?.getModel()
    if (model && uris.some((uri) => uri.toString() === model.uri.toString())) refreshMarkers()
  })
  void loadAndReveal()
})

function markersSettled(): Promise<void> {
  const model = editor?.getModel()
  return model ? waitForMarkers(model) : Promise.resolve()
}

// Selects the first match so Monaco's find action seeds its search box from it.
function revealInFind(query: string) {
  const match = editor
    ?.getModel()
    ?.findNextMatch(query, { lineNumber: 1, column: 1 }, !!searchRegex, false, null, false)
  if (!match || !editor) return
  editor.setSelection(match.range)
  editor.revealRangeInCenter(match.range)
  editor.trigger('keyboard', 'actions.find', null)
}

async function loadPayload() {
  if (!editor) return
  const token = ++loadToken
  const fetched = pending ? undefined : await nav.fetchKeyPayload(subsystem, name, mode, version)
  if (token !== loadToken || !editor) return
  key.value = fetched
  if (category !== modelCategory) {
    modelCategory = category
    const oldModel = editor.getModel()
    editor.setModel(createPayloadModel('', category))
    oldModel?.dispose()
    markers.value = []
  }
  resetToBaseline()
}

async function revealProblemIfRequested() {
  if (!revealFirstProblem) return
  await markersSettled()
  showFirstProblem()
}

async function loadAndReveal() {
  await loadPayload()
  if (searchQuery) revealInFind(searchQuery)
  await revealProblemIfRequested()
}

watch(() => [subsystem, name, mode, version, pending], loadAndReveal)

watch(() => revealFirstProblem, revealProblemIfRequested)

watch(readOnly, (value) => editor?.updateOptions({ readOnly: value }))

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

// Reads markers as of now; saving within the yaml worker's validation debounce can miss errors just typed.
function validationStatus(): 'skipped' | 'passed' | 'failed' {
  if (!isYaml.value) return 'skipped'
  return markers.value.length > 0 ? 'failed' : 'passed'
}

function baseEdit(comment: string) {
  return {
    subsystem_name: subsystem,
    vertex_name: name,
    mode_name: mode,
    base_version: version,
    proposed_payload: editor!.getValue(),
    comment,
    validation_status: validationStatus(),
  }
}

async function save(comment: string) {
  await changes.stage([baseEdit(comment)])
  const { edit, left } = afterStage(subsystem, name, mode, version, pending)
  if (left) return
  resetToBaseline()
  if (pending) return
  if (!canQueue) {
    showStaged(subsystem, name, mode)
    return
  }
  if (depth === undefined) return
  if (edit) nav.markPathStaged(depth - 1, edit.expected_version)
}

async function saveAndQueue(comment: string) {
  await save(comment)
  emit('queue')
}

async function fork(newModeName: string, description: string) {
  await changes.fork({
    ...baseEdit(description),
    new_mode_name: newModeName,
    description,
  })
  resetToBaseline()
  await navigateToStaged(subsystem, name, newModeName, `Forked to mode "${newModeName}"`)
}

async function copyTo(targetMode: string, comment: string) {
  await changes.copyTo({ ...baseEdit(comment), target_mode_name: targetMode })
  resetToBaseline()
  await navigateToStaged(subsystem, name, targetMode, `Copied to mode "${targetMode}"`)
}

const payloadExtensions: Record<string, string[]> = { yaml: ['yaml', 'yml'], xml: ['xml'] }
const currentExts = computed(() => payloadExtensions[languageFor(category)])
const payloadFileType = computed(() => currentExts.value?.[0]?.toUpperCase())

function exportPayload() {
  if (!editor) return
  const ext = currentExts.value?.[0]
  const blob = new Blob([editor.getValue()], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${subsystem}_${name}_${mode}_v${version}${ext ? `.${ext}` : ''}`
  a.click()
  URL.revokeObjectURL(url)
}

function showFirstProblem() {
  editor?.focus()
  editor?.getAction('editor.action.marker.next')?.run()
}

function importPayload() {
  const input = document.createElement('input')
  input.type = 'file'
  if (currentExts.value) input.accept = currentExts.value.map((e) => `.${e}`).join(',')
  input.onchange = async () => {
    const file = input.files?.[0]
    if (file && editor) editor.setValue(await file.text())
  }
  input.click()
}

onBeforeUnmount(() => {
  markerListener?.dispose()
  editor?.getModel()?.dispose()
  editor?.dispose()
})
</script>
