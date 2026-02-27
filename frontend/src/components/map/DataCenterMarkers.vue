<template>
  <l-circle-marker
    v-for="dc in visibleDCs"
    :key="dc.external_slug ?? dc.facility_name"
    :lat-lng="[dc.lat!, dc.lon!]"
    :radius="dcRadius(dc.capacity_mw)"
    :color="statusColor(dc.status)"
    :fill-color="statusColor(dc.status)"
    :fill-opacity="0.8"
    :weight="2"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 180px;">
        <strong>{{ dc.facility_name ?? 'Data Center' }}</strong><br />
        <span v-if="dc.operator">Operator: {{ dc.operator }}<br /></span>
        <span v-if="dc.capacity_mw">Capacity: {{ dc.capacity_mw }} MW<br /></span>
        <span v-if="dc.status">Status: {{ dc.status }}<br /></span>
        <span v-if="dc.zone_code">Zone: {{ dc.zone_code }}<br /></span>
        <span v-if="dc.state_code">State: {{ dc.state_code }}</span>
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useIsoStore } from '@/stores/isoStore'
import { fetchDataCenters, type DataCenter } from '@/api/isos'

const isoStore = useIsoStore()
const dataCenters = ref<DataCenter[]>([])

const visibleDCs = computed(() => {
  return dataCenters.value.filter(d => d.lat != null && d.lon != null)
})

watch(() => isoStore.selectedISO, async (iso) => {
  if (iso) {
    try {
      dataCenters.value = await fetchDataCenters(iso)
    } catch {
      dataCenters.value = []
    }
  } else {
    dataCenters.value = []
  }
}, { immediate: true })

const STATUS_COLORS: Record<string, string> = {
  operational: '#3498db',
  operating: '#3498db',
  planned: '#e67e22',
  under_construction: '#f1c40f',
  proposed: '#9b59b6',
}

function statusColor(status: string | null): string {
  if (!status) return '#95a5a6'
  return STATUS_COLORS[status.toLowerCase()] ?? '#95a5a6'
}

function dcRadius(capacityMw: number | null): number {
  if (!capacityMw) return 5
  return Math.min(5 + capacityMw * 0.05, 14)
}
</script>
