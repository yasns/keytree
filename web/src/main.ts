import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import vuetify from './plugins/vuetify'
import { useSnackbarStore } from './stores/snackbar'

import 'unfonts.css'
import './styles/main.scss'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(vuetify)

const snackbar = useSnackbarStore()

app.config.errorHandler = (err) => {
  snackbar.notifyError(err)
}
window.addEventListener('unhandledrejection', (e) => {
  snackbar.notifyError(e.reason)
})

app.mount('#app')
