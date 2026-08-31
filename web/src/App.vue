<template>
  <v-app>
    <v-layout v-if="auth.claims">
      <MainNav />

      <v-main>
        <router-view />
      </v-main>
    </v-layout>

    <v-container v-else class="h-full items-center justify-center flex">
      <v-progress-circular indeterminate color="primary" size="50" width="5" />
    </v-container>
  </v-app>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import MainNav from './components/MainNav.vue'

const auth = useAuthStore()

onMounted(() => auth.checkAuth())
</script>
