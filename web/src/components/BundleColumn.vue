<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <KeyMetadata
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :payload="payload"
      :modified="dirty"
      :staged="staged"
    ></KeyMetadata>

    <EditorToolbar
      :dirty="dirty"
      :staged-comment="staged?.comment"
      @save="save"
      @discard="applyBaseline"
    ></EditorToolbar>

    <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
      <v-list v-if="children" class="py-0">
        <v-list-item
          v-for="child in children"
          :key="child.alias"
          :active="child.alias === selectedAlias"
          @click="emit('select', child)"
          class="py-2 px-2"
        >
          <div class="d-flex flex-column ga-1">
            <div class="d-flex align-center ga-1">
              <v-icon
                :icon="iconFor(child, child.subsystem_name !== subsystem)"
                size="x-small"
              ></v-icon>

              <span class="text-title-small">{{ child.alias }}</span>
            </div>

            <v-select
              v-if="child.category === 'external'"
              class="key-select"
              :model-value="externalChoice.get(child.alias)"
              :items="externalItems(child)"
              placeholder="Select key"
              density="compact"
              hide-details
              @click.stop
              @update:model-value="(v) => externalChoice.set(child.alias, v)"
            >
              <template #item="{ props: itemProps }">
                <v-list-item v-bind="itemProps" class="key-select"></v-list-item>
              </template>
            </v-select>
            <v-select
              v-else
              class="key-select"
              :model-value="childChoice.get(child.alias)?.mode"
              :items="modeItems(child)"
              placeholder="Select key"
              density="compact"
              hide-details
              @click.stop
              @update:model-value="(v) => onModeSelect(child, v)"
            >
              <template #item="{ props: itemProps }">
                <v-list-item v-bind="itemProps" class="key-select"></v-list-item>
              </template>
            </v-select>
          </div>
        </v-list-item>
      </v-list>

      <Spinner v-else></Spinner>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useNavStore } from '@/stores/nav'
import { useChangesStore, useDirtySource } from '@/stores/changes'
import { iconFor } from '@/category'
import { resolveExternalOptions } from '@/external'
import type { components } from '@/api-types'
import KeyMetadata from './KeyMetadata.vue'
import EditorToolbar from './EditorToolbar.vue'
import Spinner from './Spinner.vue'

type KeyOut = components['schemas']['KeyOut']
type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']
type ModeOut = components['schemas']['ModeOut']
type StagedEditIn = components['schemas']['StagedEditIn']

const props = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  selectedAlias?: string
}>()

const emit = defineEmits<{ select: [child: KeyChildMetaOut] }>()

const nav = useNavStore()
const changes = useChangesStore()

const payload = ref<KeyOut>()
const children = ref<KeyChildMetaOut[]>()

const staged = computed(() =>
  changes.stagedFor(props.subsystem, props.name, props.mode, props.version),
)

const externalOptionsCache = reactive(new Map<string, string[]>())
const externalOptionsRequested = new Set<string>()
const externalChoice = reactive(new Map<string, string>())

const childChoice = reactive(new Map<string, { keyId: number | null; mode: string }>())

function externalKey(child: KeyChildMetaOut): string {
  return `${child.subsystem_name}/${child.node_name}`
}

function externalItems(child: KeyChildMetaOut) {
  const options = externalOptionsCache.get(externalKey(child)) ?? []
  return [{ title: 'None', value: '' }, ...options.map((o) => ({ title: o, value: o }))]
}

function ensureExternalOptions(child: KeyChildMetaOut) {
  const key = externalKey(child)
  if (externalOptionsRequested.has(key)) return
  externalOptionsRequested.add(key)
  resolveExternalOptions(child.subsystem_name, child.node_name)
    .then((options) => externalOptionsCache.set(key, options))
    .catch(() => externalOptionsRequested.delete(key))
}

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

function modeItems(child: KeyChildMetaOut) {
  return [
    { title: 'None', value: '' },
    ...modeOptions(child).map((m) => ({
      title: `${child.subsystem_name}/${child.node_name}/${m.name}/v${m.versions[0]}`,
      value: m.name,
    })),
  ]
}

