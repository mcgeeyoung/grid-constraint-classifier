import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'gridDark',
    themes: {
      gridDark: {
        dark: true,
        colors: {
          primary: '#22d3ee',
          secondary: '#a78bfa',
          error: '#ef4444',
          warning: '#f59e0b',
          success: '#22c55e',
          info: '#38bdf8',
          surface: '#14141f',
          background: '#0d0d14',
        },
      },
    },
  },
  defaults: {
    global: {
      density: 'compact',
    },
  },
})
