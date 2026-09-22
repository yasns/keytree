import { describe, expect, it } from 'vitest'
import { bundleDiffCounts, lineDiffCounts } from './useDiff'

describe('lineDiffCounts', () => {
  it('counts pure additions', () => {
    expect(lineDiffCounts('', 'a\nb')).toEqual({ added: 2, removed: 0 })
  })

  it('counts pure removals', () => {
    expect(lineDiffCounts('a\nb', '')).toEqual({ added: 0, removed: 2 })
  })

  it('counts only the changed lines around a shared middle', () => {
    expect(lineDiffCounts('a\nb\nc', 'x\nb\ny')).toEqual({ added: 2, removed: 2 })
  })

  it('is zero/zero for identical text', () => {
    expect(lineDiffCounts('a\nb', 'a\nb')).toEqual({ added: 0, removed: 0 })
  })
})

describe('bundleDiffCounts', () => {
  it('counts an added alias', () => {
    expect(bundleDiffCounts({ a: 1 }, { a: 1, b: 2 })).toEqual({ added: 1, removed: 0 })
  })

  it('counts a removed alias', () => {
    expect(bundleDiffCounts({ a: 1, b: 2 }, { a: 1 })).toEqual({ added: 0, removed: 1 })
  })

  it('counts a retarget as both an add and a remove', () => {
    expect(bundleDiffCounts({ a: 1 }, { a: 2 })).toEqual({ added: 1, removed: 1 })
  })

  it('treats a null target as a self-reference distinct from any ancestor id', () => {
    expect(bundleDiffCounts({ a: 1 }, { a: null })).toEqual({ added: 1, removed: 1 })
  })

  it('is zero/zero for an unchanged bundle', () => {
    expect(bundleDiffCounts({ a: 1, b: 2 }, { a: 1, b: 2 })).toEqual({ added: 0, removed: 0 })
  })
})
