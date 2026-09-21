import { type Component, computed, ref, shallowRef, watch } from 'vue'
import { defineStore } from 'pinia'
import { api, unwrap } from '@/api'
import { iconFor, sortByKind } from '@/category'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']
type TreeOut = components['schemas']['TreeOut']
type VertexOut = components['schemas']['VertexOut']
type ModeOut = components['schemas']['ModeOut']
type KeyOut = components['schemas']['KeyOut']
type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']

export type BundleRoot = {
  subsystem: string
  name: string
  mode: string
  version: number
  // true when `version` is the mode's staged edit, not a committed key
  pending: boolean
}

/** The key filling a child alias, or undefined when the alias is empty */
export function childLocator(child: KeyChildMetaOut): BundleRoot | undefined {
  if (child.mode_name === null || child.version === null) return undefined
  return {
    subsystem: child.subsystem_name,
    name: child.vertex_name,
    mode: child.mode_name,
    version: child.version,
    // no key id means the version this changeset will produce
    pending: child.id === null,
  }
}

export type Row = {
  path: string
  title: string
  icon: string
  vertex: TreeOut
  isAlias: boolean
  ancestors: string[]
  children?: Row[]
}

function buildRows(vertices: TreeOut[], ancestors: string[], subsystemId: number): Row[] {
  const withAlias = vertices.map((vertex) => ({
    vertex,
    isAlias: vertex.subsystem_id !== subsystemId,
  }))
  return sortByKind(withAlias, ({ vertex, isAlias }) => ({
    alias: vertex.alias,
    category: vertex.category,
    isAlias,
  })).map(({ vertex, isAlias }) => {
    const path = `${ancestors.at(-1) ?? ''}/${vertex.alias}`
    return {
      path,
      title: vertex.alias,
      icon: iconFor(vertex, isAlias),
      vertex,
      isAlias,
      ancestors,
      children:
        !isAlias && vertex.children.length
          ? buildRows(vertex.children, [...ancestors, path], subsystemId)
          : undefined,
    }
  })
}

export function* walk(list: Row[]): Generator<Row> {
  for (const row of list) {
    yield row
    if (row.children) yield* walk(row.children)
  }
}

