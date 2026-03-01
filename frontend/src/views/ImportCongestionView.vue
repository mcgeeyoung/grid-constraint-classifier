<template>
  <div style="height: calc(100vh - 48px); display: flex;">
    <!-- Map -->
    <div style="flex: 1; position: relative;">
      <l-map
        ref="mapRef"
        :zoom="4"
        :center="[39.8, -98.5]"
        :use-global-leaflet="false"
        style="height: 100%; width: 100%;"
      >
        <l-tile-layer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution="&copy; OpenStreetMap &copy; CARTO"
          :max-zoom="19"
        />
        <BAMarkers />
      </l-map>

      <!-- Loading indicator -->
      <v-progress-linear
        v-if="store.isLoading"
        indeterminate
        color="primary"
        style="position: absolute; top: 0; left: 0; right: 0; z-index: 1000;"
      />

      <!-- Legend -->
      <div style="position: absolute; bottom: 24px; left: 12px; z-index: 1000;">
        <v-card density="compact" class="pa-2" style="background: rgba(255,255,255,0.92);">
          <div class="text-caption font-weight-medium mb-1">Hours &gt; 80% Utilization</div>
          <div v-for="item in legendItems" :key="item.label" class="d-flex align-center ga-2" style="font-size: 11px;">
            <span :style="{ background: item.color, width: '10px', height: '10px', borderRadius: '50%', display: 'inline-block' }" />
            <span class="text-medium-emphasis">{{ item.label }}</span>
          </div>
        </v-card>
      </div>
    </div>

    <!-- Right panel -->
    <div style="width: 400px; border-left: 1px solid #ddd; overflow-y: auto; background: #ffffff;">
      <div class="pa-3 pb-0">
        <div class="d-flex align-center justify-space-between">
          <h2 class="text-subtitle-1 font-weight-bold">Import Congestion</h2>
          <v-chip size="x-small" variant="flat" color="primary">{{ store.year }}</v-chip>
        </div>
        <div class="text-caption text-medium-emphasis mt-1">
          BA-level import utilization and congestion opportunity scores
        </div>
      </div>

      <v-tabs v-model="activeTab" density="compact" bg-color="surface" class="mt-2">
        <v-tab value="rankings">Rankings</v-tab>
        <v-tab value="detail">
          Detail
          <v-badge v-if="store.selectedBACode" dot color="primary" inline />
        </v-tab>
      </v-tabs>

      <div class="pa-2">
        <CongestionTable v-if="activeTab === 'rankings'" />
        <BADetail v-else-if="activeTab === 'detail'" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { LMap, LTileLayer } from '@vue-leaflet/vue-leaflet'
import BAMarkers from '@/components/map/BAMarkers.vue'
import CongestionTable from '@/components/panels/CongestionTable.vue'
import BADetail from '@/components/panels/BADetail.vue'
import { useCongestionStore } from '@/stores/congestionStore'

const store = useCongestionStore()
const mapRef = ref<InstanceType<typeof LMap> | null>(null)
const activeTab = ref('rankings')

const legendItems = [
  { color: '#c0392b', label: '1000+' },
  { color: '#e74c3c', label: '500–999' },
  { color: '#e67e22', label: '200–499' },
  { color: '#f1c40f', label: '50–199' },
  { color: '#2ecc71', label: '< 50' },
  { color: '#95a5a6', label: 'No data' },
]

// Auto-switch to detail tab when a BA is selected
watch(() => store.selectedBACode, (code) => {
  if (code) activeTab.value = 'detail'
})

onMounted(() => {
  if (store.annualScores.length === 0) {
    store.loadData()
  }
})
</script>
