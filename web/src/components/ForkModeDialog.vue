<template>
  <FormDialog
    v-model="open"
    title="Fork to New Mode"
    confirm-text="Fork"
    :valid="valid"
    @confirm="confirm"
  >
    <div class="text-medium-emphasis mb-4">Includes any unsaved edits currently in the editor.</div>
    <v-text-field
      v-model="name"
      label="Mode name"
      autofocus
      maxlength="64"
      hide-details="auto"
      :rules="rules"
      class="mb-4"
    ></v-text-field>
    <v-textarea
      v-model="description"
      label="Description"
      rows="2"
      maxlength="255"
      counter
      hide-details="auto"
      :rules="[(v: string) => !!v.trim() || 'A description is required']"
    ></v-textarea>
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import FormDialog from './FormDialog.vue'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{ existing: string[] }>()

const emit = defineEmits<{ fork: [name: string, description: string] }>()

const name = ref('')
const description = ref('')

watch(open, (isOpen) => {
  if (isOpen) {
    name.value = ''
    description.value = ''
  }
})

const rules = computed(() => [
  (v: string) => !!v.trim() || 'A mode name is required',
  (v: string) => /^[a-z0-9_]+$/.test(v) || 'Lowercase letters, digits and underscores only',
  (v: string) => v.length <= 64 || 'At most 64 characters',
  (v: string) => !props.existing.includes(v) || 'This path already has a mode with that name',
])

const valid = computed(
  () => rules.value.every((rule) => rule(name.value) === true) && !!description.value.trim(),
)

function confirm() {
  emit('fork', name.value, description.value.trim())
}
</script>
