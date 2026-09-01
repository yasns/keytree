<template>
  <v-app>
    <v-layout v-if="auth.claims">
      <MainNav />

      <v-main scrollable>
        <router-view />
      </v-main>
    </v-layout>

    <template v-else>
      <div class="d-flex justify-center align-center h-100">
        <v-progress-circular indeterminate color="primary" size="50" width="5" />
      </div>
    </template>
  </v-app>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import MainNav from './components/MainNav.vue'

const auth = useAuthStore()

onMounted(() => auth.checkAuth())
</script>
