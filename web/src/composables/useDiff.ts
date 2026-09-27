import { reactive, shallowReactive, onBeforeUnmount, watch } from 'vue'
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

/** Splits diff runs at a character index, so a label's mode/version tail can render separately from its head. */
export function splitRunsAt(runs: DiffRun[], index: number): [DiffRun[], DiffRun[]] {
  const head: DiffRun[] = []
  const tail: DiffRun[] = []
  let pos = 0
  for (const run of runs) {
    const end = pos + run.text.length
    if (end <= index) {
      head.push(run)
    } else if (pos >= index) {
      tail.push(run)
    } else {
      const cut = index - pos
      head.push({ text: run.text.slice(0, cut), changed: run.changed })
      tail.push({ text: run.text.slice(cut), changed: run.changed })
    }
    pos = end
  }
  return [head, tail]
}

/** Index of the 2nd "/" in a `subsystem/namespace/mode/vN` label, so the tail keeps the slash plus mode+version. */
export function labelTailStart(label: string): number {
  const first = label.indexOf('/')
  if (first < 0) return 0
  const second = label.indexOf('/', first + 1)
  return second < 0 ? 0 : second
}

/** Diff runs for a label, split into head/tail at `labelTailStart` so the mode+version stays visible. */
export function runsForLabel(own: string, other: string | undefined): [DiffRun[], DiffRun[]] {
  return splitRunsAt(runsFor(own, other), labelTailStart(own))
}

export type DiffCounts = { added: number; removed: number }

const MAX_DIFF_CELLS = 4_000_000

/** Classic unified-diff line counts (added/removed), via longest common subsequence length. */
export function lineDiffCounts(before: string, after: string): DiffCounts | undefined {
  const a = before ? before.split('\n') : []
  const b = after ? after.split('\n') : []
  // O(n*m) DP; bail out above MAX_DIFF_CELLS instead of freezing the main thread on a huge payload.
  if ((a.length + 1) * (b.length + 1) > MAX_DIFF_CELLS) return undefined
  let prevRow: number[] = Array.from({ length: b.length + 1 }, () => 0)
  let curRow: number[] = Array.from({ length: b.length + 1 }, () => 0)
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      curRow[j] =
        a[i] === b[j]
          ? (prevRow[j + 1] ?? 0) + 1
          : Math.max(prevRow[j + 1] ?? 0, curRow[j + 1] ?? 0)
    }
    ;[prevRow, curRow] = [curRow, prevRow]
  }
  const lcs = prevRow[0] ?? 0
  return { added: b.length - lcs, removed: a.length - lcs }
}

/** '+added -removed' aliases vs the ancestor. A retarget counts as both. */
export function bundleDiffCounts(
  ancestor: Record<string, number>,
  proposed: Record<string, number | null>,
): DiffCounts {
  const SELF = -1 // no null proposed target ("supplied by this changeset") ever matches a real ancestor id
  const resolved: Record<string, number> = {}
  for (const [alias, target] of Object.entries(proposed)) resolved[alias] = target ?? SELF
  const aliases = new Set([...Object.keys(ancestor), ...Object.keys(resolved)])
  let added = 0
  let removed = 0
  for (const alias of aliases) {
    if (ancestor[alias] === resolved[alias]) continue
    if (alias in ancestor) removed++
    if (alias in resolved) added++
  }
  return { added, removed }
}

export type KeyRef = {
  subsystem_name: string
  namespace_name: string
  mode_name: string
  version: number
}

/** A pending version has no key of its own: resolve to its staged edit's committed source, or its own ref otherwise. */
export function pendingSourceRef(
  pending: boolean | undefined,
  staged: { based_on?: { mode_name: string; version: number } | null } | undefined,
  mode: string,
  version: number,
): { mode: string; version: number } {
  const source = pending ? staged?.based_on : undefined
  return { mode: source?.mode_name ?? mode, version: source?.version ?? version }
}

/** A key's children, as alias -> child key id (entries with no child yet are dropped). */
export function childrenToIdMap(children: KeyChildMetaOut[]): Record<string, number> {
  return Object.fromEntries(
    children.filter((c) => c.id !== null).map((c) => [c.alias, c.id as number]),
  )
}

/** Dedupes repeated fetches for the same key ref, for the memoizer's lifetime. */
export function memoizeByRef<R>(fetch: (ref: KeyRef) => Promise<R>): (ref: KeyRef) => Promise<R> {
  const cache = new Map<string, Promise<R>>()
  return (ref) => {
    const key = `${ref.subsystem_name}/${ref.namespace_name}/${ref.mode_name}/${ref.version}`
    let result = cache.get(key)
    if (!result) {
      result = fetch(ref)
      cache.set(key, result)
    }
    return result
  }
}

/** Diff counts for a proposed payload/children against a specific key version. */
export async function diffAgainstRef(
  ref: KeyRef,
  proposedPayload: string | null,
  proposedChildrenMap: Record<string, number | null> | null,
  fetchPayload: (ref: KeyRef) => Promise<KeyOut | undefined>,
  fetchChildren: (ref: KeyRef) => Promise<KeyChildMetaOut[]>,
): Promise<DiffCounts | undefined> {
  if (proposedPayload !== null) {
    const before = (await fetchPayload(ref))?.payload ?? ''
    return lineDiffCounts(before, proposedPayload)
  }
  const refMap = childrenToIdMap(await fetchChildren(ref))
  return bundleDiffCounts(refMap, proposedChildrenMap ?? {})
}

/** Diff counts for a staged edit's proposal against its fork/copy source (or prior version). */
export function diffAgainstAncestor(
  edit: StagedEditOut | undefined,
  fetchPayload: (ref: KeyRef) => Promise<KeyOut | undefined>,
  fetchChildren: (ref: KeyRef) => Promise<KeyChildMetaOut[]>,
): Promise<DiffCounts | undefined> {
  const ancestor = edit?.based_on
  if (!edit || !ancestor) return Promise.resolve(undefined)
  const proposedChildrenMap = edit.proposed_children
    ? Object.fromEntries(
        Object.entries(edit.proposed_children).map(([alias, child]) => [
          alias,
          child?.key_id ?? null,
        ]),
      )
    : null
  return diffAgainstRef(
    {
      subsystem_name: edit.subsystem_name,
      namespace_name: edit.namespace_name,
      mode_name: ancestor.mode_name,
      version: ancestor.version,
    },
    edit.proposed_payload,
    proposedChildrenMap,
    fetchPayload,
    fetchChildren,
  )
}

/** A reactive cache of per-item async results, pruned and refilled whenever `source()` changes. */
export function useDiffCountCache<T, K, V>(
  source: () => T[],
  keyFn: (item: T) => K,
  load: (item: T) => Promise<V | undefined>,
) {
  const cache = shallowReactive(new Map<K, V>())

  async function ensure(item: T) {
    const key = keyFn(item)
    if (cache.has(key)) return
    try {
      const value = await load(item)
      if (value !== undefined) cache.set(key, value)
    } catch {
      // Decorative badge only; skip quietly on fetch failure.
    }
  }

  watch(
    source,
    (items) => {
      const keys = new Set(items.map(keyFn))
      for (const k of cache.keys()) {
        if (!keys.has(k)) cache.delete(k)
      }
      items.forEach((item) => void ensure(item))
    },
    { immediate: true },
  )

  return { get: (item: T) => cache.get(keyFn(item)) }
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
