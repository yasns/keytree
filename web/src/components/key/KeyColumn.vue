<template>
  <div class="d-flex flex-column h-100 elevation-1 elevation-overlay" style="min-height: 0">
    <div>
      <KeyMetadata
        :subsystem="subsystem"
        :name="name"
        :mode="mode"
        :version="version"
        :payload="payload"
        :staged="staged"
        :pending="pending"
      ></KeyMetadata>

      <div v-if="readOnly" class="flex-shrink-0">
        <ReadOnlyAlert :reason="readOnlyText"></ReadOnlyAlert>
      </div>
      <div v-if="payload?.retired_descendants.length" class="flex-shrink-0">
        <RetiredDescendantsAlert :refs="payload.retired_descendants"></RetiredDescendantsAlert>
      </div>
      <div v-if="pendingEditors.length" class="flex-shrink-0">
        <PendingEditorsAlert :editors="pendingEditors"></PendingEditorsAlert>
      </div>

      <KeyToolbar
        :dirty="dirty"
        :staged="!!staged"
        :staged-comment="staged?.comment"
        :can-queue="!!canQueue"
        :subsystem="subsystem"
        :name="name"
        :mode="mode"
        :version="version"
        :committed="!pending"
        :read-only="readOnly"
        :payload="payload"
        @save="save"
        @save-and-queue="saveAndQueue"
        @discard="applyBaseline"
        @fork="fork"
        @copy-to="copyTo"
      ></KeyToolbar>
    </div>

    <div class="overflow-y-auto flex-grow-1" style="min-height: 0">
      <v-list v-if="children" activatable slim>
        <v-list-item
          v-for="row in rows"
          :key="row.child.alias"
          :active="row.child.alias === selectedAlias"
          :class="{
            'row-changed': row.changed,
            'row-dirty': row.dirty,
            'row-external': row.child.category === 'external',
          }"
          :ripple="row.child.category !== 'external'"
          @click="onRowClick(row.child)"
          class="py-4"
        >
          <div class="d-flex align-center ga-2">
            <v-icon
              :icon="iconFor(row.child, row.child.subsystem_name !== subsystem)"
              size="small"
            ></v-icon>

            <v-select
              v-if="row.child.category === 'external'"
              class="key-label"
              :model-value="externalChoice.get(row.child.alias) || undefined"
              :items="externalItems(row.child)"
              :disabled="readOnly || row.child.id === null"
              :label="row.child.alias"
              placeholder="Select key"
              hide-details
              @click.stop
              @update:model-value="(v) => externalChoice.set(row.child.alias, v)"
            >
              <template #item="{ item, props: itemProps }">
                <v-divider v-if="'type' in item && item.type === 'divider'"></v-divider>
                <v-list-item v-else v-bind="itemProps" class="key-label"></v-list-item>
              </template>
            </v-select>
            <template v-else>
              <div class="d-flex flex-column ga-1 w-100">
                <v-select
                  class="key-label"
                  :model-value="modeValue(childChoice.get(row.child.alias))"
                  :items="row.items"
                  :label="row.child.alias"
                  placeholder="Select key"
                  hide-details
                  :disabled="readOnly"
                  @click.stop
                  @update:model-value="(v) => onModeSelect(row.child, v)"
                >
                  <template #item="{ item, props: itemProps }">
                    <v-divider v-if="'type' in item && item.type === 'divider'"></v-divider>
                    <v-list-item v-else v-bind="itemProps" class="key-label"></v-list-item>
                  </template>
                  <template #selection
                    ><span class="key-label-truncate w-100"
                      ><span class="key-label-head"
                        >{{ row.child.subsystem_name }}/{{ row.child.vertex_name }}</span
                      ><span class="key-label-tail">{{ selectionTail(row.child) }}</span></span
                    ></template
                  >
                </v-select>

                <div v-if="row.upgrade" class="text-label-medium text-info">
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
                    v-if="!readOnly"
                    href="#"
                    class="text-primary hover-underline"
                    @click.stop.prevent="updateToLatest(row.child, row.upgrade)"
                    >Update to v{{ row.upgrade.version }}</a
                  >
                </div>

                <div v-if="row.archived" class="text-label-medium text-error">
                  <v-icon
                    icon="mdi-archive-outline"
                    size="x-small"
                    style="vertical-align: baseline"
                  ></v-icon>
                  This mode is archived.
                </div>

                <div v-if="row.decommissioned" class="text-label-medium text-error">
                  <v-icon
                    icon="mdi-key-remove"
                    size="x-small"
                    style="vertical-align: baseline"
                  ></v-icon>
                  This key is decommissioned.
                </div>
              </div>
            </template>
            <template v-if="row.child.category !== 'external'">
              <v-icon icon="mdi-chevron-right" size="small"></v-icon>
            </template>
          </div>
        </v-list-item>
      </v-list>

      <v-skeleton-loader v-else type="list-item@6"></v-skeleton-loader>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, toRef, watch } from 'vue'
