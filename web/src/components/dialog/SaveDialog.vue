<template>
  <v-dialog v-model="open" max-width="480" persistent>
    <v-card :title="title">
      <v-card-text>
        <div v-if="warning" class="text-error text-body-small mb-2">{{ warning }}</div>
        <v-textarea
          v-model="comment"
          :label="label"
          rows="3"
          autofocus
          hide-details="auto"
          maxlength="255"
          counter
          :rules="[(v) => !!v.trim() || 'A comment is required']"
        ></v-textarea>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn variant="flat" color="primary" :disabled="!comment.trim()" @click="confirm">
          {{ confirmText }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const open = defineModel<boolean>({ required: true })

const props = withDefaults(
  defineProps<{
    title?: string
    label?: string
    confirmText?: string
    initialComment?: string
    warning?: string
  }>(),
  { title: 'Save changes', label: 'Comment', confirmText: 'Save', initialComment: '' },
)

const emit = defineEmits<{ save: [comment: string] }>()

const comment = ref(props.initialComment)

watch(open, (isOpen) => {
  if (isOpen) comment.value = props.initialComment
})

function confirm() {
  if (!comment.value.trim()) return
  emit('save', comment.value.trim())
  open.value = false
}
</script>
