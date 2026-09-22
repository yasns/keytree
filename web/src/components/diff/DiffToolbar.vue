<template>
  <v-toolbar density="compact" class="px-4">
    <template v-slot:prepend>
      <span class="key-label ml-1 key-label-truncate"
        ><span class="key-label-head">{{ keyPrefix }}</span
        ><span class="key-label-tail">{{ keyASuffix }}</span></span
      >
      <v-btn size="small" class="ml-1" variant="tonal" density="comfortable" @click="editA"
        >Edit</v-btn
      >
    </template>

    <template v-slot:default>
      <v-btn size="small" variant="tonal" prepend-icon="mdi-swap-horizontal" @click="swap">
        Swap Sides
      </v-btn>
      <v-btn size="small" variant="tonal" class="ml-1" prepend-icon="mdi-close" @click="exitDiff">
        Exit Comparison
      </v-btn>
    </template>

    <template v-slot:append>
      <span class="key-label ml-1 key-label-truncate"
        ><span class="key-label-head">{{ keyPrefix }}</span
        ><span class="key-label-tail">{{ keyBSuffix }}</span></span
      >
      <v-btn size="small" class="ml-1" variant="tonal" density="comfortable" @click="editB"
        >Edit</v-btn
      >
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

function versionLabel(mode: string, version: VersionTarget | undefined): string {
  if (version !== 'pending') return version === undefined ? '' : `v${version}`
  const staged = changes.stagedForMode(
    route.params.subsystem as string,
    route.params.name as string,
    mode,
  )
  return staged ? `v${staged.expected_version}` : ''
}

function suffixFor(mode: string, version: VersionTarget | undefined): string {
  return `/${mode}/${versionLabel(mode, version)}`
}

const keyASuffix = computed(() =>
  suffixFor(route.params.mode as string, parseVersion(route.params.version as string)),
)
const keyBSuffix = computed(() => suffixFor(props.diffTarget.mode, props.diffTarget.version))

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