import { childLocator, useNavStore } from '@/stores/nav'
import { useChangesStore, useDirtySource } from '@/stores/changes'
import { useKeyReadOnly } from '@/composables/useReadOnly'
import { useCurrentMode, useIsArchived, useModesByPath } from '@/composables/useModes'
import { useStagedNavigation } from '@/composables/useStagedNavigation'
import { usePendingEditors } from '@/composables/usePendingEditors'
import { iconFor } from '@/category'
import { resolveExternalOptions } from '@/external'
import { goodTip } from '@/mode'
import type { components } from '@/api-types'
import KeyMetadata from './KeyMetadata.vue'
import KeyToolbar from './KeyToolbar.vue'
import ReadOnlyAlert from './ReadOnlyAlert.vue'
import RetiredDescendantsAlert from './RetiredDescendantsAlert.vue'
import PendingEditorsAlert from './PendingEditorsAlert.vue'

type KeyOut = components['schemas']['KeyOut']
type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']
type ModeOut = components['schemas']['ModeOut']
type StagedEditIn = components['schemas']['StagedEditIn']

const props = defineProps<{
  subsystem: string
  name: string
  mode: string
  version: number
  /** Bundle-path index this column writes on click; root is 0. */
  depth: number
  selectedAlias?: string
  canQueue?: boolean
  pending?: boolean
}>()

const emit = defineEmits<{ select: [child: KeyChildMetaOut]; queue: []; close: [] }>()

const nav = useNavStore()
const changes = useChangesStore()
const { navigateToStaged, showStaged, afterStage } = useStagedNavigation()

const payload = ref<KeyOut>()
const modes = useModesByPath(toRef(props, 'subsystem'), toRef(props, 'name'))
const currentMode = useCurrentMode(modes, toRef(props, 'mode'))
const archived = useIsArchived(currentMode)
const { readOnly, readOnlyText } = useKeyReadOnly(() => props.subsystem, payload, archived)
const pendingEditors = usePendingEditors(computed(() => currentMode.value?.id))

const children = ref<KeyChildMetaOut[]>()

const staged = computed(() =>
  changes.stagedForColumn(props.subsystem, props.name, props.mode, props.version, props.pending),
)

const externalOptionsCache = reactive(new Map<string, string[]>())
const externalOptionsRequested = new Set<string>()
const externalChoice = reactive(new Map<string, string>())

type ChildChoice = { keyId: number | null; mode: string; version: number | null }
const childChoice = reactive(new Map<string, ChildChoice>())

type SelectOption = { title: string; value: string } | { type: 'divider' }

function externalKey(child: KeyChildMetaOut): string {
  return `${child.subsystem_name}/${child.vertex_name}`
}

function withDivider(rest: { title: string; value: string }[]): SelectOption[] {
  return rest.length
    ? [{ title: 'None', value: '' }, { type: 'divider' }, ...rest]
    : [{ title: 'None', value: '' }]
}

function externalItems(child: KeyChildMetaOut): SelectOption[] {
  const options = externalOptionsCache.get(externalKey(child)) ?? []
  return withDivider(options.map((o) => ({ title: o, value: o })))
}

