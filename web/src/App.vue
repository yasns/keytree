<template>
  <v-app>
    <v-layout v-if="auth.claims">
      <MainNav />

      <v-main scrollable>
        <router-view />
      </v-main>
    </v-layout>

    <Spinner v-else></Spinner>

    <v-snackbar-queue
      v-model="snackbar.messages"
      location="bottom end"
      total-visible="3"
      closable
    ></v-snackbar-queue>

    <ConfirmDialog
      v-model="changes.confirmOpen"
      title="Unsaved changes"
      text="You are trying to navigate away from this page, which will discard your changes. Are you sure you want to continue?"
      confirm-text="Discard changes"
      @confirm="changes.resolveConfirm(true)"
      @cancel="changes.resolveConfirm(false)"
    ></ConfirmDialog>
  </v-app>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import { useChangesStore } from './stores/changes'
import { useSnackbarStore } from './stores/snackbar'
import MainNav from './components/sidebar/MainNav.vue'
import Spinner from './components/Spinner.vue'
import ConfirmDialog from './components/dialog/ConfirmDialog.vue'

const auth = useAuthStore()
const changes = useChangesStore()
const snackbar = useSnackbarStore()

onMounted(() => Promise.all([auth.checkAuth(), changes.load()]))
</script>
