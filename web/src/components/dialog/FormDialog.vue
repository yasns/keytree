<template>
  <v-dialog v-model="open" max-width="480" persistent>
    <v-card :title="title">
      <v-card-text>
        <slot></slot>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn variant="flat" color="primary" :disabled="!valid" @click="confirm">
          {{ confirmText }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const open = defineModel<boolean>({ required: true })

const props = defineProps<{ title: string; confirmText: string; valid: boolean }>()

const emit = defineEmits<{ confirm: [] }>()

function confirm() {
  if (!props.valid) return
  emit('confirm')
  open.value = false
}
</script>
