import { describe, it, expect, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'

describe('App', () => {
  it('renders the api health, fetched from /api/health', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', environment: 'test', commit: 'abc123' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/health')
    expect(wrapper.text()).toContain('"status": "ok"')
    expect(wrapper.text()).toContain('"environment": "test"')
    expect(wrapper.text()).toContain('"commit": "abc123"')
  })

  it('reports an unreachable api instead of blanking', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('boom')))

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.text()).toContain('unreachable: boom')
  })
})
