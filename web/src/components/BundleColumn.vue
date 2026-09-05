<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <KeyMetadata
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :payload="payload"
    ></KeyMetadata>

    <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
      <v-list v-if="children" class="py-0">
        <v-list-item
          v-for="child in children"
          :key="child.alias"
          :active="child.alias === selectedAlias"
          @click="emit('select', child)"
          class="py-2"
        >
          <div class="d-flex flex-column ga-1">
            <div class="d-flex align-center ga-1">
              <v-icon :icon="iconFor(child, false)" size="x-small"></v-icon>

              <span class="text-title-small">{{ child.alias }}</span>
            </div>

            <v-select
              v-if="child.category === 'scalar'"
              :model-value="scalarValues.get(child.alias)"
              :items="scalarOptionsCache.get(scalarKey(child)) ?? []"
              placeholder="Select value"
              density="compact"
              hide-details
              @click.stop
              @update:model-value="(v) => scalarValues.set(child.alias, v)"
            ></v-select>
            <v-select
              v-else
              :model-value="child.mode_name"
              :items="
                modeOptions(child).map((m) => ({
                  title: `${m.name}/v${m.versions[0]}`,
                  value: m.name,
                }))
              "
              density="compact"
              hide-details
              disabled
              @click.stop
            ></v-select>
          </div>
        </v-list-item>
      </v-list>

      <Spinner v-else></Spinner>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useNavStore } from '@/stores/nav'
import { iconFor } from '@/category'
import { resolveScalarOptions } from '@/scalar'
import type { components } from '@/api-types'
import KeyMetadata from './KeyMetadata.vue'
import Spinner from './Spinner.vue'

type KeyOut = components['schemas']['KeyOut']
type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']
type ModeOut = components['schemas']['ModeOut']

const props = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  selectedAlias?: string
}>()

const emit = defineEmits<{ select: [child: KeyChildMetaOut] }>()

const nav = useNavStore()

const payload = ref<KeyOut>()
const children = ref<KeyChildMetaOut[]>()

// Scalar option lists for this column
const scalarOptionsCache = reactive(new Map<string, string[]>())
const scalarOptionsRequested = new Set<string>()

// Selected scalar dropdown values for this column
const scalarValues = reactive(new Map<string, string>())

function scalarKey(child: KeyChildMetaOut): string {
  return `${child.subsystem_name}/${child.node_name}`
}

function ensureScalarOptions(child: KeyChildMetaOut) {
  const key = scalarKey(child)
  if (scalarOptionsRequested.has(key)) return
  scalarOptionsRequested.add(key)
  resolveScalarOptions(child.subsystem_name, child.node_name)
    .then((options) => scalarOptionsCache.set(key, options))
    .catch(() => scalarOptionsRequested.delete(key))
}

// Mode/version options for each row
const modesCache = reactive(new Map<number, ModeOut[]>())
const modesRequested = new Set<number>()

function ensureModes(nodeId: number) {
  if (modesRequested.has(nodeId)) return
  modesRequested.add(nodeId)
  nav
    .fetchNodeDetail(nodeId)
    .then((detail) => {
      if (detail) modesCache.set(nodeId, detail.modes)
    })
    .catch(() => modesRequested.delete(nodeId))
}

function modeOptions(child: KeyChildMetaOut): ModeOut[] {
  return modesCache.get(child.node_id) ?? []
}

let loadToken = 0

async function load() {
  payload.value = undefined
  children.value = undefined
  scalarValues.clear()
  const token = ++loadToken
  const [p, c] = await Promise.all([
    nav.fetchKeyPayload(props.subsystem, props.name, props.mode, props.version),
    nav.fetchKeyChildren(props.subsystem, props.name, props.mode, props.version),
  ])
  if (token !== loadToken) return
  payload.value = p
  children.value = c
  for (const child of c) {
    if (child.category === 'scalar') ensureScalarOptions(child)
    else ensureModes(child.node_id)
  }
}

watch(() => [props.subsystem, props.name, props.mode, props.version], load, { immediate: true })
</script>