export const useNavStore = defineStore('nav', () => {
  const snackbar = useSnackbarStore()
  const subsystems = ref<Subsystem[]>([])
  const selectedSubsystemId = ref<number | null>(null)

  const tree = ref<TreeOut[]>([])
  const treeSubsystemId = ref<number | null>(null)

  const openedRow = ref<string[]>([])
  const activatedRow = ref<string[]>([])

  const activePanel = shallowRef<Component | null>(null)
  const subsystemMenuOpen = ref(false)

  const vertexDetail = ref<VertexOut | null>(null)
  const vertexDetailCache = ref<Map<number, VertexOut>>(new Map())

  const pendingVertexId = ref<number | null>(null)
  const bundleRoot = ref<BundleRoot | null>(null)
  const bundlePath = ref<KeyChildMetaOut[]>([])

  /** Full path to return to on comparison exit; set when comparison is entered. */
  const preDiffLocation = ref<string | null>(null)

  watch(bundleRoot, (next, prev) => {
    // same key, only version/pending relabeled: open path stays valid
    if (
      next &&
      prev &&
      next.subsystem === prev.subsystem &&
      next.name === prev.name &&
      next.mode === prev.mode
    )
      return
    bundlePath.value = []
  })

  async function fetchSubsystems() {
    if (subsystems.value.length) return
    subsystems.value = unwrap(await api.GET('/api/subsystems/'))
  }

  function subsystemName(subsystemId: number): string | undefined {
    return subsystems.value.find((s) => s.id === subsystemId)?.name
  }

  function subsystemDisplayName(name: string): string {
    const s = subsystems.value.find((s) => s.name === name)
    return s?.display_name ?? s?.name ?? name
  }

  async function fetchTree(subsystemId: number) {
    if (subsystemId === treeSubsystemId.value) return
    tree.value = unwrap(
      await api.GET('/api/subsystems/{subsystem_id}/tree', {
        params: { path: { subsystem_id: subsystemId } },
      }),
    )
    treeSubsystemId.value = subsystemId
  }

  async function fetchVertexByPath(subsystem: string, name: string) {
    const data = unwrap(
      await api.GET('/api/vertices/by-path/{subsystem_name}/{vertex_name}', {
        params: { path: { subsystem_name: subsystem, vertex_name: name } },
      }),
    )
    vertexDetail.value = data
    vertexDetailCache.value.set(data.id, data)
  }

  /** Dedupes concurrent fetches across columns sharing a vertex. */
  const vertexDetailPending = new Map<number, Promise<VertexOut>>()

  async function fetchVertexDetail(vertexId: number): Promise<VertexOut | undefined> {
    const cached = vertexDetailCache.value.get(vertexId)
    if (cached) return cached
    const pending = vertexDetailPending.get(vertexId)
    if (pending) return pending
    const request = api
      .GET('/api/vertices/{vertex_id}', { params: { path: { vertex_id: vertexId } } })
      .then((res) => {
        const data = unwrap(res)
        vertexDetailCache.value.set(vertexId, data)
        return data
      })
      .finally(() => vertexDetailPending.delete(vertexId))
    vertexDetailPending.set(vertexId, request)
    return request
  }

  /** Bumped by refreshKeys; watch alongside own props to reload. */
  const keysToken = ref(0)

  /** Clears caches, reloads current vertex: committed versions show up. */
  async function refreshKeys() {
    vertexDetailCache.value.clear()
    vertexDetailPending.clear()
    keysToken.value++
    if (vertexDetail.value)
      await fetchVertexByPath(vertexDetail.value.subsystem_name, vertexDetail.value.name)
  }

  /** So components sharing a vertex don't each fire their own. */
  const modesByPathPending = new Map<string, Promise<ModeOut[]>>()

  async function fetchModesByPath(subsystem: string, name: string): Promise<ModeOut[]> {
    const cached = [...vertexDetailCache.value.values()].find(
      (n) => n.subsystem_name === subsystem && n.name === name,
    )
    if (cached) return cached.modes
    const cacheKey = `${subsystem}/${name}`
    const pending = modesByPathPending.get(cacheKey)
    if (pending) return pending
    const request = api
      .GET('/api/vertices/by-path/{subsystem_name}/{vertex_name}', {
        params: { path: { subsystem_name: subsystem, vertex_name: name } },
      })
      .then((res) => {
        const data = unwrap(res)
        vertexDetailCache.value.set(data.id, data)
        return data.modes
      })
      .finally(() => modesByPathPending.delete(cacheKey))
    modesByPathPending.set(cacheKey, request)
    return request
  }

  async function fetchKeyPayload(
    subsystem: string,
    name: string,
    mode: string,
    version: number,
  ): Promise<KeyOut | undefined> {
    return unwrap(
      await api.GET('/api/keys/{subsystem_name}/{vertex_name}/{mode_name}/{version}', {
        params: {
          path: { subsystem_name: subsystem, vertex_name: name, mode_name: mode, version },
        },
      }),
    )
  }

  async function fetchKeyChildren(
    subsystem: string,
    name: string,
    mode: string,
    version: number,
  ): Promise<KeyChildMetaOut[]> {
    const children = unwrap(
      await api.GET('/api/keys/{subsystem_name}/{vertex_name}/{mode_name}/{version}/children', {
        params: {
          path: { subsystem_name: subsystem, vertex_name: name, mode_name: mode, version },
        },
      }),
    )
    return sortByKind(children, (child) => ({
      alias: child.alias,
      category: child.category,
      isAlias: child.subsystem_name !== subsystem,
    }))
  }

  /** Pending version has no key of its own: fetch rows from the committed source. */
  function sourceOf(locator: BundleRoot): BundleRoot {
    if (!locator.pending) return locator
    const based = useChangesStore().stagedForMode(
      locator.subsystem,
      locator.name,
      locator.mode,
    )?.based_on
    if (!based) return locator
    return { ...locator, mode: based.mode_name, version: based.version }
  }

  /** Repoints a committed child at whatever its parent's staged edit proposes for that alias. */
  function stagedChild(parent: BundleRoot, child: KeyChildMetaOut): KeyChildMetaOut {
    const changes = useChangesStore()
    const proposed = changes.stagedForMode(
      parent.subsystem,
      parent.name,
      parent.mode,
    )?.proposed_children
    if (!proposed) return child
    const target = proposed[child.alias]
    // alias absent from map means changeset clears it
    if (target === undefined) return { ...child, id: null, mode_name: null, version: null }
    if (target)
      return { ...child, id: target.key_id, mode_name: target.mode_name, version: target.version }
    // null means key this changeset produces; read off the staged edit
    const edit = changes.stagedForVertex(child.subsystem_name, child.vertex_name)
    return edit
      ? { ...child, id: null, mode_name: edit.mode_name, version: edit.expected_version }
      : child
  }

  /** Points a bundle-path entry at its own newly staged version. */
  function markPathStaged(index: number, version: number) {
    const entry = bundlePath.value[index]
    if (!entry) return
    bundlePath.value.splice(index, 1, { ...entry, id: null, version })
  }

  async function resolveBundlePath(
    root: BundleRoot,
    aliases: string[],
  ): Promise<KeyChildMetaOut[]> {
    const path: KeyChildMetaOut[] = []
    let locator: BundleRoot = root
    for (const alias of aliases) {
      const source = sourceOf(locator)
      const children = await fetchKeyChildren(
        source.subsystem,
        source.name,
        source.mode,
        source.version,
      )
      const found = children.find((c) => c.alias === alias)
      if (!found) break
      const child = stagedChild(locator, found)
      path.push(child)
      if (child.category !== null) break // leaf: nothing further to descend into
      const next = childLocator(child)
      if (!next) break // alias left empty by this key: no child bundle to open
      locator = next
    }
    return path
  }

  const rows = computed<Row[]>(() =>
    treeSubsystemId.value !== null ? buildRows(tree.value, [], treeSubsystemId.value) : [],
  )

  function findRow(predicate: (row: Row) => boolean): Row | undefined {
    for (const row of walk(rows.value)) if (predicate(row)) return row
  }

  function findRowByVertexId(vertexId: number): Row | undefined {
    return findRow((r) => !r.isAlias && r.vertex.id === vertexId)
  }

  watch(
    selectedSubsystemId,
    async (id) => {
      if (id === treeSubsystemId.value) return
      openedRow.value = []
      activatedRow.value = []
      if (id === null) {
        tree.value = []
        treeSubsystemId.value = null
        return
      }
      await fetchTree(id)
    },
    { immediate: true },
  )

  function goToName(name: string) {
    const row = findRow((r) => !r.isAlias && r.vertex.name === name)
    if (!row) return
    const opened = [...row.ancestors]
    if (row.children) opened.push(row.path)
    openedRow.value = opened
    activatedRow.value = [row.path]
  }

  async function goToAlias(vertex: TreeOut) {
    await fetchTree(vertex.subsystem_id)
    selectedSubsystemId.value = vertex.subsystem_id
    goToName(vertex.name)
    const name = subsystemName(vertex.subsystem_id)
    snackbar.notify(
      `You are editing ${vertex.name} in ${name ? subsystemDisplayName(name) : 'another subsystem'}`,
      'info',
    )
  }

  return {
    subsystems,
    selectedSubsystemId,
    openedRow,
    activatedRow,
    activePanel,
    subsystemMenuOpen,
    vertexDetail,
    vertexDetailCache,
    pendingVertexId,
    bundleRoot,
    bundlePath,
    preDiffLocation,
    keysToken,
    rows,
    fetchSubsystems,
    subsystemName,
    subsystemDisplayName,
    fetchTree,
    fetchVertexByPath,
    fetchVertexDetail,
    refreshKeys,
    fetchModesByPath,
    fetchKeyPayload,
    fetchKeyChildren,
    markPathStaged,
    resolveBundlePath,
    findRow,
    findRowByVertexId,
    goToName,
    goToAlias,
  }
})
