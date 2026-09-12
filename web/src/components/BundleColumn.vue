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
      :can-queue="!!canQueue"
      :subsystem="subsystem"
      :name="name"
      :mode="mode"
      :committed="isCommitted(staged)"
      @save="save"
      @save-and-queue="saveAndQueue"
      @discard="applyBaseline"
      @fork="fork"
      @copy-to="copyTo"
    ></EditorToolbar>

    <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
      <v-list v-if="children" activatable>
        <v-list-item
          v-for="row in rows"
          :key="row.child.alias"
          :active="row.child.alias === selectedAlias"
          :class="{ 'row-changed': row.changed, 'row-dirty': row.dirty }"
          @click="onRowClick(row.child)"
          class="py-2 px-2"
        >
          <div class="d-flex align-center ga-2">
            <v-icon
              :icon="iconFor(row.child, row.child.subsystem_name !== subsystem)"
              size="small"
            ></v-icon>

            <v-select
              v-if="row.child.category === 'external'"
              class="key-select"
              :model-value="externalChoice.get(row.child.alias) || undefined"
              :items="externalItems(row.child)"
              :disabled="row.child.id === null"
              :label="row.child.alias"
              placeholder="Select key"
              hide-details
              density="compact"
              @click.stop
              @update:model-value="(v) => externalChoice.set(row.child.alias, v)"
            >
              <template #item="{ props: itemProps }">
                <v-list-item v-bind="itemProps" class="key-select"></v-list-item>
              </template>
            </v-select>
            <template v-else>
              <div class="d-flex flex-column ga-1 w-100">
                <v-select
                  class="key-select"
                  :model-value="modeValue(childChoice.get(row.child.alias))"
                  :items="modeItems(row.child)"
                  :label="row.child.alias"
                  placeholder="Select key"
                  hide-details
                  density="compact"
                  @click.stop
                  @update:model-value="(v) => onModeSelect(row.child, v)"
                >
                  <template #item="{ props: itemProps }">
                    <v-list-item v-bind="itemProps" class="key-select"></v-list-item>
                  </template>
                  <template #selection>{{ selectionLabel(row.child) }}</template>
                </v-select>

                <div v-if="row.upgrade" class="text-label-medium text-medium-emphasis">
                  <v-icon
                    icon="mdi-alert-circle-outline"
                    size="x-small"
                    style="vertical-align: baseline"
                  ></v-icon>
                  {{
                    row.upgrade.staged
                      ? 'A newer version is pending.'
                      : 'A newer version is available.'
                  }}
                  <a
                    href="#"
                    class="text-primary"
                    @click.stop.prevent="updateToLatest(row.child, row.upgrade)"
                    >Update to v{{ row.upgrade.version }}</a
                  >
                </div>
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
import { isCommitted, pendingSource, useChangesStore, useDirtySource } from '@/stores/changes'
import { useStagedNavigation } from '@/composables/useStagedNavigation'
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
  /** This column's bundle-path index, i.e. what a row click here writes to. Root is 0. */
  depth: number
  selectedAlias?: string
  canQueue?: boolean
}>()

const emit = defineEmits<{ select: [child: KeyChildMetaOut]; queue: []; close: [] }>()

const nav = useNavStore()
const changes = useChangesStore()
const { navigateToStaged } = useStagedNavigation()

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

/** Value contains the tip version so reselecting a newer tip is a value change. */
function modeItems(child: KeyChildMetaOut) {
  return [
    { title: 'None', value: '' },
    ...modeOptions(child).map((m) => {
      const version = tipOf(child, m.name)?.version ?? m.versions[0]
      return {
        title: `${child.subsystem_name}/${child.node_name}/${m.name}/v${version}`,
        value: `${m.name}/${version}`,
      }
    }),
  ]
}

/** Undefined for a cleared row so a placeholder is shown. */
function modeValue(choice: ChildChoice | undefined): string | undefined {
  if (!choice?.mode) return undefined
  return `${choice.mode}/${choice.version ?? ''}`
}

