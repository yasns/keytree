<template>
  <FormDialog
    v-model="open"
    title="Compare with..."
    confirm-text="Compare"
    :valid="valid"
    @confirm="confirm"
  >
    <div class="d-flex align-center ga-1 mb-3">
      <v-icon icon="mdi-alpha-a-box-outline"></v-icon>

      <v-autocomplete
        :model-value="props.currentMode"
        :items="[props.currentMode]"
        label="Mode"
        disabled
        hide-details
        density="comfortable"
      ></v-autocomplete>
      <v-select
        :model-value="props.currentVersion"
        :items="[{ title: currentVersionPlain, value: props.currentVersion }]"
        label="Version"
        disabled
        hide-details
        style="max-width: 130px"
        density="comfortable"
      ></v-select>
    </div>

    <div class="d-flex align-center ga-1">
      <v-icon icon="mdi-alpha-b-box"></v-icon>

      <v-autocomplete
        v-model="selectedMode"
        v-model:menu="menuOpen"
        :items="modes.map((m) => m.name)"
        label="Mode"
        autofocus
        hide-details
        density="comfortable"
      ></v-autocomplete>
      <v-select
        v-model="selectedVersion"
        :items="versionItems"
        :disabled="!selectedMode"
        :error="sameAsKeyA"
        label="Version"
        hide-details
        style="max-width: 130px"
        density="comfortable"
      >
        <template #selection="{ item }">{{ item.plain }}</template>
      </v-select>
    </div>
    <div v-if="sameAsKeyA" class="text-label-medium text-error mt-1">Must differ from Key A</div>
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { useModesByPath } from '@/composables/useModes'
import { useChangesStore } from '@/stores/changes'
import type { DiffTarget, VersionTarget } from '@/router'
import FormDialog from './FormDialog.vue'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  subsystem: string
  name: string
  currentMode?: string
  currentVersion?: VersionTarget
}>()

const emit = defineEmits<{ compare: [target: DiffTarget] }>()

const changes = useChangesStore()
const modes = useModesByPath(toRef(props, 'subsystem'), toRef(props, 'name'))

const selectedMode = ref('')
const selectedVersion = ref<VersionTarget | undefined>(undefined)
const menuOpen = ref(false)

watch(open, (isOpen) => {
  if (!isOpen) return
  selectedMode.value = props.currentMode ?? ''
  selectedVersion.value = undefined
  menuOpen.value = true
})

watch(selectedMode, () => {
  selectedVersion.value = undefined
})

const versionItems = computed<{ title: string; value: VersionTarget; plain: string }[]>(() => {
  const mode = modes.value.find((m) => m.name === selectedMode.value)
  if (!mode) return []
  const items = mode.versions.map((v, i) => ({
    title: i === 0 ? `v${v} (latest)` : `v${v}`,
    value: v as VersionTarget,
    plain: `v${v}`,
  }))
  const staged = changes.stagedForMode(props.subsystem, props.name, selectedMode.value)
  if (staged) {
    items.unshift({
      title: `v${staged.expected_version} (pending)`,
      value: 'pending',
      plain: `v${staged.expected_version}`,
    })
  }
  return items
})

const currentVersionPlain = computed(() =>
  props.currentVersion === 'pending' ? 'pending' : `v${props.currentVersion}`,
)

const sameAsKeyA = computed(
  () =>
    !!selectedMode.value &&
    selectedMode.value === props.currentMode &&
    selectedVersion.value === props.currentVersion,
)

const valid = computed(
  () => !!selectedMode.value && selectedVersion.value !== undefined && !sameAsKeyA.value,
)

function confirm() {
  if (!selectedMode.value || selectedVersion.value === undefined) return
  emit('compare', { mode: selectedMode.value, version: selectedVersion.value })
}
</script>
