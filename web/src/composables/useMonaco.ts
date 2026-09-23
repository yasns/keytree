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
export function createPayloadModel(
  value: string,
  format: string | null | undefined,
  category: string | null | undefined,
) {
  const language = languageFor(format)
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

/** Resolves once the yaml worker has posted markers for this model, or after a timeout (e.g. markers were already empty). */
export function waitForMarkers(model: monaco.editor.ITextModel): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      listener.dispose()
      clearTimeout(timeout)
      resolve()
    }
    const listener = monaco.editor.onDidChangeMarkers((uris) => {
      if (uris.some((uri) => uri.toString() === model.uri.toString())) finish()
    })
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
