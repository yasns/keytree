import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './api-types'

// Stop at the same-origin redirect to avoid CORS issues
const reauth: Middleware = {
  onResponse({ response }) {
    if (response.type === 'opaqueredirect') {
      const returnTo = encodeURIComponent(window.location.href)
      window.location.href = `/api/auth/token_request?redirect_uri=${returnTo}`
      return new Promise<Response>(() => {})
    }
  },
}

export const api = createClient<paths>({ baseUrl: '/', redirect: 'manual' })
api.use(reauth)

export type ApiError = { detail: unknown; status: number }

function apiError(error: unknown, response: Response): ApiError {
  const detail =
    error && typeof error === 'object' && 'detail' in error
      ? (error as { detail: unknown }).detail
      : (typeof error === 'string' && error) || response.statusText || `HTTP ${response.status}`
  return { detail, status: response.status }
}

export function unwrap<T>({
  data,
  error,
  response,
}: {
  data?: T
  error?: unknown
  response: Response
}): T {
  if (error || !response.ok) throw apiError(error, response)
  return data as T
}
