<template>
  <v-list v-if="children.length" density="compact">
    <v-list-item
      v-for="child in children"
      :key="child.path"
      :data-row-name="child.title"
      :class="{ 'bg-highlight': isHighlighted(child) }"
    >
      <template v-slot:prepend>
        <v-icon :icon="child.icon" size="small"></v-icon>
      </template>

      <v-list-item-title>{{ child.title }}</v-list-item-title>

      <template v-slot:append>
        <div class="d-flex align-center ga-2" style="min-width: 480px">
          <v-autocomplete
            :model-value="child.node.category !== 'scalar' && enabled ? childLabel(child) : undefined"
            :items="child.node.category !== 'scalar' && childLabel(child) ? [childLabel(child)] : []"
            :disabled="!enabled"
            :label="child.node.category === 'scalar' ? undefined : 'key'"
            :placeholder="child.node.category === 'scalar' ? 'key' : undefined"
            density="compact"
            hide-details
          ></v-autocomplete>
          <CopyButton :text="enabled ? (childLabel(child) ?? '') : ''"></CopyButton>
          <v-btn
            v-if="child.node.category !== 'scalar'"
            icon="mdi-pencil-outline"
            size="small"
            density="comfortable"
            variant="tonal"
            :disabled="!enabled || !childRoute(child)"
            :to="enabled ? childRoute(child) : undefined"
          ></v-btn>
        </div>
      </template>
    </v-list-item>
  </v-list>
  <v-container fluid v-else>
    <p class="text-medium-emphasis">No children.</p>
  </v-container>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useNavStore, type Row } from '@/stores/nav'
import type { components } from '@/api-types'
import CopyButton from './CopyButton.vue'

type NodeDetailOut = components['schemas']['NodeDetailOut']

const { enabled } = defineProps<{
  enabled: boolean
}>()

const nav = useNavStore()
const route = useRoute()

const children = computed<Row[]>(() => {
  const detail = nav.nodeDetail
  if (!detail) return []
  return nav.findRowByNodeId(detail.id)?.children ?? []
})

// Non-scalar children need their own modes/versions, fetched lazily and cached per node id.
const childDetails = reactive(new Map<number, NodeDetailOut>())

watch(
  children,
  (rows) => {
    for (const row of rows) {
      if (row.node.category === 'scalar' || childDetails.has(row.node.id)) continue
      nav.fetchNodeDetail(row.node.id).then((detail) => {
        if (detail) childDetails.set(row.node.id, detail)
      })
    }
  },
  { immediate: true },
)

function defaultModeAndVersion(child: Row): { mode: string; version: number } | undefined {
  const detail = childDetails.get(child.node.id)
  const mode = detail?.modes[0]
  const version = mode?.versions[0]
  return mode && version !== undefined ? { mode: mode.name, version } : undefined
}

function childLabel(child: Row): string | undefined {
  const subsystem = nav.subsystemName(child.node.subsystem_id)
  const mv = defaultModeAndVersion(child)
  return mv && subsystem ? `${subsystem}/${child.node.name}/${mv.mode}/v${mv.version}` : undefined
}

function childRoute(child: Row) {
  const subsystem = nav.subsystemName(child.node.subsystem_id)
  const mv = defaultModeAndVersion(child)
  return mv && subsystem
    ? { name: 'node', params: { subsystem, name: child.node.name, mode: mv.mode, version: `v${mv.version}` } }
    : undefined
}

function isHighlighted(child: Row): boolean {
  return route.hash === `#${child.title}`
}

watch(
  () => route.hash,
  async (hash) => {
    if (!hash) return
    await nextTick()
    document
      .querySelector(`[data-row-name="${CSS.escape(hash.slice(1))}"]`)
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  },
  { immediate: true },
)
</script>

<style scoped>
.bg-highlight {
  background-color: rgba(var(--v-theme-primary), 0.12);
}
</style>
