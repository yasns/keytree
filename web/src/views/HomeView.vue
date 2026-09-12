<template>
  <v-empty-state
    headline="Welcome"
    title="What would you like to do today?"
    icon="mdi-hand-wave-outline"
  >
    <v-container>
      <v-row>
        <v-col cols="12" md="6">
          <v-card
            prepend-icon="mdi-key-chain"
            text="Explore the subsystem tree and pick a key to view or edit."
            title="Browse / Edit Keys"
            @click="browseKeys"
          ></v-card>
        </v-col>

        <v-col cols="12" md="6">
          <v-card
            prepend-icon="mdi-source-branch"
            text="Check validation status, compare your changes, and commit them to the database."
            title="View Pending Changes"
            @click="viewPendingChanges"
          ></v-card>
        </v-col>

        <v-col cols="12" md="6">
          <v-card
            href="#"
            prepend-icon="mdi-help-circle-outline"
            target="_blank"
            text="View documentation and other resources."
            title="Get Help"
          ></v-card>
        </v-col>

        <v-col cols="12" md="6">
          <v-card
            href="mailto:keytree-admins@cern.ch"
            prepend-icon="mdi-bug-outline"
            target="_blank"
            text="File a bug report for Keytree."
            title="Report a Bug"
          ></v-card>
        </v-col>
      </v-row>
    </v-container>
  </v-empty-state>
</template>

<script setup lang="ts">
import { useNavStore } from '@/stores/nav'
import BrowsePanel from '@/components/BrowsePanel.vue'
import VersionControlPanel from '@/components/VersionControlPanel.vue'

const nav = useNavStore()

function browseKeys() {
  if (nav.activePanel !== BrowsePanel) nav.activePanel = BrowsePanel
  nav.subsystemMenuOpen = true
}

function viewPendingChanges() {
  if (nav.activePanel !== VersionControlPanel) nav.activePanel = VersionControlPanel
}
</script>
