import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { ApiError } from '@/api'

export type Level = 'success' | 'info' | 'warning' | 'error'

const LEVEL_ICON: Record<Level, string> = {
  success: 'mdi-check-circle',
  info: 'mdi-information',
  warning: 'mdi-alert',
  error: 'mdi-alert-circle',
}

type Message = { text: string; color: Level; prependIcon: string; timeout: number }

export const useSnackbarStore = defineStore('snackbar', () => {
  const messages = ref<Message[]>([])

  function notify(text: string, level: Level = 'info') {
    messages.value.push({ text, color: level, prependIcon: LEVEL_ICON[level], timeout: 5000 })
  }

  function notifyError(err: unknown) {
    notify(errorMessage(err), 'error')
  }

  return { messages, notify, notifyError }
})

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  if (err && typeof err === 'object' && 'detail' in err) {
    const { detail, status } = err as ApiError
    const text = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? d.msg : d)).join(', ') : undefined
    if (text) return status ? `${status}: ${text}` : text
  }
  return 'Something went wrong'
}
