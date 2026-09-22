<template>
  <v-alert type="warning" variant="tonal" density="compact" class="rounded-0">
    <div v-for="editor in editors" :key="editor.cern_login">
      {{ editor.display_name }} (<v-tooltip
        v-if="editor.email"
        :text="editor.email"
        location="bottom"
      >
        <template v-slot:activator="{ props }">
          <a :href="editor.email ? `mailto:${editor.email}` : undefined" v-bind="props">
            {{ editor.cern_login }}
          </a>
        </template> </v-tooltip
      >) has unsaved changes on this mode.
    </div>
  </v-alert>
</template>

<script setup lang="ts">
import type { components } from '@/api-types'

const props = defineProps<{ editors: components['schemas']['PendingEditorOut'][] }>()
</script>
