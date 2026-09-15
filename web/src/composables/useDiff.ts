import { reactive, onBeforeUnmount } from 'vue'
import type { ScrollSide } from './useSyncedScroll'
import type { components } from '@/api-types'

type KeyOut = components['schemas']['KeyOut']
type StagedEditOut = components['schemas']['StagedEditOut']
type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']

export type ColumnDiffData = {
  subsystem?: string
  name?: string
  mode: string
  version: number
  pending: boolean
  payload?: KeyOut
  staged?: StagedEditOut
  children?: KeyChildMetaOut[]
}

function otherSide(side: ScrollSide): ScrollSide {
  return side === 'left' ? 'right' : 'left'
}

export type DiffRun = { text: string; changed: boolean }

/** Splits on the common prefix/suffix so only the differing middle is marked changed. */
export function runsFor(own: string, other: string | undefined): DiffRun[] {
  if (other === undefined || own === other) return own ? [{ text: own, changed: false }] : []
  let start = 0
  const minLen = Math.min(own.length, other.length)
  while (start < minLen && own[start] === other[start]) start++
  // Equal lengths only: a full suffix match would otherwise mask a real diff (e.g. "5" vs "15").
  const maxSuffixLen = own.length === other.length ? minLen - start : minLen - start - 1
  let suffixLen = 0
  while (
    suffixLen < maxSuffixLen &&
    own[own.length - 1 - suffixLen] === other[other.length - 1 - suffixLen]
  ) {
    suffixLen++
  }
  const ownEnd = own.length - suffixLen
  const runs: DiffRun[] = []
  if (start > 0) runs.push({ text: own.slice(0, start), changed: false })
  if (ownEnd > start) runs.push({ text: own.slice(start, ownEnd), changed: true })
  if (ownEnd < own.length) runs.push({ text: own.slice(ownEnd), changed: false })
  return runs
}

export function sideHighlightClass(side: ScrollSide | undefined): string | undefined {
  if (side === 'left') return 'diff-highlight-left'
  if (side === 'right') return 'diff-highlight-right'
  return undefined
}

/** Lets same-depth columns on each side publish their data and read the counterpart's back. */
export function useDiff() {
  const entries = reactive(new Map<string, ColumnDiffData>())

  function publish(depth: number, side: ScrollSide, data: ColumnDiffData) {
    entries.set(`${side}:col${depth}`, data)
  }

  function clear(depth: number, side: ScrollSide) {
    entries.delete(`${side}:col${depth}`)
  }

  function counterpart(depth: number, side: ScrollSide): ColumnDiffData | undefined {
    return entries.get(`${otherSide(side)}:col${depth}`)
  }

  onBeforeUnmount(() => entries.clear())

  return { publish, clear, counterpart }
}
