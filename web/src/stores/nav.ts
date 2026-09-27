import { type Component, computed, ref, shallowRef, watch } from 'vue'
import { defineStore } from 'pinia'
import { api, unwrap, type ApiError } from '@/api'
import { iconFor, sortByKind } from '@/category'
import { useChangesStore } from '@/stores/changes'
import { useSnackbarStore } from '@/stores/snackbar'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']
type TreeOut = components['schemas']['TreeOut']
type NamespaceOut = components['schemas']['NamespaceOut']
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

async function catch404<T>(p: Promise<T>, fallback: T): Promise<T> {
  try {
    return await p
  } catch (e) {
    if ((e as ApiError).status === 404) return fallback
    throw e
  }
}

/** The key filling a child alias, or undefined when the alias is empty */
export function childLocator(child: KeyChildMetaOut): BundleRoot | undefined {
  if (child.mode_name === null || child.version === null) return undefined
  return {
    subsystem: child.subsystem_name,
    name: child.namespace_name,
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
  namespace: TreeOut
  isAlias: boolean
  ancestors: string[]
  children?: Row[]
}

function buildRows(namespaces: TreeOut[], ancestors: string[], subsystemId: number): Row[] {
  const withAlias = namespaces.map((namespace) => ({
    namespace,
    isAlias: namespace.subsystem_id !== subsystemId,
  }))
  return sortByKind(withAlias, ({ namespace, isAlias }) => ({
    alias: namespace.alias,
    category: namespace.category,
    isAlias,
  })).map(({ namespace, isAlias }) => {
    const path = `${ancestors.at(-1) ?? ''}/${namespace.alias}`
    return {
      path,
      title: namespace.alias,
      icon: iconFor(namespace, isAlias),
      namespace,
      isAlias,
      ancestors,
      children:
        !isAlias && namespace.children.length
          ? buildRows(namespace.children, [...ancestors, path], subsystemId)
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

  const namespaceDetail = ref<NamespaceOut | null>(null)
  const namespaceDetailCache = ref<Map<number, NamespaceOut>>(new Map())

  const pendingNamespaceId = ref<number | null>(null)
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

  async function fetchNamespaceByPath(subsystem: string, name: string) {
    const data = unwrap(
      await api.GET('/api/namespaces/by-path/{subsystem_name}/{namespace_name}', {
        params: { path: { subsystem_name: subsystem, namespace_name: name } },
      }),
    )
    namespaceDetail.value = data
    namespaceDetailCache.value.set(data.id, data)
  }

  /** Dedupes concurrent fetches across columns sharing a namespace. */
  const namespaceDetailPending = new Map<number, Promise<NamespaceOut>>()

  async function fetchNamespaceDetail(namespaceId: number): Promise<NamespaceOut | undefined> {
    const cached = namespaceDetailCache.value.get(namespaceId)
    if (cached) return cached
    const pending = namespaceDetailPending.get(namespaceId)
    if (pending) return pending
    const request = api
      .GET('/api/namespaces/{namespace_id}', { params: { path: { namespace_id: namespaceId } } })
      .then((res) => {
        const data = unwrap(res)
        namespaceDetailCache.value.set(namespaceId, data)
        return data
      })
      .finally(() => namespaceDetailPending.delete(namespaceId))
    namespaceDetailPending.set(namespaceId, request)
    return request
  }

  /** Bumped by refreshKeys; watch alongside own props to reload. */
  const keysToken = ref(0)

  /** Clears caches, reloads current namespace: committed versions show up. */
  async function refreshKeys() {
    namespaceDetailCache.value.clear()
    namespaceDetailPending.clear()
    keysToken.value++
    if (namespaceDetail.value)
      await fetchNamespaceByPath(namespaceDetail.value.subsystem_name, namespaceDetail.value.name)
  }

  /** So components sharing a namespace don't each fire their own. */
  const modesByPathPending = new Map<string, Promise<ModeOut[]>>()

  async function fetchModesByPath(subsystem: string, name: string): Promise<ModeOut[]> {
    const cached = [...namespaceDetailCache.value.values()].find(
      (n) => n.subsystem_name === subsystem && n.name === name,
    )
    if (cached) return cached.modes
    const cacheKey = `${subsystem}/${name}`
    const pending = modesByPathPending.get(cacheKey)
    if (pending) return pending
    const request = api
      .GET('/api/namespaces/by-path/{subsystem_name}/{namespace_name}', {
        params: { path: { subsystem_name: subsystem, namespace_name: name } },
      })
      .then((res) => {
        const data = unwrap(res)
        namespaceDetailCache.value.set(data.id, data)
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
    return catch404(
      api
        .GET('/api/keys/{subsystem_name}/{namespace_name}/{mode_name}/{version}', {
          params: {
            path: { subsystem_name: subsystem, namespace_name: name, mode_name: mode, version },
          },
        })
        .then(unwrap),
      undefined,
    )
  }

  async function fetchKeyChildren(
    subsystem: string,
    name: string,
    mode: string,
    version: number,
  ): Promise<KeyChildMetaOut[]> {
    const children = await catch404(
      api
        .GET('/api/keys/{subsystem_name}/{namespace_name}/{mode_name}/{version}/children', {
          params: {
            path: { subsystem_name: subsystem, namespace_name: name, mode_name: mode, version },
          },
        })
        .then(unwrap),
      [],
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
    return changes.overlayStagedChild(
      changes.stagedForMode(parent.subsystem, parent.name, parent.mode),
      child,
    )
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
      const child = locator.pending ? stagedChild(locator, found) : found
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

  function findRowByNamespaceId(namespaceId: number): Row | undefined {
    return findRow((r) => !r.isAlias && r.namespace.id === namespaceId)
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
    const row = findRow((r) => !r.isAlias && r.namespace.name === name)
    if (!row) return

    activatedRow.value = [row.path]
  }

  async function goToAlias(namespace: TreeOut) {
    await fetchTree(namespace.subsystem_id)
    selectedSubsystemId.value = namespace.subsystem_id
    goToName(namespace.name)
    const name = subsystemName(namespace.subsystem_id)
    snackbar.notify(
      `You are editing ${namespace.name} in ${name ? subsystemDisplayName(name) : 'another subsystem'}`,
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
    namespaceDetail,
    namespaceDetailCache,
    pendingNamespaceId,
    bundleRoot,
    bundlePath,
    preDiffLocation,
    keysToken,
    rows,
    fetchSubsystems,
    subsystemName,
    subsystemDisplayName,
    fetchTree,
    fetchNamespaceByPath,
    fetchNamespaceDetail,
    refreshKeys,
    fetchModesByPath,
    fetchKeyPayload,
    fetchKeyChildren,
    markPathStaged,
    resolveBundlePath,
    findRow,
    findRowByNamespaceId,
    goToName,
    goToAlias,
  }
})
