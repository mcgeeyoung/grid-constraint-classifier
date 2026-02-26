<template>
  <div v-if="zone">
    <h3 class="text-h6 mb-2">{{ zone.zone_code }}</h3>
    <p v-if="zone.zone_name" class="text-body-2 text-medium-emphasis mb-3">
      {{ zone.zone_name }}
    </p>

    <v-chip
      :color="classificationColor(zone.classification)"
      size="small"
      class="mb-3"
    >
      {{ zone.classification }}
    </v-chip>

    <v-table density="compact">
      <tbody>
        <tr>
          <td class="text-medium-emphasis">Transmission Score</td>
          <td class="text-right">{{ zone.transmission_score?.toFixed(2) ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Generation Score</td>
          <td class="text-right">{{ zone.generation_score?.toFixed(2) ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Avg Congestion</td>
          <td class="text-right">{{ zone.avg_abs_congestion?.toFixed(2) ?? '-' }} $/MWh</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Max Congestion</td>
          <td class="text-right">{{ zone.max_congestion?.toFixed(2) ?? '-' }} $/MWh</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Congested Hours</td>
          <td class="text-right">{{ zone.congested_hours_pct != null ? (zone.congested_hours_pct * 100).toFixed(1) + '%' : '-' }}</td>
        </tr>
      </tbody>
    </v-table>

    <div class="mt-4">
      <h4 class="text-subtitle-2 mb-2">DER Locations in Zone</h4>
      <p class="text-body-2 text-medium-emphasis">
        {{ derCount }} DER{{ derCount !== 1 ? 's' : '' }} registered
      </p>
    </div>
  </div>
  <div v-else class="text-center text-medium-emphasis pa-4">
    Click a zone on the map to see details
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'

const isoStore = useIsoStore()
const mapStore = useMapStore()

const zone = computed(() => {
  if (!mapStore.selectedZoneCode) return null
  return isoStore.classifications.find(c => c.zone_code === mapStore.selectedZoneCode) ?? null
})

const derCount = computed(() => {
  if (!mapStore.selectedZoneCode) return 0
  return isoStore.derLocations.filter(d => d.zone_code === mapStore.selectedZoneCode).length
})

function classificationColor(cls: string): string {
  switch (cls) {
    case 'transmission': return '#e74c3c'
    case 'generation': return '#3498db'
    case 'both': return '#9b59b6'
    case 'unconstrained': return '#2ecc71'
    default: return 'grey'
  }
}
</script>
