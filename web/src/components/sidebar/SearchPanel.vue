<template>
  <div class="d-flex flex-column h-100">
    <div>
      <div class="px-2 pt-2 d-flex ga-2 align-center flex-wrap">
        <span class="text-label-medium">Search in</span>
        <v-chip-group v-model="mode" mandatory>
          <v-chip
            v-for="item in modeItems"
            :key="item.value"
            :value="item.value"
            filter
            size="small"
            variant="outlined"
          >
            {{ item.title }}
          </v-chip>
        </v-chip-group>
      </div>

      <div class="px-2 pb-2 d-flex ga-2 align-center">
        <v-text-field
          v-model="q"
          label="Search"
          :placeholder="
            mode === 'label' ? 'e.g. ugt/conf/pp/v92' : 'e.g. building, crate, 0x1234...'
          "
          hide-details
          clearable
          density="comfortable"
        ></v-text-field>

        <v-tooltip text="Use Regular Expression">
          <template #activator="{ props: tooltipProps }">
            <v-btn
              v-bind="tooltipProps"
              icon="mdi-regex"
              :color="regex ? 'primary' : undefined"
              variant="flat"
              size="small"
              @click="regex = !regex"
            ></v-btn>
          </template>
        </v-tooltip>
      </div>
    </div>

    <div
      v-if="loading"
      class="d-flex flex-grow-1 align-center justify-center"
      style="min-height: 0"
    >
      <Spinner></Spinner>
    </div>
    <div
      v-else-if="belowMinLength || !hits.length"
      class="d-flex flex-grow-1 align-center justify-center text-medium-emphasis"
      style="min-height: 0"
    >
      {{ belowMinLength ? `Type at least ${MIN_QUERY_LENGTH} characters...` : 'No matches' }}
    </div>
    <div v-else class="search-results overflow-y-auto flex-grow-1" style="min-height: 0">
      <v-list density="compact">
        <v-list-item v-for="hit in hits" :key="hit.label" @click="open(hit)">
          <template #title>
            <span class="key-label">
              <template v-for="(seg, i) in highlightLabel(hit.label)" :key="i">
                <mark v-if="seg.matched">{{ seg.text }}</mark>
                <template v-else>{{ seg.text }}</template>
              </template>
            </span>
          </template>
        </v-list-item>
      </v-list>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, unwrap } from '@/api'
import { keyRoute } from '@/router'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'
import Spinner from '../Spinner.vue'
import type { components } from '@/api-types'

type KeyMatchOut = components['schemas']['KeyMatchOut']
type Field = 'label' | 'payload'

const router = useRouter()
const nav = useNavStore()
const snackbar = useSnackbarStore()

const modeItems: { title: string; value: Field }[] = [
  { title: 'Key labels', value: 'label' },
  { title: 'Payload content', value: 'payload' },
]
const mode = ref<Field>('label')
const regex = ref(false)
const q = ref('')
const loading = ref(false)
const hits = ref<KeyMatchOut[]>([])

const MIN_QUERY_LENGTH = 3
const trimmedQuery = computed(() => (q.value ?? '').trim())
const belowMinLength = computed(() => trimmedQuery.value.length < MIN_QUERY_LENGTH)

let searchToken = 0
let debounceHandle: ReturnType<typeof setTimeout> | undefined

async function runSearch(query: string, field: Field, useRegex: boolean) {
  const token = ++searchToken
  loading.value = true
  try {
    const results = unwrap(
      await api.GET('/api/keys/search', {
        params: { query: { q: query, field, regex: useRegex, limit: 50 } },
      }),
    )
    if (token === searchToken) hits.value = results
  } catch (err) {
    if (token === searchToken) {
      hits.value = []
      snackbar.notifyError(err)
    }
  } finally {
    if (token === searchToken) loading.value = false
  }
}

watch([mode, trimmedQuery, regex], ([m, trimmed, useRegex]) => {
  clearTimeout(debounceHandle)
  searchToken++ // invalidate requests, drop in progress search
  hits.value = []
  if (belowMinLength.value) {
    loading.value = false
    return
  }
  loading.value = true
  debounceHandle = setTimeout(() => runSearch(trimmed, m, useRegex), 250)
})

function open(hit: KeyMatchOut) {
  const query =
    mode.value === 'payload'
      ? { q: trimmedQuery.value, regex: regex.value ? '1' : undefined }
      : undefined
  nav.pendingVertexId = null
  nav.bundleRoot = {
    subsystem: hit.subsystem_name,
    name: hit.vertex_name,
    mode: hit.mode_name,
    version: hit.version,
    pending: false,
  }
  router.push({
    ...keyRoute(hit.subsystem_name, hit.vertex_name, hit.mode_name, hit.version),
    query,
  })
}

const needle = computed(() => trimmedQuery.value.toLowerCase())

function highlightLabel(label: string): { text: string; matched: boolean }[] {
  if (!regex.value && needle.value) {
    const idx = label.toLowerCase().indexOf(needle.value)
    if (idx !== -1) {
      const end = idx + needle.value.length
      return [
        { text: label.slice(0, idx), matched: false },
        { text: label.slice(idx, end), matched: true },
        { text: label.slice(end), matched: false },
      ].filter((seg) => seg.text.length > 0)
    }
  }
  return [{ text: label, matched: false }]
}
</script>

<style scoped>
.search-results mark {
  background: rgba(var(--v-theme-warning), 0.4);
  color: inherit;
  border-radius: 2px;
}
</style>
