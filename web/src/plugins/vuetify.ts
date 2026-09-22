import { createVuetify } from 'vuetify'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

export default createVuetify({
  theme: {
    defaultTheme: 'system',
  },
  display: {
    mobileBreakpoint: 'md',
  },
  defaults: {
    VTextField: { density: 'compact' },
    VTextarea: { density: 'compact' },
    VSelect: { density: 'compact' },
    VAutocomplete: { density: 'compact' },
    VCombobox: { density: 'compact' },
  },
})
