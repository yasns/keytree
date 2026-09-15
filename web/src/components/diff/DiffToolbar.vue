<template>
  <v-toolbar density="compact" class="bg-surface border-b-sm px-4">
    <template v-slot:prepend>
      <v-icon icon="mdi-alpha-a-box" size="small"></v-icon>
      <span class="key-label ml-1">{{ keyALabel }}</span>
    </template>

    <template v-slot:default>
      <v-btn size="small" variant="tonal" prepend-icon="mdi-swap-horizontal" @click="swap">
        Swap sides
      </v-btn>
      <v-btn
        size="small"
        variant="tonal"
        color="error"
        class="ml-1"
        prepend-icon="mdi-close"
        @click="exitDiff"
      >
        Exit comparison
      </v-btn>
    </template>

    <template v-slot:append>
      <v-icon icon="mdi-alpha-b-box" size="small"></v-icon>
      <span class="key-label ml-1">{{ keyBLabel }}</span>
    </template>
  </v-toolbar>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  keyRoute,
  parseVersion,
  withDiffQuery,
  type DiffTarget,
  type VersionTarget,
} from '@/router'
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'

const props = defineProps<{
  diffTarget: DiffTarget
}>()

const route = useRoute()
const router = useRouter()
const nav = useNavStore()
const changes = useChangesStore()

const keyPrefix = computed(() => `${route.params.subsystem}/${route.params.name}`)

/** Resolves a 'pending' target to the staged edit's expected version, so it doesn't show literally. */
function versionLabel(mode: string, version: VersionTarget | undefined): string {
  if (version !== 'pending') return version === undefined ? '' : `v${version}`
  const staged = changes.stagedForMode(
    route.params.subsystem as string,
    route.params.name as string,
    mode,
  )
  return staged ? `v${staged.expected_version}` : 'pending'
}

const keyALabel = computed(
  () =>
    `${keyPrefix.value}/${route.params.mode}/${versionLabel(route.params.mode as string, parseVersion(route.params.version as string))}`,
)
const keyBLabel = computed(
  () =>
    `${keyPrefix.value}/${props.diffTarget.mode}/${versionLabel(props.diffTarget.mode, props.diffTarget.version)}`,
)

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
