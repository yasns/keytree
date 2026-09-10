<template>
  <v-navigation-drawer rail permanent>
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
                color="error"
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
          <v-card>
            <v-card-text>
              <div class="mx-auto text-center">
                <v-avatar color="secondary" size="large">
                  <span class="text-headline-small">{{ auth.initials }}</span>
                </v-avatar>
                <h3 class="font-weight-bold mt-1">{{ auth.displayName }}</h3>
                <p class="text-body-small mt-1">
                  <span class="text-medium-emphasis">@</span>{{ auth.username }}
                </p>
                <v-divider class="my-3"></v-divider>
                <v-btn variant="text" prepend-icon="mdi-logout" @click="auth.logout">Log Out</v-btn>
              </div>
            </v-card-text>
          </v-card>
        </v-menu>
      </v-list>
    </template>
  </v-navigation-drawer>

  <v-navigation-drawer v-model="panelOpen" permanent width="400">
    <component :is="nav.activePanel" v-if="nav.activePanel" />
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { useTheme } from 'vuetify'
import { useAuthStore } from '@/stores/auth'
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { computed, type Component } from 'vue'
import BrowsePanel from './BrowsePanel.vue'
import VersionControlPanel from './VersionControlPanel.vue'

const auth = useAuthStore()
const theme = useTheme()
const nav = useNavStore()
const changes = useChangesStore()

const menuItems = computed(() => [
  { icon: 'mdi-script-text-key', title: 'Browse', component: BrowsePanel },
  {
    icon: 'mdi-source-branch',
    title:
      'Version Control' +
      (changes.visibleEdits.length > 0 ? ` – ${changes.visibleEdits.length} pending changes` : ''),
    component: VersionControlPanel,
    badge: changes.visibleEdits.length,
  },
])

nav.activePanel ??= BrowsePanel
const panelOpen = computed(() => nav.activePanel !== null)
function togglePanel(component: Component) {
  nav.activePanel = nav.activePanel === component ? null : component
}

const isDark = computed(() => theme.current.value.dark)
</script>
