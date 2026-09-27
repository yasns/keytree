<template>
  <div class="d-flex flex-column h-100">
    <div class="d-flex flex-column px-4 py-3 ga-1 border-b-sm">
      <div class="text-title-medium">Search</div>

      <div>
        <div class="d-flex ga-1">
          <v-text-field
            v-model="q"
            density="comfortable"
            label="Search..."
            :placeholder="
              mode === 'label' ? 'e.g. ugt/conf/pp/v92' : 'e.g. building, crate, 0x1234...'
            "
            hide-details
            clearable
          ></v-text-field>

          <v-select
            v-model="mode"
            density="comfortable"
            :items="modeItems"
            item-title="title"
            item-value="value"
            label="In"
            hide-details
            style="max-width: 120px"
          ></v-select>
        </div>

        <div class="d-flex justify-end">
          <v-chip-group
            :model-value="regex ? 'regex' : undefined"
            @update:model-value="(v) => (regex = v === 'regex')"
          >
            <v-chip
              value="regex"
              prepend-icon="mdi-regex"
              filter
              size="small"
              variant="outlined"
              class="mr-0"
            >
              Use Regex
            </v-chip>
          </v-chip-group>
        </div>
      </div>
    </div>

    <div v-if="loading" class="flex-grow-1" style="min-height: 0">
      <v-skeleton-loader type="list-item@6"></v-skeleton-loader>
    </div>
    <v-empty-state
      v-else-if="belowMinLength || !hits.length"
      class="flex-grow-1"
      style="min-height: 0"
      icon="mdi-magnify"
      :text="belowMinLength ? `Type at least ${MIN_QUERY_LENGTH} characters...` : 'No matches'"
    ></v-empty-state>
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
import { highlightMatch } from '@/format'
import { keyRoute } from '@/router'
import { useNavStore } from '@/stores/nav'
import { useSnackbarStore } from '@/stores/snackbar'
import type { components } from '@/api-types'

type KeyMatchOut = components['schemas']['KeyMatchOut']
type Field = 'label' | 'payload'

const router = useRouter()
const nav = useNavStore()
const snackbar = useSnackbarStore()

const modeItems: { title: string; value: Field }[] = [
  { title: 'Keys', value: 'label' },
  { title: 'Content', value: 'payload' },
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
  nav.pendingNamespaceId = null
  nav.bundleRoot = {
    subsystem: hit.subsystem_name,
    name: hit.namespace_name,
    mode: hit.mode_name,
    version: hit.version,
    pending: false,
  }
  router.push({
    ...keyRoute(hit.subsystem_name, hit.namespace_name, hit.mode_name, hit.version),
    query,
  })
}

function highlightLabel(label: string) {
  return regex.value ? [{ text: label, matched: false }] : highlightMatch(label, trimmedQuery.value)
}
</script>
