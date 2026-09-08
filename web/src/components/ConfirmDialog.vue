<template>
  <v-dialog v-model="open" max-width="420" persistent>
    <v-card :title="title">
      <v-card-text>{{ text }}</v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancel">{{ cancelText }}</v-btn>
        <v-btn variant="flat" :color="confirmColor" @click="confirm">{{ confirmText }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const open = defineModel<boolean>({ required: true })

withDefaults(
  defineProps<{
    title: string
    text: string
    confirmText?: string
    cancelText?: string
    confirmColor?: string
  }>(),
  { confirmText: 'Confirm', cancelText: 'Cancel', confirmColor: 'error' },
)

const emit = defineEmits<{ confirm: []; cancel: [] }>()

function confirm() {
  open.value = false
  emit('confirm')
}

function cancel() {
  open.value = false
  emit('cancel')
}
</script>
