<template>
  <v-navigation-drawer rail permanent>
    <v-list density="compact" nav>
      <v-tooltip v-for="item in menuItems" :key="item.title" :text="item.title" location="end">
        <template v-slot:activator="{ props: activatorProps }">
          <v-list-item
            :prepend-icon="item.icon"
            :value="item"
            :active="activePanel === item.component"
            @click="togglePanel(item.component)"
            v-bind="activatorProps"
          ></v-list-item>
        </template>
      </v-tooltip>
    </v-list>

    <template v-slot:append>
      <v-divider></v-divider>

      <v-list density="compact" nav>
        <v-menu>
          <template v-slot:activator="{ props: menuProps }">
            <v-tooltip text="Account" location="end">
              <template v-slot:activator="{ props: tooltipProps }">
                <v-list-item
                  class="d-flex justify-center min-w-10 min-h-10 overflow-visible px-1"
                  v-bind="{ ...menuProps, ...tooltipProps }"
                >
                  <v-avatar color="secondary" class="min-w-8 min-h-8">
                    <span class="text-headline-small">{{ auth.firstName?.[0] }}</span>
                  </v-avatar>
                </v-list-item>
              </template>
            </v-tooltip>
          </template>
          <v-card class="min-w-52">
            <v-card-text>
              <div class="mx-auto text-center">
                <v-avatar color="secondary" size="large">
                  <span class="text-headline-small">{{ auth.initials }}</span>
                </v-avatar>
                <h3 class="font-bold mt-1">{{ auth.firstName }} {{ auth.lastName }}</h3>
                <p class="text-body-small mt-1">
                  <span class="text-gray-400">@</span>{{ auth.username }}
                </p>
                <v-divider class="my-3"></v-divider>
                <v-btn variant="text" prepend-icon="mdi-logout" @click="auth.logout">Log Out</v-btn>
              </div>
            </v-card-text>
          </v-card>
        </v-menu>
        <v-menu>
          <template v-slot:activator="{ props: menuProps }">
            <v-tooltip text="Settings" location="end">
              <template v-slot:activator="{ props: tooltipProps }">
                <v-list-item
                  prepend-icon="mdi-cog"
                  v-bind="{ ...menuProps, ...tooltipProps }"
                ></v-list-item>
              </template>
            </v-tooltip>
          </template>

          <v-list>
            <v-list-item v-for="item in settingsItems" :key="item.title" @click="item.click">
              <template v-slot:prepend>
                <v-icon :icon="item.icon"></v-icon>
              </template>
              <v-list-item-title>{{ item.title }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </v-list>
    </template>
  </v-navigation-drawer>

  <v-navigation-drawer v-model="panelOpen" permanent width="340">
    <component :is="activePanel" v-if="activePanel" />
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { useTheme } from 'vuetify'
import { useAuthStore } from '@/stores/auth'
import { computed, shallowRef, type Component } from 'vue'
import BrowsePanel from './BrowsePanel.vue'
import VersionControlPanel from './VersionControlPanel.vue'

const auth = useAuthStore()
const theme = useTheme()

const menuItems = [
  { icon: 'mdi-file-multiple', title: 'Browse', component: BrowsePanel },
  { icon: 'mdi-source-branch', title: 'Version Control', component: VersionControlPanel },
]

const activePanel = shallowRef<Component | null>(null)
const panelOpen = computed(() => activePanel.value !== null)
function togglePanel(component: Component) {
  activePanel.value = activePanel.value === component ? null : component
}

const isDark = computed(() => theme.current.value.dark)
const settingsItems = computed(() => [
  {
    icon: isDark.value ? 'mdi-white-balance-sunny' : 'mdi-weather-night',
    title: isDark.value ? 'Light Mode' : 'Dark Mode',
    click: () => theme.cycle(),
  },
])
</script>
