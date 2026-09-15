import { watch } from 'vue'
import { useTheme } from 'vuetify'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'

// Module-level: runs once no matter how many editors/diff editors get created.
;(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
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
