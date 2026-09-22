<template>
  <FormDialog
    v-model="open"
    title="Copy to Existing Mode"
    confirm-text="Copy"
    :valid="valid"
    @confirm="confirm"
  >
    <div class="text-medium-emphasis mb-4">Includes any unsaved edits currently in the editor.</div>
    <v-autocomplete
      v-model="targetMode"
      v-model:menu="menuOpen"
      :items="modes"
      item-title="name"
      item-value="name"
      label="Target mode"
      autofocus
      hide-details="auto"
      class="mb-4"
    ></v-autocomplete>
    <v-textarea
      v-model="comment"
      label="Comment"
      rows="3"
      hide-details="auto"
      maxlength="255"
      counter
      :rules="[(v: string) => !!v.trim() || 'A comment is required']"
    ></v-textarea>
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { components } from '@/api-types'
import { useChangesStore } from '@/stores/changes'
import FormDialog from './FormDialog.vue'

type ModeOut = components['schemas']['ModeOut']

const open = defineModel<boolean>({ required: true })

const props = defineProps<{ modes: ModeOut[]; current: string }>()

const emit = defineEmits<{ copy: [mode: string, comment: string] }>()

const changes = useChangesStore()

const targetMode = ref('')
const comment = ref('')
const menuOpen = ref(false)

const modes = computed(() =>
  props.modes.filter((m) => !changes.archived(m) && m.name !== props.current),
)

watch(open, (isOpen) => {
  if (isOpen) {
    targetMode.value = ''
    comment.value = ''
    menuOpen.value = true
  }
})

const valid = computed(() => !!targetMode.value && !!comment.value.trim())

function confirm() {
  emit('copy', targetMode.value, comment.value.trim())
}
</script>
