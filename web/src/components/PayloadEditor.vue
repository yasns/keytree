<template>
  <div ref="editorElem" class="h-100"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTheme } from 'vuetify'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import { useNavStore } from '@/stores/nav'
import { CATEGORY } from '@/category'

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
let editor: monaco.editor.IStandaloneCodeEditor | undefined

onMounted(() => {
  if (!editorElem.value) return
  const category = nav.nodeDetail?.category
  editor = monaco.editor.create(editorElem.value, {
    value: '',
    language: category ? CATEGORY[category]?.format : undefined,
    automaticLayout: true,
    theme: theme.current.value.dark ? 'vs-dark' : 'vs',
  })
  loadPayload()
})

async function loadPayload() {
  if (!editor) return
  const key = await nav.fetchKeyPayload(subsystem, name, mode, version)
  editor.setValue(key?.payload ?? '')
}

watch(() => [subsystem, name, mode, version], loadPayload)

watch(
  () => theme.current.value.dark,
  (dark) => editor?.updateOptions({ theme: dark ? 'vs-dark' : 'vs' }),
)

onBeforeUnmount(() => editor?.dispose())
</script>
