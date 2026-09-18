import { watch } from 'vue'
import { useTheme } from 'vuetify'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import YamlWorker from './yaml.worker.js?worker'
import { configureMonacoYaml } from 'monaco-yaml'
import { schemas } from '@/schemas'
import { languageFor } from '@/category'

// Module-level: runs once no matter how many editors/diff editors get created.
;(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: (_: unknown, label: string) =>
    label === 'yaml' ? new YamlWorker() : new EditorWorker(),
}

configureMonacoYaml(monaco, { enableSchemaRequest: false, schemas })

let uid = 0

/** Schema selection is by model URI, not language, so payload editors need a real model. */
export function createPayloadModel(value: string, category: string | null | undefined) {
  const language = languageFor(category)
  const ext = language === 'yaml' ? 'yaml' : 'txt'
  return monaco.editor.createModel(
    value,
    language,
    monaco.Uri.parse(`inmemory://keytree/${uid++}/${category ?? 'general'}.${ext}`),
  )
}

/** Errors before warnings, then by line; each line labeled so severity reads at a glance. */
export function formatMarkers(markers: monaco.editor.IMarker[]): string[] {
  return [...markers]
    .sort((a, b) => b.severity - a.severity || a.startLineNumber - b.startLineNumber)
    .map(
      (m) =>
        `${m.severity === monaco.MarkerSeverity.Error ? 'Error' : 'Warning'} (line ${m.startLineNumber}): ${m.message}`,
    )
}

/** Runs payload through the yaml worker off-screen and resolves with the same messages the live editor would show. */
export function validatePayload(payload: string, category: string | null): Promise<string[]> {
  if (languageFor(category) !== 'yaml') return Promise.resolve([])
  const model = createPayloadModel(payload, category)
  return new Promise((resolve) => {
    const finish = () => {
      listener.dispose()
      clearTimeout(timeout)
      const markers = monaco.editor.getModelMarkers({ resource: model.uri, owner: 'yaml' })
      model.dispose()
      resolve(formatMarkers(markers))
    }
    const listener = monaco.editor.onDidChangeMarkers((uris) => {
      if (uris.some((uri) => uri.toString() === model.uri.toString())) finish()
    })
    // Falls back if the worker never reports a change, e.g. markers were already empty.
    const timeout = setTimeout(finish, 2000)
  })
}

type MonacoTheme = 'vs' | 'vs-dark'

function monacoTheme(dark: boolean): MonacoTheme {
  return dark ? 'vs-dark' : 'vs'
}

/** Monaco themes are process-global, so this sets it there and keeps it in sync with the app theme. */
export function useMonacoTheme(): MonacoTheme {
  const theme = useTheme()
  const initial = monacoTheme(theme.current.value.dark)
  monaco.editor.setTheme(initial)
  watch(
    () => theme.current.value.dark,
    (dark) => monaco.editor.setTheme(monacoTheme(dark)),
  )
  return initial
}
