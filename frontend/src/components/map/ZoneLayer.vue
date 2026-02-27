<template>
  <l-geo-json
    v-for="zone in zonesWithGeo"
    :key="zone.zone_code + '-' + mapStore.zoneColorMode"
    :geojson="zone.geojson"
    :options="{ style: () => zoneStyle(zone) }"
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
  congestion: number | null
  geojson: any
}

const zonesWithGeo = computed<ZoneGeo[]>(() => {
  const clsMap = new Map<string, { classification: string; congestion: number | null }>()
  for (const c of isoStore.classifications) {
    clsMap.set(c.zone_code, {
      classification: c.classification,
      congestion: c.avg_abs_congestion,
    })
  }

  const filters = mapStore.filterClassifications
  return isoStore.zones
    .filter((z: any) => z.boundary_geojson)
    .map((z: any) => ({
      zone_code: z.zone_code,
      classification: clsMap.get(z.zone_code)?.classification ?? 'unconstrained',
      congestion: clsMap.get(z.zone_code)?.congestion ?? null,
      geojson: z.boundary_geojson,
    }))
    .filter(z => filters.length === 0 || filters.includes(z.classification))
})

// Compute min/max congestion for normalization in value mode
const congestionRange = computed(() => {
  const values = zonesWithGeo.value
    .map(z => z.congestion)
    .filter((v): v is number => v != null && v > 0)
  if (values.length === 0) return { min: 0, max: 1 }
  return { min: Math.min(...values), max: Math.max(...values) }
})

const CLASSIFICATION_COLORS: Record<string, string> = {
  transmission: '#e74c3c',
  generation: '#3498db',
  both: '#9b59b6',
  unconstrained: '#2ecc71',
}

function valueColor(congestion: number | null): string {
  if (congestion == null || congestion <= 0) return '#2ecc71'
  const { min, max } = congestionRange.value
  const range = max - min || 1
  const t = Math.min((congestion - min) / range, 1)
  // Green -> Yellow -> Red gradient
  if (t < 0.5) {
    const s = t * 2
    const r = Math.round(0x2e + (0xf1 - 0x2e) * s)
    const g = Math.round(0xcc + (0xc4 - 0xcc) * s)
    const b = Math.round(0x71 + (0x0f - 0x71) * s)
    return `rgb(${r},${g},${b})`
  } else {
    const s = (t - 0.5) * 2
    const r = Math.round(0xf1 + (0xe7 - 0xf1) * s)
    const g = Math.round(0xc4 + (0x4c - 0xc4) * s)
    const b = Math.round(0x0f + (0x3c - 0x0f) * s)
    return `rgb(${r},${g},${b})`
  }
}

function zoneStyle(zone: ZoneGeo) {
  const color = mapStore.zoneColorMode === 'value'
    ? valueColor(zone.congestion)
    : (CLASSIFICATION_COLORS[zone.classification] ?? '#95a5a6')

  return {
    color,
    fillColor: color,
    fillOpacity: mapStore.zoneColorMode === 'value' ? 0.3 : 0.15,
    weight: 2,
    opacity: 0.7,
  }
}

function onZoneClick(zoneCode: string) {
  mapStore.selectedZoneCode = zoneCode
}
</script>
