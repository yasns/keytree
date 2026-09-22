<template>
  <v-empty-state
    :headline="auth.displayName ? `Hello, ${auth.displayName.split(' ')[0]}` : 'Welcome'"
    title="What would you like to do today?"
  >
    <v-container>
      <v-row>
        <v-col cols="12" md="4">
          <v-card
            prepend-icon="mdi-folder-key"
            text="Explore the subsystem tree and pick a key to view or edit."
            title="Browse Keys"
            @click="browseKeys"
          ></v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card
            prepend-icon="mdi-magnify"
            text="Search for keys or their content across all subsystems."
            title="Search"
            @click="search"
          ></v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card
            text="Check validation status, compare your changes, and commit them to the database."
            title="View Pending Changes"
            @click="viewPendingChanges"
          >
            <template v-slot:prepend>
              <v-badge
                :content="changes.pendingCount"
                :model-value="changes.pendingCount > 0"
                color="warning"
                text-color="black"
                floating
                offset-x="10"
                offset-y="10"
                location="bottom right"
                bordered
              >
                <v-icon icon="mdi-source-branch"></v-icon>
              </v-badge>
            </template>
          </v-card>
        </v-col>
      </v-row>
    </v-container>
  </v-empty-state>
</template>

<script setup lang="ts">
import { useNavStore } from '@/stores/nav'
import { useChangesStore } from '@/stores/changes'
import { useAuthStore } from '@/stores/auth'
import BrowsePanel from '@/components/sidebar/BrowsePanel.vue'
import PendingChangesPanel from '@/components/sidebar/PendingChangesPanel.vue'
import SearchPanel from '@/components/sidebar/SearchPanel.vue'

const nav = useNavStore()
const changes = useChangesStore()
const auth = useAuthStore()

function browseKeys() {
  if (nav.activePanel !== BrowsePanel) nav.activePanel = BrowsePanel
  nav.subsystemMenuOpen = true
}

function viewPendingChanges() {
  if (nav.activePanel !== PendingChangesPanel) nav.activePanel = PendingChangesPanel
}

function search() {
  nav.activePanel = SearchPanel
}
</script>