function ensureExternalOptions(child: KeyChildMetaOut) {
  const key = externalKey(child)
  if (externalOptionsRequested.has(key)) return
  externalOptionsRequested.add(key)
  resolveExternalOptions(child.subsystem_name, child.vertex_name)
    .then((options) => externalOptionsCache.set(key, options))
    .catch(() => externalOptionsRequested.delete(key))
}

function modeOptions(child: KeyChildMetaOut): ModeOut[] {
  return nav.vertexDetailCache.get(child.vertex_id)?.modes ?? []
}

function committedTip(child: KeyChildMetaOut, modeName: string): number | undefined {
  const mode = modeOptions(child).find((m) => m.name === modeName)
  return mode && goodTip(mode)
}

type Upgrade = { version: number; staged: boolean }

/** Includes a staged-but-uncommitted version; `staged` marks that case. */
function tipOf(child: KeyChildMetaOut, modeName: string): Upgrade | undefined {
  const committed = committedTip(child, modeName)
  const edit = changes.stagedForMode(child.subsystem_name, child.vertex_name, modeName)
  const version = edit ? edit.expected_version : committed
  if (version === undefined) return undefined
  return { version, staged: committed !== undefined && version > committed }
}

function modeItems(child: KeyChildMetaOut): SelectOption[] {
  return withDivider(
    modeOptions(child).map((m) => {
      const version = tipOf(child, m.name)?.version ?? m.versions[0]
      return {
        title: `${child.subsystem_name}/${child.vertex_name}/${m.name}/v${version}`,
        value: `${m.name}/${version}`,
      }
    }),
  )
}

function archivedMode(child: KeyChildMetaOut): boolean {
  const mode = childChoice.get(child.alias)?.mode
  if (!mode) return false
  const option = modeOptions(child).find((m) => m.name === mode)
  return !!option && changes.archived(option)
}

// Off the mode's committed decommissioned_versions, mirroring archivedMode's fresh option lookup.
function decommissionedChild(child: KeyChildMetaOut): boolean {
  const choice = childChoice.get(child.alias)
  if (!choice?.mode || choice.version == null) return false
  const mode = modeOptions(child).find((m) => m.name === choice.mode)
  return !!mode?.decommissioned_versions.includes(choice.version)
}

function modeValue(choice: ChildChoice | undefined): string | undefined {
  if (!choice?.mode) return undefined
  return `${choice.mode}/${choice.version ?? ''}`
}

/** Tail (slash + mode + version) always shown in full; head truncates first. May be behind the mode's tip. */
function selectionTail(child: KeyChildMetaOut): string {
  const choice = childChoice.get(child.alias)
  if (!choice?.mode) return ''
  return choice.version === null ? `/${choice.mode}` : `/${choice.mode}/v${choice.version}`
}

function baselineExternal(child: KeyChildMetaOut): string {
  return changes.overlayStagedChild(props.pending ? staged.value : undefined, child).payload ?? ''
}

/** Committed child, or what the changeset stages. */
function baselineChild(child: KeyChildMetaOut): ChildChoice {
  const effective = changes.overlayStagedChild(props.pending ? staged.value : undefined, child)
  return { keyId: effective.id, mode: effective.mode_name ?? '', version: effective.version }
}

function applyBaselineRow(child: KeyChildMetaOut) {
  if (child.category === 'external') {
    externalChoice.set(child.alias, baselineExternal(child))
  } else {
    childChoice.set(child.alias, baselineChild(child))
  }
}

function applyBaseline() {
  if (!children.value) return
  for (const child of children.value) applyBaselineRow(child)
}

async function onModeSelect(child: KeyChildMetaOut, value: string) {
  if (value === '') {
    // cleared: map entry dropped, commit leaves no child row
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
    // no key yet: null tells the commit to fill it in
    childChoice.set(child.alias, { keyId: null, mode: modeName, version: tip.version })
    return
  }
  const key = await nav.fetchKeyPayload(
    child.subsystem_name,
    child.vertex_name,
    modeName,
    tip.version,
  )
  if (key) childChoice.set(child.alias, { keyId: key.id, mode: modeName, version: key.version })
}

/** When ahead of the row's own selection. */
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

/** Mode disambiguates a cleared row from a staged one: neither has a key id. */
function choiceId(choice: ChildChoice): string {
  return `${choice.mode}/${choice.keyId ?? ''}`
}

