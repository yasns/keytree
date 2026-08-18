import { describe, it, expect, vi } from 'vitest'
import { createPinia } from 'pinia'

import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'

function mountApp() {
  return mount(App, { global: { plugins: [createPinia()] } })
}

function mockAuthenticatedFetch(healthImpl: () => Promise<unknown>) {
  return vi.fn(async (url: string) => {
    if (url === '/api/user/claims') {
      return { type: 'basic', json: async () => ({ claims: { given_name: 'Ada' } }) }
    }
    if (url === '/api/health') return healthImpl()
    throw new Error(`unexpected fetch: ${url}`)
  })
}

describe('App', () => {
  it('renders the claims name and api health once the session is authenticated', async () => {
    const fetchMock = mockAuthenticatedFetch(async () => ({
      ok: true,
      json: async () => ({ status: 'ok', environment: 'test', commit: 'abc123' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountApp()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/user/claims', { redirect: 'manual' })
    expect(fetchMock).toHaveBeenCalledWith('/api/health')
    expect(wrapper.text()).toContain('Hello Ada!')
    expect(wrapper.text()).toContain('"status": "ok"')
    expect(wrapper.text()).toContain('"environment": "test"')
    expect(wrapper.text()).toContain('"commit": "abc123"')
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

  it('redirects to auth with the current page as redirect_uri when unauthenticated', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ type: 'opaqueredirect' })
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
