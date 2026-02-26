<template>
  <l-geo-json
    v-for="zone in zonesWithGeo"
    :key="zone.zone_code"
    :geojson="zone.geojson"
    :options="{ style: () => zoneStyle(zone.classification) }"
    @click="onZoneClick(zone.zone_code)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LGeoJson } from '@vue-leaflet/vue-leaflet'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'

const isoStore = useIsoStore()
const mapStore = useMapStore()

interface ZoneGeo {
  zone_code: string
  classification: string
  geojson: any
}

const zonesWithGeo = computed<ZoneGeo[]>(() => {
  // Build a classification lookup
  const clsMap = new Map<string, string>()
  for (const c of isoStore.classifications) {
    clsMap.set(c.zone_code, c.classification)
  }

  return isoStore.zones
    .filter((z: any) => z.boundary_geojson)
    .map((z: any) => ({
      zone_code: z.zone_code,
      classification: clsMap.get(z.zone_code) ?? 'unconstrained',
      geojson: z.boundary_geojson,
    }))
})

const CLASSIFICATION_COLORS: Record<string, string> = {
  transmission: '#e74c3c',
  generation: '#3498db',
  both: '#9b59b6',
  unconstrained: '#2ecc71',
}

function zoneStyle(classification: string) {
  const color = CLASSIFICATION_COLORS[classification] ?? '#95a5a6'
  return {
    color,
    fillColor: color,
    fillOpacity: 0.15,
    weight: 2,
    opacity: 0.7,
  }
}

function onZoneClick(zoneCode: string) {
  mapStore.selectedZoneCode = zoneCode
}
</script>
