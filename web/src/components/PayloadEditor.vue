<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <KeyMetadata
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :payload="key"
    ></KeyMetadata>

    <div ref="editorElem" class="flex-grow-1" style="min-height: 0"></div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTheme } from 'vuetify'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import { useNavStore } from '@/stores/nav'
import { CATEGORY } from '@/category'
import KeyMetadata from './KeyMetadata.vue'

;(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
}

const { subsystem, name, mode, version } = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
}>()

const nav = useNavStore()
const theme = useTheme()

const editorElem = ref<HTMLDivElement>()
const key = ref<Awaited<ReturnType<typeof nav.fetchKeyPayload>>>()
let editor: monaco.editor.IStandaloneCodeEditor | undefined

onMounted(() => {
  if (!editorElem.value) return
  const category = nav.nodeDetail?.category
  editor = monaco.editor.create(editorElem.value, {
    value: '',
    language: category ? CATEGORY[category]?.format : undefined,
    automaticLayout: true,
    theme: theme.current.value.dark ? 'vs-dark' : 'vs',
    readOnly: true,
  })
  loadPayload()
})

async function loadPayload() {
  if (!editor) return
  key.value = await nav.fetchKeyPayload(subsystem, name, mode, version)
  editor.setValue(key.value?.payload ?? '')
}

watch(() => [subsystem, name, mode, version], loadPayload)

watch(
  () => theme.current.value.dark,
  (dark) => editor?.updateOptions({ theme: dark ? 'vs-dark' : 'vs' }),
)

onBeforeUnmount(() => editor?.dispose())
</script>
