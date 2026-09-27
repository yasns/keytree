<template>
  <v-toolbar density="compact" class="px-4">
    <template v-slot:prepend>
      <v-btn class="ml-1" variant="tonal" text="Edit A" @click="editA"></v-btn>
    </template>

    <template v-slot:default>
      <v-btn variant="text" prepend-icon="mdi-swap-horizontal" @click="swap"> Swap Sides </v-btn>
      <v-btn variant="text" class="ml-1" prepend-icon="mdi-close" @click="exitDiff">
        Exit Comparison
      </v-btn>
    </template>

    <template v-slot:append>
      <v-btn class="ml-1" variant="tonal" text="Edit B" @click="editB"></v-btn>
    </template>
  </v-toolbar>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { keyRoute, parseVersion, withDiffQuery, type DiffTarget } from '@/router'
import { useNavStore } from '@/stores/nav'

const props = defineProps<{
  diffTarget: DiffTarget
}>()

const route = useRoute()
const router = useRouter()
const nav = useNavStore()

function exitDiff() {
  const returnTo = nav.preDiffLocation
  nav.preDiffLocation = null
  if (returnTo) {
    router.replace(returnTo)
    return
  }
  router.replace({
    name: 'editor',
    params: route.params,
    query: withDiffQuery(route.query as Record<string, string>, undefined),
  })
}

function editA() {
  const version = parseVersion(route.params.version as string)
  if (version === undefined) return
  router.replace({
    ...keyRoute(
      route.params.subsystem as string,
      route.params.name as string,
      route.params.mode as string,
      version,
    ),
    query: withDiffQuery(route.query as Record<string, string>, undefined),
  })
}

function editB() {
  router.replace({
    ...keyRoute(
      route.params.subsystem as string,
      route.params.name as string,
      props.diffTarget.mode,
      props.diffTarget.version,
    ),
    query: withDiffQuery(route.query as Record<string, string>, undefined),
  })
}

function swap() {
  const version = parseVersion(route.params.version as string)
  if (version === undefined) return
  router.replace({
    ...keyRoute(
      route.params.subsystem as string,
      route.params.name as string,
      props.diffTarget.mode,
      props.diffTarget.version,
    ),
    query: withDiffQuery(route.query as Record<string, string>, {
      mode: route.params.mode as string,
      version,
    }),
  })
}
</script>
