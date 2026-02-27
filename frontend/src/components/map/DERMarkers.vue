<template>
  <l-circle-marker
    v-for="der in visibleDERs"
    :key="der.id"
    :lat-lng="[der.lat!, der.lon!]"
    :radius="derRadius(der.capacity_mw)"
    :color="tierColor(der.value_tier)"
    :fill-color="tierColor(der.value_tier)"
    :fill-opacity="0.7"
    :weight="1"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 140px;">
        <strong>{{ der.der_type }}</strong> ({{ der.capacity_mw }} MW)<br />
        Zone: {{ der.zone_code ?? 'Unknown' }}<br />
        Source: {{ der.source }}
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'

const isoStore = useIsoStore()
const mapStore = useMapStore()

interface DERWithTier {
  id: number
  lat: number | null
  lon: number | null
  der_type: string
  capacity_mw: number
  zone_code: string | null
  source: string
  value_tier?: string
}

const visibleDERs = computed<DERWithTier[]>(() => {
  return (isoStore.derLocations as DERWithTier[]).filter(d => {
    if (d.lat == null || d.lon == null) return false
    if (mapStore.filterTiers.length > 0 && !mapStore.filterTiers.includes(d.value_tier ?? 'low')) return false
    if (mapStore.filterDerType && d.der_type !== mapStore.filterDerType) return false
    return true
  })
})

const TIER_COLORS: Record<string, string> = {
  premium: '#c0392b',
  high: '#e67e22',
  moderate: '#f1c40f',
  low: '#27ae60',
}

function tierColor(tier?: string): string {
  return TIER_COLORS[tier ?? 'low'] ?? '#27ae60'
}

function derRadius(capacityMw: number): number {
  return Math.min(4 + capacityMw * 2, 16)
}
</script>
