import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'light',
    themes: {
      light: {
        colors: {
          primary: '#2980b9',
          secondary: '#27ae60',
          accent: '#c0392b',
          warning: '#d4a017',
          info: '#8e44ad',
          surface: '#ffffff',
          background: '#f5f5f5',
        },
      },
    },
  },
})
