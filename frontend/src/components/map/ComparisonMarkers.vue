<template>
  <l-circle-marker
    v-for="(entry, idx) in valuationStore.comparisonList"
    :key="idx"
    :lat-lng="[entry.lat, entry.lon]"
    :radius="10"
    :color="idx === valuationStore.selectedComparisonIndex ? '#fff' : tierColor(entry.result.value_tier)"
    :fill-color="tierColor(entry.result.value_tier)"
    :fill-opacity="0.9"
    :weight="idx === valuationStore.selectedComparisonIndex ? 3 : 2"
    @click="onMarkerClick(idx)"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 140px;">
        <strong>Site #{{ idx + 1 }}</strong><br />
        {{ entry.derType }} &middot; {{ entry.capacityMw }} MW<br />
        Zone: {{ entry.result.geo_resolution?.zone_code ?? '?' }}<br />
        Value: ${{ entry.result.value_per_kw_year.toFixed(0) }}/kW-yr<br />
        Tier: {{ entry.result.value_tier }}
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useValuationStore } from '@/stores/valuationStore'

const valuationStore = useValuationStore()

function tierColor(tier: string): string {
  switch (tier) {
    case 'premium': return '#c0392b'
    case 'high': return '#e67e22'
    case 'moderate': return '#f1c40f'
    case 'low': return '#27ae60'
    default: return '#666'
  }
}

function onMarkerClick(index: number) {
  valuationStore.selectComparison(index)
}
</script>