function baselineExternal(child: KeyChildMetaOut): string {
  const proposed = staged.value?.proposed_children?.[child.alias]
  if (proposed === undefined || proposed?.key_id === child.id) return child.payload ?? ''
  const sibling = changes.stagedFor(
    child.subsystem_name,
    child.node_name,
    child.mode_name,
    child.version,
  )
  return sibling?.proposed_payload ?? ''
}

function baselineChild(child: KeyChildMetaOut): { keyId: number | null; mode: string } {
  const proposed = staged.value?.proposed_children?.[child.alias]
  if (proposed === undefined) return { keyId: child.id, mode: child.mode_name }
  if (proposed === null) return { keyId: null, mode: '' }
  return { keyId: proposed.key_id, mode: proposed.mode_name }
}

function applyBaseline() {
  if (!children.value) return
  for (const child of children.value) {
    if (child.category === 'external') {
      externalChoice.set(child.alias, baselineExternal(child))
    } else {
      childChoice.set(child.alias, baselineChild(child))
    }
  }
}

async function onModeSelect(child: KeyChildMetaOut, modeName: string) {
  if (modeName === '') {
    childChoice.set(child.alias, { keyId: null, mode: '' })
    return
  }
  if (modeName === child.mode_name) {
    childChoice.set(child.alias, { keyId: child.id, mode: modeName })
    return
  }
  childChoice.set(child.alias, {
    keyId: childChoice.get(child.alias)?.keyId ?? child.id,
    mode: modeName,
  })
  const version = modeOptions(child).find((m) => m.name === modeName)?.versions[0]
  if (version === undefined) return
  const key = await nav.fetchKeyPayload(child.subsystem_name, child.node_name, modeName, version)
  if (key) childChoice.set(child.alias, { keyId: key.id, mode: modeName })
}

const dirty = computed(() => {
  if (!children.value) return false
  return children.value.some((child) =>
    child.category === 'external'
      ? externalChoice.get(child.alias) !== baselineExternal(child)
      : childChoice.get(child.alias)?.keyId !== baselineChild(child).keyId,
  )
})

useDirtySource(dirty)

async function save(comment: string) {
  if (!children.value) return
  const edits: StagedEditIn[] = []
  const proposedChildren: Record<string, number | null> = {}

  for (const child of children.value) {
    if (child.category === 'external') {
      const value = externalChoice.get(child.alias) ?? ''
      const changed = value !== (child.payload ?? '')
      proposedChildren[child.alias] = changed ? null : child.id
      if (changed) {
        edits.push({
          subsystem_name: child.subsystem_name,
          node_name: child.node_name,
          mode_name: child.mode_name,
          base_version: child.version,
          proposed_payload: value,
          comment,
        })
      }
    } else {
      const choice = childChoice.get(child.alias)
      proposedChildren[child.alias] = choice !== undefined ? choice.keyId : child.id
    }
  }

  edits.push({
    subsystem_name: props.subsystem,
    node_name: props.name,
    mode_name: props.mode,
    base_version: props.version,
    proposed_children: proposedChildren,
    comment,
  })

  await changes.stage(edits)
}

let loadToken = 0

async function load() {
  payload.value = undefined
  children.value = undefined
  externalChoice.clear()
  childChoice.clear()
  const token = ++loadToken
  const [p, c] = await Promise.all([
    nav.fetchKeyPayload(props.subsystem, props.name, props.mode, props.version),
    nav.fetchKeyChildren(props.subsystem, props.name, props.mode, props.version),
  ])
  if (token !== loadToken) return
  payload.value = p
  children.value = c
  for (const child of c) {
    if (child.category === 'external') {
      ensureExternalOptions(child)
    } else {
      ensureModes(child.node_id)
    }
  }
  applyBaseline()
}

watch(() => [props.subsystem, props.name, props.mode, props.version], load, { immediate: true })

watch(staged, applyBaseline)
</script>

<style scoped>
.key-select {
  font-family: ui-monospace, monospace;
  font-size: 0.875rem;
}
.key-select :deep(.v-field__input),
.key-select :deep(.v-list-item-title) {
  font-family: ui-monospace, monospace;
  font-size: 0.875rem;
}
</style>
