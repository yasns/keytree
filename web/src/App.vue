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
  </v-app>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import { useSnackbarStore } from './stores/snackbar'
import MainNav from './components/MainNav.vue'
import Spinner from './components/Spinner.vue'

const auth = useAuthStore()
const snackbar = useSnackbarStore()

onMounted(() => auth.checkAuth())
</script>
