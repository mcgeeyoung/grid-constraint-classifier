<template>
  <l-circle-marker
    v-for="sub in visibleSubs"
    :key="sub.id"
    :lat-lng="[sub.lat!, sub.lon!]"
    :radius="6"
    :color="loadingColor(sub.peak_loading_pct)"
    :fill-color="loadingColor(sub.peak_loading_pct)"
    :fill-opacity="0.8"
    :weight="2"
    @click="onSubClick(sub.id)"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 160px;">
        <strong>{{ sub.substation_name }}</strong><br />
        Rating: {{ sub.facility_rating_mw?.toFixed(1) ?? '?' }} MW<br />
        Loading: {{ sub.peak_loading_pct?.toFixed(0) ?? '?' }}%<br />
        Zone: {{ sub.zone_code ?? 'Unknown' }}
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useHierarchyStore } from '@/stores/hierarchyStore'
import { useMapStore } from '@/stores/mapStore'
import type { Substation } from '@/api/hierarchy'

const hierarchyStore = useHierarchyStore()
const mapStore = useMapStore()

const visibleSubs = computed<Substation[]>(() => {
  return hierarchyStore.substations.filter(s => {
    if (s.lat == null || s.lon == null) return false
    if (mapStore.filterMinLoading > 0 && (s.peak_loading_pct ?? 0) < mapStore.filterMinLoading) return false
    return true
  })
})

function loadingColor(pct: number | null): string {
  if (pct == null) return '#95a5a6'
  if (pct > 100) return '#e74c3c'
  if (pct >= 80) return '#e67e22'
  if (pct >= 60) return '#f1c40f'
  return '#2ecc71'
}

function onSubClick(id: number) {
  mapStore.selectedSubstationId = id
  hierarchyStore.selectSubstation(id)
}
</script>
