import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'dark',
    themes: {
      dark: {
        colors: {
          primary: '#3498db',
          secondary: '#2ecc71',
          accent: '#e74c3c',
          warning: '#f1c40f',
          info: '#9b59b6',
          surface: '#1e1e2e',
          background: '#121220',
        },
      },
    },
  },
})
