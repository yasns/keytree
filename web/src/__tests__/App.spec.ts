import { describe, it, expect, vi } from 'vitest'
import { createPinia } from 'pinia'

import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'

function mountApp() {
  return mount(App, { global: { plugins: [createPinia()] } })
}

function mockAuthenticatedFetch(healthImpl: (url: string) => Promise<unknown>) {
  return vi.fn<(url: string) => Promise<unknown>>(async (url) => {
    if (url === '/api/user/claims') {
      return { type: 'basic', json: async () => ({ claims: { given_name: 'Ada' } }) }
    }
    if (url.startsWith('/api/health/')) return healthImpl(url)
    throw new Error(`unexpected fetch: ${url}`)
  })
}

describe('App', () => {
  it('renders the claims name and both health probes once authenticated', async () => {
    const fetchMock = mockAuthenticatedFetch(async (url) => ({
      ok: true,
      json: async () =>
        url.endsWith('/live')
          ? { status: 'ok', environment: 'test', commit: 'abc123' }
          : { status: 'ok', applied_revisions: ['tree_base'] },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountApp()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/user/claims', { redirect: 'manual' })
    expect(fetchMock).toHaveBeenCalledWith('/api/health/live')
    expect(fetchMock).toHaveBeenCalledWith('/api/health/ready')
    expect(wrapper.text()).toContain('Hello Ada!')
    expect(wrapper.text()).toContain('"commit":"abc123"')
    expect(wrapper.text()).toContain('"applied_revisions":["tree_base"]')
  })

  it('reports an unreachable api instead of blanking', async () => {
    const fetchMock = mockAuthenticatedFetch(async () => {
      throw new Error('boom')
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountApp()
    await flushPromises()

    expect(wrapper.text()).toContain('unreachable: boom')
  })

  it('surfaces a failing readiness probe', async () => {
    const fetchMock = mockAuthenticatedFetch(async (url) =>
      url.endsWith('/ready') ? { ok: false, status: 503 } : { ok: true, json: async () => ({}) },
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountApp()
    await flushPromises()

    expect(wrapper.text()).toContain('unreachable: HTTP 503')
  })

  it('redirects to auth with the current page as redirect_uri when unauthenticated', async () => {
    const fetchMock = vi.fn<() => Promise<unknown>>().mockResolvedValue({
      type: 'opaqueredirect',
    })
    vi.stubGlobal('fetch', fetchMock)
    const location = { href: 'http://localhost:5173/some/page' }
    vi.stubGlobal('location', location)

    const wrapper = mountApp()
    await flushPromises()

    expect(location.href).toBe(
      '/api/auth/token_request?redirect_uri=http%3A%2F%2Flocalhost%3A5173%2Fsome%2Fpage',
    )
    expect(wrapper.text()).toBe('')
  })
})
