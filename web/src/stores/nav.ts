import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { components } from '@/api-types'

type Subsystem = components['schemas']['SubsystemOut']
type NodeOut = components['schemas']['NodeOut']

export const useNavStore = defineStore('nav', () => {
  const subsystems = ref<Subsystem[]>([])
  const selectedSubsystemId = ref<number | null>(null)

  const tree = ref<NodeOut[]>([])
  const treeSubsystemId = ref<number | null>(null)

  const openedRow = ref<string[]>([])
  const activatedRow = ref<string[]>([])

  async function fetchSubsystems() {
    const { data, error } = await api.GET('/api/subsystems/')
    if (error) throw error
    subsystems.value = data
  }

  async function fetchTree(subsystemId: number) {
    const { data, error } = await api.GET('/api/subsystems/{subsystem_id}/tree', {
      params: { path: { subsystem_id: subsystemId } },
    })
    if (error) throw error
    tree.value = data
    treeSubsystemId.value = subsystemId
  }

  return {
    subsystems,
    selectedSubsystemId,
    tree,
    treeSubsystemId,
    openedRow,
    activatedRow,
    fetchSubsystems,
    fetchTree,
  }
})
