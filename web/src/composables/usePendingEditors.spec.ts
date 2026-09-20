import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { usePendingEditors } from './usePendingEditors'

vi.mock('@/api', () => ({
  api: {
    GET: vi
      .fn<() => Promise<{ data: unknown[]; response: { ok: boolean } }>>()
      .mockResolvedValue({ data: [{ cern_login: 'alice' }], response: { ok: true } }),
  },
  unwrap: ({ data }: { data: unknown }) => data,
}))

import { api } from '@/api'

function host(modeId: ReturnType<typeof ref<number | undefined>>) {
  return defineComponent({
    setup() {
      const editors = usePendingEditors(modeId)
      return { editors }
    },
    template: '<div>{{ editors.length }}</div>',
  })
}

describe('usePendingEditors', () => {
  it('shares one fetch across concurrent callers for the same mode', async () => {
    const modeId = ref<number | undefined>(1)
    const a = mount(host(modeId))
    const b = mount(host(modeId))
    await vi.waitFor(() => expect(a.text()).toBe('1'))
    expect(b.text()).toBe('1')
    expect(api.GET).toHaveBeenCalledTimes(1)

    a.unmount()
    b.unmount()
  })
})
