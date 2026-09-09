<template>
  <div class="d-flex flex-column h-100" style="min-height: 0">
    <KeyMetadata
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :version="version"
      :payload="payload"
      :staged="staged"
    ></KeyMetadata>

    <EditorToolbar
      :dirty="dirty"
      :staged="!!staged"
      :staged-comment="staged?.comment"
      @save="save"
      @discard="applyBaseline"
    ></EditorToolbar>

    <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
      <v-list v-if="children" class="py-0">
        <v-list-item
          v-for="row in rows"
          :key="row.child.alias"
          :active="row.child.alias === selectedAlias"
          :class="{ 'row-changed': row.changed, 'row-dirty': row.dirty }"
          @click="emit('select', row.child)"
          class="py-2 px-2"
        >
          <div class="d-flex flex-column ga-1">
            <div class="d-flex align-center ga-1">
              <v-icon
                :icon="iconFor(row.child, row.child.subsystem_name !== subsystem)"
                size="x-small"
              ></v-icon>

              <span class="text-title-medium">{{ row.child.alias }}</span>
            </div>

            <v-select
              v-if="row.child.category === 'external'"
              class="key-select"
              :model-value="externalChoice.get(row.child.alias)"
              :items="externalItems(row.child)"
              :disabled="row.child.id === null"
              placeholder="Select key"
              density="compact"
              hide-details
              @click.stop
              @update:model-value="(v) => externalChoice.set(row.child.alias, v)"
            >
              <template #item="{ props: itemProps }">
                <v-list-item v-bind="itemProps" class="key-select"></v-list-item>
              </template>
            </v-select>
            <template v-else>
              <v-select
                class="key-select"
                :model-value="childChoice.get(row.child.alias)?.mode"
                :items="modeItems(row.child)"
                placeholder="Select key"
                density="compact"
                hide-details
                @click.stop
                @update:model-value="(v) => onModeSelect(row.child, v)"
              >
                <template #item="{ props: itemProps }">
                  <v-list-item v-bind="itemProps" class="key-select"></v-list-item>
                </template>
                <template #selection>{{ selectionLabel(row.child) }}</template>
              </v-select>

              <div v-if="row.upgrade" class="text-caption text-medium-emphasis">
                {{
                  row.upgrade.staged
                    ? 'A newer version is staged in this changeset.'
                    : 'A newer version is available.'
                }}
                <a
                  href="#"
                  class="text-primary"
                  @click.stop.prevent="updateToLatest(row.child, row.upgrade)"
                  >Update to v{{ row.upgrade.version }}</a
                >
              </div>
            </template>
          </div>
        </v-list-item>
      </v-list>

      <Spinner v-else></Spinner>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { childLocator, useNavStore } from '@/stores/nav'
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

type ChildChoice = { keyId: number | null; mode: string; version: number | null }
const childChoice = reactive(new Map<string, ChildChoice>())

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

function modeOptions(child: KeyChildMetaOut): ModeOut[] {
  return nav.nodeDetailCache.get(child.node_id)?.modes ?? []
}

function committedTip(child: KeyChildMetaOut, modeName: string): number | undefined {
  return modeOptions(child).find((m) => m.name === modeName)?.versions[0]
}

type Upgrade = { version: number; staged: boolean }

/** Newest version of a child's mode, including one staged but not yet committed (`staged` marks that case). */
function tipOf(child: KeyChildMetaOut, modeName: string): Upgrade | undefined {
  const committed = committedTip(child, modeName)
  const edit = changes.stagedForMode(child.subsystem_name, child.node_name, modeName)
  const version = edit ? edit.expected_version : committed
  if (version === undefined) return undefined
  return { version, staged: committed !== undefined && version > committed }
}

/** Items are what picking them gets you, so each is labelled at its mode's tip. */
function modeItems(child: KeyChildMetaOut) {
  return [
    { title: 'None', value: '' },
    ...modeOptions(child).map((m) => ({
      title: `${child.subsystem_name}/${child.node_name}/${m.name}/v${m.versions[0]}`,
      value: m.name,
    })),
  ]
}

/** The field shows the version this row actually points at, which may be behind its mode's tip. */
function selectionLabel(child: KeyChildMetaOut): string {
  const choice = childChoice.get(child.alias)
  if (!choice) return ''
  if (!choice.mode) return 'None'
  const base = `${child.subsystem_name}/${child.node_name}/${choice.mode}`
  return choice.version === null ? base : `${base}/v${choice.version}`
}

function baselineExternal(child: KeyChildMetaOut): string {
  const proposed = staged.value?.proposed_children?.[child.alias]
  if (proposed === undefined || proposed?.key_id === child.id) return child.payload ?? ''
  const sibling = changes.stagedForNode(child.subsystem_name, child.node_name)
  return sibling?.proposed_payload ?? ''
}

