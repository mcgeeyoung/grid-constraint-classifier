<template>
  <l-circle-marker
    v-for="feeder in visibleFeeders"
    :key="feeder.id"
    :lat-lng="[feeder.centroid_lat!, feeder.centroid_lon!]"
    :radius="5"
    :color="capacityColor(feeder.remaining_capacity_mw)"
    :fill-color="capacityColor(feeder.remaining_capacity_mw)"
    :fill-opacity="0.8"
    :weight="1"
    @click="onFeederClick(feeder)"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 180px;">
        <strong>{{ feeder.feeder_name || feeder.feeder_id_external }}</strong><br />
        Hosting: {{ fmt(feeder.hosting_capacity_mw) }} MW<br />
        Remaining: {{ fmt(feeder.remaining_capacity_mw) }} MW<br />
        Installed DG: {{ fmt(feeder.installed_dg_mw) }} MW<br />
        Constraint: {{ feeder.constraining_metric || 'N/A' }}<br />
        Voltage: {{ feeder.voltage_kv ? feeder.voltage_kv + ' kV' : 'N/A' }}
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useHostingCapacityStore } from '@/stores/hostingCapacityStore'
import type { HCFeeder } from '@/api/hostingCapacity'

const hcStore = useHostingCapacityStore()

const visibleFeeders = computed<HCFeeder[]>(() => {
  return hcStore.feeders.filter(f => f.centroid_lat != null && f.centroid_lon != null)
})

function capacityColor(mw: number | null): string {
  if (mw == null) return '#9e9e9e'
  if (mw >= 5) return '#43a047'
  if (mw >= 2) return '#fdd835'
  if (mw >= 0.5) return '#ff9800'
  return '#e53935'
}

function fmt(val: number | null): string {
  return val != null ? val.toFixed(1) : '?'
}

function onFeederClick(feeder: HCFeeder) {
  hcStore.selectFeeder(feeder)
}
</script>
