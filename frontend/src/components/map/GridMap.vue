<template>
  <l-map
    ref="mapRef"
    :zoom="mapStore.zoom"
    :center="[mapStore.center.lat, mapStore.center.lng]"
    :use-global-leaflet="false"
    style="height: 100%; width: 100%;"
    @click="onMapClick"
    @update:zoom="mapStore.zoom = $event"
    @update:center="onCenterUpdate"
  >
    <l-tile-layer
      url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      attribution="&copy; OpenStreetMap &copy; CARTO"
      :max-zoom="19"
    />

    <ZoneLayer v-if="mapStore.showZones" />
    <DERMarkers v-if="mapStore.showDERs" />
    <SubstationMarkers v-if="mapStore.showSubstations" />
    <DataCenterMarkers v-if="mapStore.showDataCenters" />
    <AssetMarkers v-if="mapStore.showAssets" />
    <PnodeMarkers />
    <ComparisonMarkers />
    <SitingPopup />
  </l-map>
  <MapLegend />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { LMap, LTileLayer } from '@vue-leaflet/vue-leaflet'
import { useMapStore } from '@/stores/mapStore'
import ZoneLayer from './ZoneLayer.vue'
import DERMarkers from './DERMarkers.vue'
import SubstationMarkers from './SubstationMarkers.vue'
import DataCenterMarkers from './DataCenterMarkers.vue'
import AssetMarkers from './AssetMarkers.vue'
import PnodeMarkers from './PnodeMarkers.vue'
import ComparisonMarkers from './ComparisonMarkers.vue'
import SitingPopup from './SitingPopup.vue'
import MapLegend from './MapLegend.vue'

const mapStore = useMapStore()
const mapRef = ref<InstanceType<typeof LMap> | null>(null)

function onMapClick(e: any) {
  mapStore.setClickedPoint({ lat: e.latlng.lat, lng: e.latlng.lng })
}

function onCenterUpdate(center: any) {
  if (center && typeof center.lat === 'number') {
    mapStore.center = { lat: center.lat, lng: center.lng }
  }
}
</script>
