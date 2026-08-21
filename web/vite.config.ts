import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      // changeOrigin: false preserves the browser's Host header so tsgauth builds
      // redirect_uri to match this origin instead of the API's
      '/api': { target: 'http://api:8080', changeOrigin: false },
    },
  },
})
