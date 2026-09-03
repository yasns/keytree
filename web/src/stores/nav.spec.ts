import { describe, expect, it } from 'vitest'
import { encodeBundlePath, parseBundlePath } from './nav'
import type { components } from '@/api-types'

type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']

function child(alias: string): KeyChildMetaOut {
  return {
    alias,
    label: '',
    node_id: 0,
    node_name: '',
    subsystem_name: '',
    category: null,
    mode_name: '',
    version: 0,
    created_by: '',
    created_at: '',
    comment: '',
  }
}

describe('bundle path encoding', () => {
  it('round-trips a plain path', () => {
    const path = [child('foo'), child('bar')]
    expect(parseBundlePath(encodeBundlePath(path))).toEqual(['foo', 'bar'])
  })

  it('round-trips an alias containing a slash', () => {
    const path = [child('a/b'), child('c')]
    expect(parseBundlePath(encodeBundlePath(path))).toEqual(['a/b', 'c'])
  })

  it('parses undefined as empty', () => {
    expect(parseBundlePath(undefined)).toEqual([])
  })
})
