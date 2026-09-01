import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import { CATEGORY } from '@/category'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']
type NodeOut = components['schemas']['NodeOut']
type NodeDetailOut = components['schemas']['NodeDetailOut']
type KeyOut = components['schemas']['KeyOut']

export type Row = {
  path: string
  title: string
  icon: string
  node: NodeOut
  isAlias: boolean
  ancestors: string[]
  children?: Row[]
}

function iconFor(node: NodeOut, isAlias: boolean): string {
  if (isAlias) return 'mdi-link-variant'
  if (node.category === null) return 'mdi-folder-outline'
  return CATEGORY[node.category]?.icon ?? 'mdi-file-outline'
}

function buildRows(nodes: NodeOut[], ancestors: string[], subsystemId: number): Row[] {
  return nodes.map((node) => {
    const path = `${ancestors.at(-1) ?? ''}/${node.alias}`
    const isAlias = node.subsystem_id !== subsystemId
    return {
      path,
      title: node.alias,
      icon: iconFor(node, isAlias),
      node,
      isAlias,
      ancestors,
      children:
        !isAlias && node.children.length
          ? buildRows(node.children, [...ancestors, path], subsystemId)
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
  const subsystems = ref<Subsystem[]>([])
  const selectedSubsystemId = ref<number | null>(null)

  const tree = ref<NodeOut[]>([])
  const treeSubsystemId = ref<number | null>(null)

  const openedRow = ref<string[]>([])
  const activatedRow = ref<string[]>([])

  const nodeDetail = ref<NodeDetailOut | null>(null)
  const nodeDetailCache = ref<Map<number, NodeDetailOut>>(new Map())

  async function fetchSubsystems() {
    if (subsystems.value.length) return
    const { data, error } = await api.GET('/api/subsystems/')
    if (error) throw error
    subsystems.value = data
  }

  function subsystemName(subsystemId: number): string | undefined {
    return subsystems.value.find((s) => s.id === subsystemId)?.name
  }

  async function fetchTree(subsystemId: number) {
    if (subsystemId === treeSubsystemId.value) return
    const { data, error } = await api.GET('/api/subsystems/{subsystem_id}/tree', {
      params: { path: { subsystem_id: subsystemId } },
    })
    if (error) throw error
    tree.value = data
    treeSubsystemId.value = subsystemId
  }

  async function fetchNodeByPath(subsystem: string, name: string) {
    const { data, error } = await api.GET('/api/nodes/by-path/{subsystem_name}/{node_name}', {
      params: { path: { subsystem_name: subsystem, node_name: name } },
    })
    if (error) throw error
    nodeDetail.value = data
    nodeDetailCache.value.set(data.id, data)
  }

  async function fetchNodeDetail(nodeId: number): Promise<NodeDetailOut | undefined> {
    const cached = nodeDetailCache.value.get(nodeId)
    if (cached) return cached
    const { data, error } = await api.GET('/api/nodes/{node_id}', {
      params: { path: { node_id: nodeId } },
    })
    if (error) throw error
    nodeDetailCache.value.set(nodeId, data)
    return data
  }

  async function fetchKeyPayload(
    subsystem: string,
    name: string,
    mode: string,
    version: number,
  ): Promise<KeyOut | undefined> {
    const { data, error } = await api.GET(
      '/api/keys/{subsystem_name}/{node_name}/{mode_name}/{version}',
      {
        params: {
          path: { subsystem_name: subsystem, node_name: name, mode_name: mode, version },
        },
      },
    )
    if (error) throw error
    return data
  }

  const rows = computed<Row[]>(() =>
    selectedSubsystemId.value ? buildRows(tree.value, [], selectedSubsystemId.value) : [],
  )

  function findRow(predicate: (row: Row) => boolean): Row | undefined {
    for (const row of walk(rows.value)) if (predicate(row)) return row
  }

  function findRowByNodeId(nodeId: number): Row | undefined {
    return findRow((r) => !r.isAlias && r.node.id === nodeId)
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

  // Where a row lives in the URL: scalars are addressed via their parent + a #hash.
  function routeForRow(row: Row): { subsystem: string; name: string; hash?: string } | undefined {
    if (row.node.category !== 'scalar') {
      const subsystem = subsystemName(row.node.subsystem_id)
      return subsystem ? { subsystem, name: row.node.name } : undefined
    }
    const parentPath = row.ancestors.at(-1)
    const parent = parentPath ? findRow((r) => r.path === parentPath) : undefined
    const subsystem = parent && subsystemName(parent.node.subsystem_id)
    return parent && subsystem ? { subsystem, name: parent.node.name, hash: `#${row.title}` } : undefined
  }

  function goToName(name: string) {
    const row = findRow((r) => !r.isAlias && r.node.name === name)
    if (!row) return
    const opened = [...row.ancestors]
    if (row.children) opened.push(row.path)
    openedRow.value = opened
    activatedRow.value = [row.path]
  }

  return {
    subsystems,
    selectedSubsystemId,
    openedRow,
    activatedRow,
    nodeDetail,
    rows,
    fetchSubsystems,
    subsystemName,
    fetchTree,
    fetchNodeByPath,
    fetchNodeDetail,
    fetchKeyPayload,
    findRow,
    findRowByNodeId,
    routeForRow,
    goToName,
  }
})
