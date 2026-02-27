import { createApp } from 'vue'
import { createPinia } from 'pinia'
import L from 'leaflet'
import vuetify from './plugins/vuetify'
import router from './router'
import App from './App.vue'

import 'leaflet/dist/leaflet.css'

// Fix Leaflet default marker icons broken by Vite's asset pipeline
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'

delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl })

const app = createApp(App)
app.use(createPinia())
app.use(vuetify)
app.use(router)
app.mount('#app')
