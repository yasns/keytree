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
      :read-only="readOnly"
      :validation-errors="validationErrors"
      @save="save"
      @save-and-queue="saveAndQueue"
      @discard="resetToBaseline"
      @fork="fork"
      @copy-to="copyTo"
    ></KeyToolbar>

    <ReadOnlyAlert v-if="readOnly"></ReadOnlyAlert>

    <div ref="editorElem" class="flex-grow-1" style="min-height: 0"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'
import { useNavStore } from '@/stores/nav'
import { useChangesStore, useDirtySource } from '@/stores/changes'
import { useReadOnly } from '@/composables/useReadOnly'
import { useStagedNavigation } from '@/composables/useStagedNavigation'
import { useMonacoTheme, createPayloadModel, formatMarkers } from '@/composables/useMonaco'
import { languageFor } from '@/category'
import KeyMetadata from './KeyMetadata.vue'
import KeyToolbar from './KeyToolbar.vue'
import ReadOnlyAlert from './ReadOnlyAlert.vue'

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
}>()

const emit = defineEmits<{ queue: [] }>()

const nav = useNavStore()
const changes = useChangesStore()
const { navigateToStaged, showStaged } = useStagedNavigation()

const readOnly = useReadOnly(() => subsystem)

const editorElem = ref<HTMLDivElement>()
const key = ref<Awaited<ReturnType<typeof nav.fetchKeyPayload>>>()
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
  loadPayload().then(() => {
    if (searchQuery) revealInFind(searchQuery)
  })
})

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

watch(() => [subsystem, name, mode, version, pending], loadPayload)

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
    node_name: name,
    mode_name: mode,
    base_version: version,
    proposed_payload: editor!.getValue(),
    comment,
    validation_status: validationStatus(),
  }
}

async function save(comment: string) {
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

onBeforeUnmount(() => {
  markerListener?.dispose()
  editor?.getModel()?.dispose()
  editor?.dispose()
})
</script>
