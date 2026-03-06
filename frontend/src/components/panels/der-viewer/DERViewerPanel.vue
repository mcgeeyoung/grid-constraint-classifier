<template>
  <div>
    <!-- Header with location info -->
    <div class="mb-3">
      <h3 class="text-h6 mb-1">DER Profile Analysis</h3>
      <div v-if="location" class="text-caption text-medium-emphasis">
        <span v-if="location.substation_name">{{ location.substation_name }}</span>
        <span v-if="location.zone_code"> · {{ location.zone_code }}</span>
        <span v-if="location.iso_code"> · {{ location.iso_code.toUpperCase() }}</span>
      </div>
    </div>

    <!-- DER type selector -->
    <div class="mb-3">
      <div class="text-caption text-medium-emphasis mb-1">DER Type</div>
      <v-chip-group
        v-model="selectedDER"
        mandatory
        selected-class="text-primary"
      >
        <v-chip
          v-for="dt in derTypes"
          :key="dt.value"
          :value="dt.value"
          size="small"
          variant="outlined"
          :prepend-icon="dt.icon"
          filter
        >
          {{ dt.label }}
        </v-chip>
      </v-chip-group>
    </div>

    <!-- Loading -->
    <div v-if="enrichmentStore.isDERViewerLoading" class="text-center pa-4">
      <v-progress-circular indeterminate size="24" color="primary" />
    </div>

    <template v-else-if="enrichmentStore.derGridScores">
      <!-- DER production profile -->
      <div class="mb-4">
        <div class="text-subtitle-2 mb-2">DER Output Profile</div>
        <template v-if="enrichmentStore.derGridScores.der_profile_12x24">
          <ProfileHeatmap
            :constraint-profile="enrichmentStore.derGridScores.der_profile_12x24"
            :constraint-base-color="[56, 189, 248]"
            constraint-label="DER Output"
            size="large"
            :show-labels="true"
            :show-legend="false"
          />
        </template>
        <div v-else-if="isDispatchable" class="text-caption pa-3" style="background: var(--bg-surface-2, rgba(255,255,255,0.05)); border-radius: 6px;">
          <v-icon icon="mdi-lightning-bolt" size="16" color="warning" class="mr-1" />
          <strong>Dispatchable</strong>: can target any constraint period (CF = 1.0)
        </div>
        <div v-else class="text-caption pa-3" style="background: var(--bg-surface-2, rgba(255,255,255,0.05)); border-radius: 6px;">
          <v-icon icon="mdi-lightbulb-on-outline" size="16" color="success" class="mr-1" />
          <strong>Consistent</strong>: flat output across all hours
        </div>
      </div>

      <!-- Grid Constraint Scores -->
      <div>
        <div class="text-subtitle-2 mb-2">Grid Constraint Scores</div>
        <GridLevelCard
          v-for="level in enrichmentStore.derGridScores.levels"
          :key="level.level"
          :level="level"
          :der-profile="enrichmentStore.derGridScores.der_profile_12x24"
        />
      </div>
    </template>

    <div v-else class="text-caption text-medium-emphasis pa-4 text-center">
      <template v-if="enrichmentStore.derViewerError">
        <v-icon size="24" color="error" class="mb-2">mdi-alert-circle-outline</v-icon>
        <div class="mb-2">Failed to load DER data.</div>
        <div class="text-caption mb-3" style="color: var(--text-secondary); word-break: break-word;">
          {{ enrichmentStore.derViewerError }}
        </div>
        <v-btn size="small" variant="outlined" @click="retry">
          <v-icon start size="14">mdi-refresh</v-icon>
          Retry
        </v-btn>
      </template>
      <template v-else>
        No data available for this location.
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSelectionStore } from '@/stores/selectionStore'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import { useGridDataStore } from '@/stores/gridDataStore'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'
import GridLevelCard from './GridLevelCard.vue'

const selectionStore = useSelectionStore()
const enrichmentStore = useEnrichmentStore()
const gridStore = useGridDataStore()

const DER_ICONS: Record<string, string> = {
  solar: 'mdi-white-balance-sunny',
  wind: 'mdi-wind-turbine',
  storage: 'mdi-battery-high',
  demand_response: 'mdi-lightning-bolt',
  energy_efficiency_eemetered: 'mdi-lightbulb-on-outline',
  weatherization: 'mdi-home-thermometer',
  combined_heat_power: 'mdi-factory',
  fuel_cell: 'mdi-fuel-cell',
}

const derTypes = [
  { value: 'solar', label: 'Solar', icon: DER_ICONS.solar },
  { value: 'wind', label: 'Wind', icon: DER_ICONS.wind },
  { value: 'storage', label: 'Storage', icon: DER_ICONS.storage },
  { value: 'demand_response', label: 'DR', icon: DER_ICONS.demand_response },
  { value: 'energy_efficiency_eemetered', label: 'EE', icon: DER_ICONS.energy_efficiency_eemetered },
  { value: 'weatherization', label: 'Weatherization', icon: DER_ICONS.weatherization },
  { value: 'combined_heat_power', label: 'CHP', icon: DER_ICONS.combined_heat_power },
  { value: 'fuel_cell', label: 'Fuel Cell', icon: DER_ICONS.fuel_cell },
]

const DISPATCHABLE_TYPES = new Set(['storage', 'demand_response', 'fuel_cell'])

const selectedDER = ref(enrichmentStore.selectedViewerDERType)

const location = computed(() => enrichmentStore.derGridScores?.location ?? null)

const isDispatchable = computed(() => DISPATCHABLE_TYPES.has(selectedDER.value))

// Resolve lat/lon from current context
function getLatLon(): { lat: number; lon: number } | null {
  // Use clickedPoint first
  if (selectionStore.clickedPoint) {
    return { lat: selectionStore.clickedPoint.lat, lon: selectionStore.clickedPoint.lng }
  }
  // Use selected substation
  const sub = gridStore.selectedSubstationDetail
  if (sub?.lat != null && sub?.lon != null) {
    return { lat: sub.lat, lon: sub.lon }
  }
  // Use zone centroid
  if (selectionStore.selectedZoneCode && selectionStore.selectedISO) {
    const zone = gridStore.zoneByCode(selectionStore.selectedZoneCode)
    if (zone?.centroid_lat != null && zone?.centroid_lon != null) {
      return { lat: zone.centroid_lat, lon: zone.centroid_lon }
    }
  }
  // Use DER grid scores location (if already loaded)
  if (enrichmentStore.derGridScores?.location) {
    const loc = enrichmentStore.derGridScores.location
    return { lat: loc.lat, lon: loc.lon }
  }
  return null
}

// Reload when DER type changes (initial load is triggered by the caller)
watch(selectedDER, (newType) => {
  const coords = getLatLon()
  if (coords) {
    enrichmentStore.loadDERGridScores(coords.lat, coords.lon, newType)
  }
})

function retry() {
  const coords = getLatLon()
  if (coords) {
    enrichmentStore.loadDERGridScores(coords.lat, coords.lon, selectedDER.value)
  }
}
</script>
