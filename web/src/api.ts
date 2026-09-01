import createClient from 'openapi-fetch'
import type { paths } from './api-types'

export const api = createClient<paths>({ baseUrl: '/' })

export type ApiError = { detail: unknown; status: number }

// Normalizes a failed response into `{ detail, status }`
function apiError(error: unknown, response: Response): ApiError {
  const detail =
    error && typeof error === 'object' && 'detail' in error
      ? (error as { detail: unknown }).detail
      : (typeof error === 'string' && error) || response.statusText || `HTTP ${response.status}`
  return { detail, status: response.status }
}

export function unwrap<T>({ data, error, response }: { data?: T; error?: unknown; response: Response }): T {
  if (error || !response.ok) throw apiError(error, response)
  return data as T
}