/** The field shows the version this row actually points at, which may be behind its mode's tip. */
function selectionLabel(child: KeyChildMetaOut): string {
  const choice = childChoice.get(child.alias)
  if (!choice?.mode) return ''
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

async function onModeSelect(child: KeyChildMetaOut, value: string) {
  if (value === '') {
    // Cleared: the map entry for this alias is dropped, so the commit leaves it with no child row
    childChoice.set(child.alias, { keyId: null, mode: '', version: null })
  } else {
    const modeName = value.slice(0, value.lastIndexOf('/'))
    const tip = tipOf(child, modeName)
    if (modeName === child.mode_name && tip?.version === child.version) {
      childChoice.set(child.alias, { keyId: child.id, mode: modeName, version: child.version })
    } else {
      childChoice.set(child.alias, {
        keyId: childChoice.get(child.alias)?.keyId ?? child.id,
        mode: modeName,
        version: null,
      })
      if (tip) await selectKeyVersion(child, modeName, tip)
    }
  }
  await maybeReopen(child)
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
  await maybeReopen(child)
}

/** Mode separates a cleared row from one on a staged key, since neither of them has a key id. */
function choiceId(choice: ChildChoice): string {
  return `${choice.mode}/${choice.keyId ?? ''}`
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

/** The key a row points at per its pending UI choice */
function resolvedChild(child: KeyChildMetaOut): KeyChildMetaOut {
  if (child.category === 'external') {
    return { ...child, payload: externalChoice.get(child.alias) || null }
  }
  const choice = childChoice.get(child.alias)
  if (!choice?.mode) return { ...child, id: null, mode_name: null, version: null }
  return { ...child, id: choice.keyId, mode_name: choice.mode, version: choice.version }
}

// Clicking the already-open row toggles it closed; clicking any other row opens it at its current selection
async function onRowClick(child: KeyChildMetaOut) {
  if (child.alias !== props.selectedAlias) {
    emit('select', resolvedChild(child))
    return
  }
  if (!(await changes.confirmDiscardBeyond(props.depth))) return
  emit('close')
}

// A dropdown change on the row whose descendant is already open re-navigates it to match, without closing it
async function maybeReopen(child: KeyChildMetaOut) {
  if (child.alias !== props.selectedAlias) return
  if (!(await changes.confirmDiscardBeyond(props.depth))) return
  emit('select', resolvedChild(child))
}

/** Per-row derivations done once here */
const rows = computed(() =>
  (children.value ?? []).map((child) => ({
    child,
    upgrade: upgrade(child),
    changed: changedFromOriginal(child),
    dirty: rowDirty(child),
  })),
)

const dirty = computed(() => rows.value.some((r) => r.dirty))

useDirtySource(dirty, props.depth)

/** Splits the row selections into payload edits on external children and this key's own alias -> child map. */
function buildEdits(comment: string): {
  childEdits: StagedEditIn[]
  proposedChildren: Record<string, number | null>
} {
  const childEdits: StagedEditIn[] = []
  const proposedChildren: Record<string, number | null> = {}

  for (const child of children.value ?? []) {
    if (child.category === 'external') {
      // An empty alias has no base key to stage a payload edit against
      const locator = childLocator(child)
      if (!locator) continue
      const value = externalChoice.get(child.alias) ?? ''
      const changed = value !== (child.payload ?? '')
      proposedChildren[child.alias] = changed ? null : child.id
      if (changed) {
        childEdits.push({
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

  return { childEdits, proposedChildren }
}

function baseEdit(comment: string, proposedChildren: Record<string, number | null>) {
  return {
    subsystem_name: props.subsystem,
    node_name: props.name,
    mode_name: props.mode,
    base_version: props.version,
    proposed_children: proposedChildren,
    comment,
  }
}

async function save(comment: string) {
  if (!children.value) return
  const { childEdits, proposedChildren } = buildEdits(comment)
  await changes.stage([...childEdits, baseEdit(comment, proposedChildren)])
}

async function saveAndQueue(comment: string) {
  await save(comment)
  emit('queue')
}

async function fork(newModeName: string, description: string) {
  if (!children.value) return
  const { childEdits, proposedChildren } = buildEdits(description)
  if (childEdits.length) await changes.stage(childEdits)
  await changes.fork({
    ...baseEdit(description, proposedChildren),
    new_mode_name: newModeName,
    description,
  })
  applyBaseline()
  await navigateToStaged(
    props.subsystem,
    props.name,
    newModeName,
    `Forked to mode "${newModeName}"`,
  )
}

async function copyTo(targetMode: string, comment: string) {
  if (!children.value) return
  const { childEdits, proposedChildren } = buildEdits(comment)
  if (childEdits.length) await changes.stage(childEdits)
  await changes.copyTo({
    ...baseEdit(comment, proposedChildren),
    target_mode_name: targetMode,
  })
  applyBaseline()
  await navigateToStaged(props.subsystem, props.name, targetMode, `Copied to mode "${targetMode}"`)
}

async function updateAliasToLatest(alias: string) {
  const child = children.value?.find((c) => c.alias === alias)
  if (!child || child.category === 'external') return
  const modeName = childChoice.get(alias)?.mode || child.mode_name
  if (!modeName) return
  const tip = tipOf(child, modeName)
  if (tip) await selectKeyVersion(child, modeName, tip)
}

defineExpose({ updateAliasToLatest })

let loadToken = 0

async function load() {
  payload.value = undefined
  children.value = undefined
  externalChoice.clear()
  childChoice.clear()
  const token = ++loadToken
  const source = pendingSource(staged.value)
  const sourceMode = source?.mode_name ?? props.mode
  const sourceVersion = source?.version ?? props.version
  const [p, c] = await Promise.all([
    nav.fetchKeyPayload(props.subsystem, props.name, sourceMode, sourceVersion),
    nav.fetchKeyChildren(props.subsystem, props.name, sourceMode, sourceVersion),
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
