<template>
  <div v-if="zone">
    <div class="d-flex align-center justify-space-between mb-2">
      <h3 class="text-h6">{{ zone.zone_code }}</h3>
      <TierChip v-if="zone.severity_tier" :tier="zone.severity_tier" />
    </div>
    <p v-if="zone.zone_name" class="text-caption mb-3" style="color: var(--text-secondary);">
      {{ zone.zone_name }}
    </p>

    <div v-if="gridStore.isDetailLoading" class="text-center pa-4">
      <v-progress-circular indeterminate size="24" color="primary" />
    </div>

    <div v-else-if="gridStore.zoneProfiles.length === 0" class="text-caption pa-2" style="color: var(--text-tertiary);">
      No constraint profiles for this zone
    </div>

    <div v-else>
      <div
        v-for="cp in gridStore.zoneProfiles"
        :key="cp.id"
        class="mb-4"
      >
        <div class="d-flex align-center ga-2 mb-1">
          <TierChip :tier="cp.constraint_type" type="constraint" />
          <span class="text-caption" style="color: var(--text-secondary);">
            Peak {{ monthName(cp.peak_month) }} @ {{ cp.peak_hour }}:00
          </span>
        </div>

        <ProfileHeatmap
          v-if="cp.profile_12x24"
          :constraint-profile="cp.profile_12x24"
          size="large"
          :highlight-peak="true"
          :peak-month="cp.peak_month"
          :peak-hour="cp.peak_hour"
        />

        <div v-else class="text-caption pa-2" style="color: var(--text-tertiary);">
          No hourly profile data
        </div>
      </div>

      <div class="text-caption text-medium-emphasis mt-1" style="line-height: 1.5;">
        Each cell represents the average constraint intensity for a given month and hour of day,
        computed from historical LMP congestion components at pnodes within this zone.
        Brighter red cells indicate hours and months with consistently higher congestion costs.
        The white-bordered cell marks the peak constraint period.
      </div>
    </div>

    <v-btn
      v-if="zone.centroid_lat != null && zone.centroid_lon != null"
      variant="tonal"
      color="info"
      size="small"
      block
      class="mb-3"
      prepend-icon="mdi-white-balance-sunny"
      @click="openDERViewer"
    >
      View DER Profiles
    </v-btn>

    <NearbyEnrichment :lat="zone.centroid_lat" :lon="zone.centroid_lon" />
  </div>
  <div v-else class="text-center pa-4" style="color: var(--text-secondary);">
    Select a zone to see constraint timing
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import TierChip from '@/components/shared/TierChip.vue'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'
import { monthName } from '@/utils/monthNames'
import NearbyEnrichment from './NearbyEnrichment.vue'

const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()
const enrichmentStore = useEnrichmentStore()

function openDERViewer() {
  if (zone.value?.centroid_lat != null && zone.value?.centroid_lon != null) {
    enrichmentStore.loadDERGridScores(zone.value.centroid_lat, zone.value.centroid_lon, 'solar')
    selectionStore.showDERViewer()
  }
}

const zone = computed(() => {
  if (!selectionStore.selectedZoneCode) return null
  return gridStore.zoneByCode(selectionStore.selectedZoneCode)
})

watch(
  () => selectionStore.selectedZoneCode,
  (zoneCode) => {
    if (!zoneCode || !selectionStore.selectedISO) return
    gridStore.loadZoneConstraints(selectionStore.selectedISO, zoneCode)
  },
  { immediate: true },
)
</script>
