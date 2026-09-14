<template>
  <v-dialog v-model="open" max-width="560" persistent>
    <v-card title="Versions taken since you staged">
      <v-card-text>
        <p class="mb-3">
          Someone else committed these keys while your changes were staged. Overwrite to put your
          changes on top as new versions, or rebase them onto the new versions to review first.
        </p>
        <v-list density="compact" class="py-0">
          <v-list-item
            v-for="conflict in conflicts"
            :key="`${conflict.subsystem_name}/${conflict.node_name}/${conflict.mode_name}`"
            class="px-0"
          >
            <v-list-item-title class="text-body-medium">
              <code>
                {{ conflict.subsystem_name }}/{{ conflict.node_name }}/{{ conflict.mode_name }}
              </code>
            </v-list-item-title>
            <v-list-item-subtitle>
              staged as v{{ conflict.expected_version }} from
              {{ conflict.base_version === null ? 'new mode' : `v${conflict.base_version}` }}, now
              on v{{ conflict.tip_version }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn variant="text" :loading="rebasing" @click="emit('rebase')">Rebase</v-btn>
        <v-btn variant="flat" color="warning" :loading="committing" @click="emit('overwrite')">
          Overwrite
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { Conflict } from '@/stores/changes'

const open = defineModel<boolean>({ required: true })

defineProps<{
  conflicts: Conflict[]
  rebasing: boolean
  committing: boolean
}>()

const emit = defineEmits<{ rebase: []; overwrite: [] }>()
</script>
