<template>
  <v-navigation-drawer
    rail
    permanent
    :class="{ 'nav-edge--active': resizing && !nav.activePanel }"
    class="elevation-2 elevation-overlay"
  >
    <v-list density="compact" nav>
      <v-tooltip v-for="item in menuItems" :key="item.title" :text="item.title" location="end">
        <template v-slot:activator="{ props: activatorProps }">
          <v-list-item
            :value="item"
            :active="nav.activePanel === item.component"
            @click="togglePanel(item.component)"
            v-bind="activatorProps"
          >
            <template v-slot:prepend>
              <v-badge
                v-if="item.badge"
                :content="item.badge"
                color="warning"
                text-color="black"
                floating
                offset-x="10"
                offset-y="10"
                location="bottom right"
                bordered
              >
                <v-icon :icon="item.icon"></v-icon>
              </v-badge>
              <v-icon v-else :icon="item.icon"></v-icon>
            </template>
          </v-list-item>
        </template>
      </v-tooltip>
    </v-list>

    <template v-slot:append>
      <v-divider></v-divider>

      <v-list density="compact" nav>
        <v-tooltip :text="`Toggle ${isDark ? 'Light' : 'Dark'} Mode`" location="end">
          <template v-slot:activator="{ props: props }">
            <v-list-item @click="theme.cycle()" v-bind="props">
              <template v-slot:prepend>
                <v-icon :icon="isDark ? 'mdi-white-balance-sunny' : 'mdi-weather-night'"></v-icon>
              </template>
            </v-list-item>
          </template>
        </v-tooltip>

        <v-tooltip text="Report a Bug" location="end">
          <template v-slot:activator="{ props: props }">
            <v-list-item
              href="https://its.cern.ch/jira/projects/CMSLITOLSW/"
              target="_blank"
              rel="noopener"
              v-bind="props"
            >
              <template v-slot:prepend>
                <v-icon icon="mdi-bug-outline"></v-icon>
              </template>
            </v-list-item>
          </template>
        </v-tooltip>

        <v-menu>
          <template v-slot:activator="{ props: menuProps }">
            <v-tooltip text="Account" location="end">
              <template v-slot:activator="{ props: tooltipProps }">
                <v-list-item v-bind="{ ...menuProps, ...tooltipProps }" class="pa-0 text-center">
                  <v-avatar color="secondary" style="width: 32px; height: 32px">
                    {{ auth.displayName?.[0] }}
                  </v-avatar>
                </v-list-item>
              </template>
            </v-tooltip>
          </template>
          <v-card style="width: 300px" class="elevation-overlay" elevation="4">
            <v-card-text>
              <div class="mx-auto text-center">
                <v-avatar color="secondary" size="large">
                  <span class="text-headline-small">{{ auth.initials }}</span>
                </v-avatar>
                <div class="text-title-medium mt-2">{{ auth.displayName }}</div>
                <div><span class="text-medium-emphasis">@</span>{{ auth.username }}</div>
                <div class="mt-2">
                  <v-chip v-for="role in auth.roles" :key="role" size="small" class="ma-1" label>
                    {{ role }}
                  </v-chip>
                </div>
                <v-divider class="my-3"></v-divider>
                <v-btn variant="text" prepend-icon="mdi-logout" @click="auth.logout">Log Out</v-btn>
              </div>
            </v-card-text>
          </v-card>
        </v-menu>
      </v-list>
    </template>
  </v-navigation-drawer>

  <v-navigation-drawer
    v-model="panelOpen"
    permanent
    class="elevation-1 elevation-overlay"
    :width="panelWidth"
    :class="{ 'nav-edge--active': resizing && nav.activePanel }"
  >
    <component :is="nav.activePanel" v-if="nav.activePanel" />
  </v-navigation-drawer>

  <div
    class="resize-handle"
    :style="{ left: handleLeft - 3 + 'px' }"
    @pointerdown="startResize"
  ></div>
</template>

<script setup lang="ts">
import { useTheme } from 'vuetify'
import { useAuthStore } from '@/stores/auth'
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { type Component, computed, ref, shallowRef } from 'vue'
import BrowsePanel from './BrowsePanel.vue'
import SearchPanel from './SearchPanel.vue'
import PendingChangesPanel from './PendingChangesPanel.vue'

const RAIL_WIDTH = 56
const MIN_WIDTH = 280
const MAX_WIDTH = 640
const CUTOFF = 180

const panelWidth = ref(400)
const lastPanel = shallowRef<Component | null>(null)
const resizing = ref(false)
const handleLeft = computed(() => RAIL_WIDTH + (nav.activePanel ? panelWidth.value : 0))

function closePanel() {
  lastPanel.value = nav.activePanel
  nav.activePanel = null
}

function startResize(down: PointerEvent) {
  down.preventDefault()
  const startX = down.clientX
  const startWidth = nav.activePanel ? panelWidth.value : 0
  function onMove(move: PointerEvent) {
    const width = startWidth + (move.clientX - startX)
    if (nav.activePanel && width < CUTOFF) {
      closePanel()
      return
    }
    if (!nav.activePanel) {
      if (width < CUTOFF) return
      nav.activePanel = lastPanel.value ?? BrowsePanel
    }
    panelWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width))
  }
  function onUp() {
    resizing.value = false
    document.body.style.userSelect = ''
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  resizing.value = true
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

const auth = useAuthStore()
const theme = useTheme()
const nav = useNavStore()
const changes = useChangesStore()

const menuItems = computed(() => [
  { icon: 'mdi-folder-key', title: 'Browse', component: BrowsePanel },
  { icon: 'mdi-magnify', title: 'Search', component: SearchPanel },
  {
    icon: 'mdi-source-branch',
    title: 'Pending Changes' + (changes.pendingCount > 0 ? ` (${changes.pendingCount})` : ''),
    component: PendingChangesPanel,
    badge: changes.pendingCount,
  },
])

nav.activePanel ??= BrowsePanel
const panelOpen = computed(() => nav.activePanel !== null)
function togglePanel(component: Component) {
  if (nav.activePanel === component) closePanel()
  else nav.activePanel = component
}

const isDark = computed(() => theme.current.value.dark)
</script>

<style scoped>
.resize-handle {
  position: fixed;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 2000;
}

.nav-edge--active {
  border-right: 6px solid rgb(var(--v-theme-primary));
}
</style>