/** Where a row points before the user touches it, i.e. the committed child, or what the changeset stages. */
function baselineChild(child: KeyChildMetaOut): ChildChoice {
  const committed = { keyId: child.id, mode: child.mode_name ?? '', version: child.version }
  const proposedChildren = staged.value?.proposed_children
  // No child map staged for this key, so the row still points where the committed key points
  if (!proposedChildren) return committed
  const proposed = proposedChildren[child.alias]
  if (proposed === undefined) return { keyId: null, mode: '', version: null }
  // null points at the key this changeset will produce, so read it back off the staged edit
  if (proposed === null) {
    const staged = changes.stagedForNode(child.subsystem_name, child.node_name)
    return staged
      ? { keyId: null, mode: staged.mode_name, version: staged.expected_version }
      : { keyId: null, mode: '', version: null }
  }
  return { keyId: proposed.key_id, mode: proposed.mode_name, version: proposed.version }
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
    // Cleared: the map entry for this alias is dropped, so the commit leaves it with no child row
    childChoice.set(child.alias, { keyId: null, mode: '', version: null })
    return
  }
  const tip = tipOf(child, modeName)
  if (modeName === child.mode_name && tip?.version === child.version) {
    childChoice.set(child.alias, { keyId: child.id, mode: modeName, version: child.version })
    return
  }
  childChoice.set(child.alias, {
    keyId: childChoice.get(child.alias)?.keyId ?? child.id,
    mode: modeName,
    version: null,
  })
  if (!tip) return
  await selectKeyVersion(child, modeName, tip)
}

async function selectKeyVersion(child: KeyChildMetaOut, modeName: string, tip: Upgrade) {
  if (tip.staged) {
    // No key exists yet, null tells the commit to fill in the key it produces for this child
    childChoice.set(child.alias, { keyId: null, mode: modeName, version: tip.version })
    return
  }
  const key = await nav.fetchKeyPayload(
    child.subsystem_name,
    child.node_name,
    modeName,
    tip.version,
  )
  if (key) childChoice.set(child.alias, { keyId: key.id, mode: modeName, version: key.version })
}

/** Tip version of the child's currently selected mode, when it's ahead of the row's own selection. */
function upgrade(child: KeyChildMetaOut): Upgrade | undefined {
  const choice = childChoice.get(child.alias)
  if (!choice || choice.version === null) return undefined
  const tip = tipOf(child, choice.mode)
  return tip && tip.version > choice.version ? tip : undefined
}

async function updateToLatest(child: KeyChildMetaOut, tip: Upgrade) {
  const choice = childChoice.get(child.alias)
  if (!choice) return
  await selectKeyVersion(child, choice.mode, tip)
}

/** Mode separates a cleared row from one on a staged key, since neither of them has a key id. */
function choiceId(choice: ChildChoice): string {
  return `${choice.mode}#${choice.keyId ?? ''}`
}

/** Current selection for a row, i.e. the external payload string, or the internal mode and key id. */
function currentValue(child: KeyChildMetaOut): string | undefined {
  if (child.category === 'external') return externalChoice.get(child.alias)
  const choice = childChoice.get(child.alias)
  return choice && choiceId(choice)
}

function changedFromOriginal(child: KeyChildMetaOut): boolean {
  const value = currentValue(child)
  const original =
    child.category === 'external'
      ? (child.payload ?? '')
      : choiceId({ keyId: child.id, mode: child.mode_name ?? '', version: child.version })
  return value !== undefined && value !== original
}

function rowDirty(child: KeyChildMetaOut): boolean {
  const baseline =
    child.category === 'external' ? baselineExternal(child) : choiceId(baselineChild(child))
  return currentValue(child) !== baseline
}

/** Per-row derivations done once here rather than on every template read. */
const rows = computed(() =>
  (children.value ?? []).map((child) => ({
    child,
    upgrade: upgrade(child),
    changed: changedFromOriginal(child),
    dirty: rowDirty(child),
  })),
)

const dirty = computed(() => rows.value.some((r) => r.dirty))

useDirtySource(dirty)

async function save(comment: string) {
  if (!children.value) return
  const edits: StagedEditIn[] = []
  const proposedChildren: Record<string, number | null> = {}

  for (const child of children.value) {
    if (child.category === 'external') {
      // An empty alias has no base key to stage a payload edit against
      const locator = childLocator(child)
      if (!locator) continue
      const value = externalChoice.get(child.alias) ?? ''
      const changed = value !== (child.payload ?? '')
      proposedChildren[child.alias] = changed ? null : child.id
      if (changed) {
        edits.push({
          subsystem_name: locator.subsystem,
          node_name: locator.name,
          mode_name: locator.mode,
          base_version: locator.version,
          proposed_payload: value,
          comment,
        })
      }
    } else {
      const choice = childChoice.get(child.alias)
      // Cleared rows stay out of the map, so the commit leaves them with no child row
      if (!choice?.mode) continue
      proposedChildren[child.alias] = choice.keyId
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
    // fetchNodeDetail dedups by node id, so repeated aliases cost nothing
    if (child.category === 'external') ensureExternalOptions(child)
    else void nav.fetchNodeDetail(child.node_id).catch(() => {})
  }
  applyBaseline()
}

watch(() => [props.subsystem, props.name, props.mode, props.version], load, { immediate: true })

// Reload committed data after a commit, unless it would throw away unsaved selections
watch(
  () => nav.keysToken,
  () => {
    if (!dirty.value) void load()
  },
)

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
.row-changed {
  border-left: 3px solid rgb(var(--v-theme-warning));
}
.row-dirty {
  background-color: rgba(var(--v-theme-warning), 0.16);
}
</style>
