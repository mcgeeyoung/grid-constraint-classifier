<template>
  <l-map
    ref="mapRef"
    :zoom="5"
    :center="[39.8, -98.5]"
    :use-global-leaflet="false"
    style="height: 100%; width: 100%;"
    @click="onMapClick"
    @update:zoom="mapStore.zoom = $event"
    @update:center="onCenterUpdate"
    @ready="onMapReady"
  >
    <l-tile-layer
      url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      attribution="&copy; OpenStreetMap &copy; CARTO"
      :max-zoom="19"
    />

    <ZoneLayer v-if="mapStore.showZones" />
    <DERMarkers v-if="mapStore.showDERs" />
    <SubstationMarkers v-if="mapStore.showSubstations" />
    <DataCenterMarkers />
    <HostingCapacityLayer v-if="mapStore.showHostingCapacity" />
    <AssetMarkers v-if="mapStore.showAssets" />
    <PnodeMarkers />
    <ComparisonMarkers />
    <SitingPopup />
  </l-map>
  <MapLegend />
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { LMap, LTileLayer } from '@vue-leaflet/vue-leaflet'
import { useMapStore } from '@/stores/mapStore'
import { useIsoStore, ISO_VIEW } from '@/stores/isoStore'
import ZoneLayer from './ZoneLayer.vue'
import DERMarkers from './DERMarkers.vue'
import SubstationMarkers from './SubstationMarkers.vue'
import DataCenterMarkers from './DataCenterMarkers.vue'
import HostingCapacityLayer from './HostingCapacityLayer.vue'
import AssetMarkers from './AssetMarkers.vue'
import PnodeMarkers from './PnodeMarkers.vue'
import ComparisonMarkers from './ComparisonMarkers.vue'
import SitingPopup from './SitingPopup.vue'
import MapLegend from './MapLegend.vue'

const mapStore = useMapStore()
const isoStore = useIsoStore()
const mapRef = ref<InstanceType<typeof LMap> | null>(null)
const skipCenterSync = ref(false)
const mapReady = ref(false)

// Debounce helper
function debounce<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: any[]) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }) as unknown as T
}

function onMapReady() {
  mapReady.value = true
}

function getLeafletMap() {
  return (mapRef.value as any)?.leafletObject
}

// ISO_VIEW imported from isoStore

// Pan to ISO region when selected
watch(() => isoStore.selectedISO, (iso) => {
  if (!iso) return
  const view = ISO_VIEW[iso]
  if (!view) return
  skipCenterSync.value = true
  const tryPan = () => {
    const map = getLeafletMap()
    if (map) {
      map.setView([view.lat, view.lng], view.zoom)
      setTimeout(() => { skipCenterSync.value = false }, 1000)
    } else {
      // Map not ready yet, retry
      setTimeout(tryPan, 100)
    }
  }
  tryPan()
})

function onMapClick(e: any) {
  mapStore.setClickedPoint({ lat: e.latlng.lat, lng: e.latlng.lng })
}

// Debounce center updates to prevent overlapping fetches during pan/zoom
const onCenterUpdate = debounce((center: any) => {
  if (skipCenterSync.value) return
  if (center && typeof center.lat === 'number') {
    mapStore.center = { lat: center.lat, lng: center.lng }
  }
}, 150)
</script>
