<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-3">
      <h3 class="text-h6">Zones</h3>
      <span class="text-caption" style="color: var(--text-secondary);">{{ zones.length }} total</span>
    </div>

    <v-progress-linear v-if="gridStore.isLoading" indeterminate color="primary" class="mb-3" />

    <v-card
      v-for="zone in sortedZones"
      :key="zone.zone_code"
      variant="outlined"
      density="compact"
      class="pa-2 mb-1"
      style="cursor: pointer;"
      @click="onSelectZone(zone)"
    >
      <div class="d-flex align-center justify-space-between">
        <span class="text-body-2 font-weight-medium text-truncate">{{ zone.zone_code }}</span>
        <TierChip v-if="zone.severity_tier" :tier="zone.severity_tier" />
      </div>
      <div v-if="zone.zone_name" class="text-caption text-truncate" style="color: var(--text-secondary);">
        {{ zone.zone_name }}
      </div>
    </v-card>

    <div v-if="!gridStore.isLoading && zones.length === 0" class="text-center pa-4" style="color: var(--text-secondary);">
      No zones loaded. Select an ISO first.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'
import TierChip from '@/components/shared/TierChip.vue'
import type { ZoneConstraintSummary } from '@/types/constraints'

const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()

const zones = computed(() => gridStore.zones)

const sortedZones = computed(() =>
  [...zones.value].sort((a, b) => (b.severity_score ?? 0) - (a.severity_score ?? 0)),
)

function onSelectZone(zone: ZoneConstraintSummary) {
  selectionStore.selectZone(zone.zone_code)
  if (selectionStore.selectedISO) {
    gridStore.loadZoneConstraints(selectionStore.selectedISO, zone.zone_code)
  }
}
</script>