/** External payload string, or internal mode + key id. */
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

// already-open row: closes. any other row: opens at its current selection
async function onRowClick(child: KeyChildMetaOut) {
  if (child.category === 'external') return
  if (child.alias !== props.selectedAlias) {
    emit('select', resolvedChild(child))
    return
  }
  if (!(await changes.confirmDiscardBeyond(props.depth))) return
  emit('close')
}

// descendant already open: re-navigate to match, don't close
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
    archived: archivedMode(child),
    decommissioned: decommissionedChild(child),
    items: child.category === 'external' ? [] : modeItems(child),
  })),
)

const dirty = computed(() => rows.value.some((r) => r.dirty))

useDirtySource(dirty, props.depth)

/** External payload edits, plus this key's own alias -> child map. */
function buildEdits(comment: string): {
  childEdits: StagedEditIn[]
  proposedChildren: Record<string, number | null>
} {
  const childEdits: StagedEditIn[] = []
  const proposedChildren: Record<string, number | null> = {}

  for (const child of children.value ?? []) {
    if (child.category === 'external') {
      // empty alias: no base key to stage against
      const locator = childLocator(child)
      if (!locator) continue
      const value = externalChoice.get(child.alias) ?? ''
      const changed = value !== (child.payload ?? '')
      proposedChildren[child.alias] = changed ? null : child.id
      if (changed) {
        childEdits.push({
          subsystem_name: locator.subsystem,
          vertex_name: locator.name,
          mode_name: locator.mode,
          base_version: locator.version,
          proposed_payload: value,
          comment,
          validation_status: 'skipped',
        })
      }
    } else {
      const choice = childChoice.get(child.alias)
      // cleared rows stay out of the map: no child row on commit
      if (!choice?.mode) continue
      proposedChildren[child.alias] = choice.keyId
    }
  }

  return { childEdits, proposedChildren }
}

function baseEdit(comment: string, proposedChildren: Record<string, number | null>) {
  return {
    subsystem_name: props.subsystem,
    vertex_name: props.name,
    mode_name: props.mode,
    base_version: props.version,
    proposed_children: proposedChildren,
    comment,
    validation_status: 'skipped' as const,
  }
}

async function save(comment: string) {
  if (!children.value) return
  const { childEdits, proposedChildren } = buildEdits(comment)
  await changes.stage([...childEdits, baseEdit(comment, proposedChildren)])
  const { edit, left } = afterStage(
    props.subsystem,
    props.name,
    props.mode,
    props.version,
    props.pending,
  )
  if (left || props.pending) return
  if (!props.canQueue) {
    // no parent to queue into: this column owns the route
    showStaged(props.subsystem, props.name, props.mode)
    return
  }
  // point this column's bundle-path entry at what it just staged
  if (edit) nav.markPathStaged(props.depth - 1, edit.expected_version)
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
  const source = props.pending ? staged.value?.based_on : undefined
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
    // fetchVertexDetail dedups by vertex id, so repeated aliases cost nothing
    if (child.category === 'external') ensureExternalOptions(child)
    else void nav.fetchVertexDetail(child.vertex_id).catch(() => {})
  }
  applyBaseline()
}

watch(() => [props.subsystem, props.name, props.mode, props.version, props.pending], load, {
  immediate: true,
})

// reload after commit, unless it would discard unsaved selections
watch(
  () => nav.keysToken,
  () => {
    if (!dirty.value) void load()
  },
)

watch(staged, applyBaseline)
</script>

<style scoped>
.v-list-item + .v-list-item {
  border-top: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.key-label :deep(.v-field__input),
.key-label :deep(.v-list-item-title) {
  font-family: ui-monospace, monospace;
  font-size: 0.8125rem;
  font-weight: 500;
}
.row-changed {
  border-left: 3px solid rgb(var(--v-theme-warning));
}
.row-dirty {
  background-color: rgba(var(--v-theme-warning), 0.16);
}
.key-label :deep(.v-field-label) {
  font-weight: 400;
  font-family: var(--v-font-body, 'Roboto', sans-serif);
}
</style>
