<template>
  <div>
    <v-tabs
      v-model="selectionStore.selectedISOTab"
      density="compact"
      color="primary"
      class="mb-3"
    >
      <v-tab :value="0">
        Zones
        <v-badge
          v-if="zones.length"
          :content="zones.length"
          inline
          color="grey-darken-1"
          class="ml-1"
        />
      </v-tab>
      <v-tab :value="1">
        BAs
        <v-badge
          v-if="filteredBAs.length"
          :content="filteredBAs.length"
          inline
          color="grey-darken-1"
          class="ml-1"
        />
      </v-tab>
      <v-tab :value="2">
        Utilities
        <v-badge
          v-if="filteredUtilities.length"
          :content="filteredUtilities.length"
          inline
          color="grey-darken-1"
          class="ml-1"
        />
      </v-tab>
    </v-tabs>

    <v-progress-linear v-if="gridStore.isLoading" indeterminate color="primary" class="mb-3" />

    <v-tabs-window v-model="selectionStore.selectedISOTab">
      <!-- Zones tab -->
      <v-tabs-window-item :value="0">
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
          No zones loaded.
        </div>
      </v-tabs-window-item>

      <!-- BAs tab -->
      <v-tabs-window-item :value="1">
        <v-card
          v-for="ba in filteredBAs"
          :key="ba.ba_code"
          variant="outlined"
          density="compact"
          class="pa-2 mb-1"
          style="cursor: pointer;"
          @click="onSelectBA(ba.ba_code)"
        >
          <div class="d-flex align-center justify-space-between">
            <span class="text-body-2 font-weight-medium">{{ ba.ba_code }}</span>
            <v-chip
              v-if="getBAScore(ba.ba_code)"
              size="x-small"
              :color="scoreColor(getBAScore(ba.ba_code)!)"
              variant="flat"
            >
              {{ Math.round(getBAScore(ba.ba_code)!) }}
            </v-chip>
          </div>
          <div v-if="ba.ba_name" class="text-caption text-truncate" style="color: var(--text-secondary);">
            {{ ba.ba_name }}
          </div>
        </v-card>
        <div v-if="filteredBAs.length === 0" class="text-center pa-4" style="color: var(--text-secondary);">
          No BAs found for this ISO.
        </div>
      </v-tabs-window-item>

      <!-- Utilities tab -->
      <v-tabs-window-item :value="2">
        <v-card
          v-for="util in filteredUtilities"
          :key="util.utility_code"
          variant="outlined"
          density="compact"
          class="pa-2 mb-1"
          style="cursor: pointer;"
          @click="onSelectUtility(util.utility_code)"
        >
          <div class="text-body-2 font-weight-medium">{{ util.utility_name }}</div>
          <div class="d-flex align-center ga-2 text-caption" style="color: var(--text-secondary);">
            <span v-if="util.states?.length">{{ util.states.join(', ') }}</span>
            <span v-if="util.total_feeders != null">{{ util.total_feeders }} feeders</span>
            <span v-if="util.total_remaining_capacity_mw != null">
              {{ Math.round(util.total_remaining_capacity_mw) }} MW remaining
            </span>
          </div>
        </v-card>
        <div v-if="filteredUtilities.length === 0" class="text-center pa-4" style="color: var(--text-secondary);">
          No utilities with hosting capacity data for this ISO.
        </div>
      </v-tabs-window-item>
    </v-tabs-window>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import TierChip from '@/components/shared/TierChip.vue'
import type { ZoneConstraintSummary } from '@/types/constraints'

const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()
const enrichmentStore = useEnrichmentStore()

const zones = computed(() => gridStore.zones)

const sortedZones = computed(() =>
  [...zones.value].sort((a, b) => (b.severity_score ?? 0) - (a.severity_score ?? 0)),
)

const filteredBAs = computed(() =>
  [...gridStore.basForSelectedISO].sort((a, b) => a.ba_code.localeCompare(b.ba_code)),
)

const filteredUtilities = computed(() => enrichmentStore.utilitiesForSelectedISO)

function getBAScore(baCode: string): number | null {
  return gridStore.scoresByBA.get(baCode)?.congestion_opportunity_score ?? null
}

function scoreColor(score: number): string {
  if (score >= 75) return 'error'
  if (score >= 50) return 'warning'
  if (score >= 25) return 'amber'
  return 'success'
}

function onSelectZone(zone: ZoneConstraintSummary) {
  selectionStore.selectZone(zone.zone_code)
  if (selectionStore.selectedISO) {
    gridStore.loadZoneConstraints(selectionStore.selectedISO, zone.zone_code)
  }
}

function onSelectBA(baCode: string) {
  gridStore.selectBA(baCode)
}

function onSelectUtility(code: string) {
  selectionStore.selectUtility(code)
}

onMounted(() => {
  // Ensure BAs are loaded for the BAs tab
  if (gridStore.bas.length === 0) {
    gridStore.loadCongestionData()
  }
  // Ensure utilities are loaded for the Utilities tab
  if (enrichmentStore.hcUtilities.length === 0) {
    enrichmentStore.loadUtilities()
  }
})
</script>
