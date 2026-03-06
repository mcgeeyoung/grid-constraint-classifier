<template>
  <v-navigation-drawer
    location="left"
    permanent
    :rail="isCollapsed"
    :width="280"
    rail-width="56"
    color="transparent"
    style="border-right: 1px solid var(--border-subtle); background: var(--bg-base) !important;"
  >
    <!-- Toggle button -->
    <div class="d-flex align-center pa-2" :class="isCollapsed ? 'justify-center' : 'justify-space-between'">
      <span v-if="!isCollapsed" class="text-caption font-weight-bold" style="color: var(--text-secondary);">
        EXPLORER
      </span>
      <v-btn icon size="small" variant="text" @click="isCollapsed = !isCollapsed">
        <v-icon>{{ isCollapsed ? 'mdi-menu' : 'mdi-chevron-left' }}</v-icon>
      </v-btn>
    </div>

    <v-divider style="border-color: var(--border-subtle);" />

    <!-- Rail mode: icon buttons -->
    <template v-if="isCollapsed">
      <div class="d-flex flex-column align-center ga-1 pt-2">
        <v-btn
          icon size="small" variant="text"
          :color="activeTab === 0 ? 'primary' : undefined"
          title="Zones"
          @click="expandTo(0)"
        >
          <v-icon>mdi-vector-polygon</v-icon>
        </v-btn>
        <v-btn
          icon size="small" variant="text"
          :color="activeTab === 1 ? 'primary' : undefined"
          title="Balancing Authorities"
          @click="expandTo(1)"
        >
          <v-icon>mdi-earth</v-icon>
        </v-btn>
        <v-btn
          icon size="small" variant="text"
          :color="activeTab === 2 ? 'primary' : undefined"
          title="Utilities"
          @click="expandTo(2)"
        >
          <v-icon>mdi-office-building</v-icon>
        </v-btn>
      </div>

      <v-divider class="my-2" style="border-color: var(--border-subtle);" />

      <div class="d-flex flex-column align-center">
        <v-btn
          icon size="small" variant="text"
          title="Layer Controls"
          @click="isCollapsed = false; showLayers = true"
        >
          <v-icon>mdi-layers</v-icon>
        </v-btn>
      </div>
    </template>

    <!-- Expanded mode -->
    <template v-else>
      <!-- Navigation tabs -->
      <v-tabs
        v-model="activeTab"
        density="compact"
        color="primary"
        grow
      >
        <v-tab :value="0">
          <v-icon size="16" class="mr-1">mdi-vector-polygon</v-icon>
          <span class="text-caption">Zones</span>
          <v-badge
            v-if="zones.length"
            :content="zones.length"
            inline
            color="grey-darken-1"
            class="ml-1"
          />
        </v-tab>
        <v-tab :value="1">
          <v-icon size="16" class="mr-1">mdi-earth</v-icon>
          <span class="text-caption">BAs</span>
          <v-badge
            v-if="filteredBAs.length"
            :content="filteredBAs.length"
            inline
            color="grey-darken-1"
            class="ml-1"
          />
        </v-tab>
        <v-tab :value="2">
          <v-icon size="16" class="mr-1">mdi-office-building</v-icon>
          <span class="text-caption">Utils</span>
          <v-badge
            v-if="filteredUtilities.length"
            :content="filteredUtilities.length"
            inline
            color="grey-darken-1"
            class="ml-1"
          />
        </v-tab>
      </v-tabs>

      <!-- Tab content -->
      <div style="flex: 1; overflow-y: auto; padding: 8px;">
        <v-progress-linear v-if="gridStore.isLoading" indeterminate color="primary" class="mb-2" />

        <div v-if="!selectionStore.selectedISO" class="text-center pa-4" style="color: var(--text-secondary);">
          <v-icon size="32" class="mb-2">mdi-map-search</v-icon>
          <div class="text-body-2">Select an ISO from the dropdown above to browse zones, BAs, and utilities.</div>
        </div>

        <template v-else>
          <!-- Zones tab -->
          <div v-show="activeTab === 0">
            <v-card
              v-for="zone in sortedZones"
              :key="zone.zone_code"
              variant="outlined"
              density="compact"
              class="pa-2 mb-1"
              style="cursor: pointer;"
              :class="{ 'border-primary': selectionStore.selectedZoneCode === zone.zone_code }"
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
          </div>

          <!-- BAs tab -->
          <div v-show="activeTab === 1">
            <v-card
              v-for="ba in filteredBAs"
              :key="ba.ba_code"
              variant="outlined"
              density="compact"
              class="pa-2 mb-1"
              style="cursor: pointer;"
              :class="{ 'border-primary': selectionStore.selectedBACode === ba.ba_code }"
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
            <div v-if="filteredBAs.length === 0 && !gridStore.isLoading" class="text-center pa-4" style="color: var(--text-secondary);">
              No BAs found for this ISO.
            </div>
          </div>

          <!-- Utilities tab -->
          <div v-show="activeTab === 2">
            <v-card
              v-for="util in filteredUtilities"
              :key="util.utility_code"
              variant="outlined"
              density="compact"
              class="pa-2 mb-1"
              style="cursor: pointer;"
              :class="{ 'border-primary': selectionStore.selectedUtilityCode === util.utility_code }"
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
            <div v-if="filteredUtilities.length === 0 && !gridStore.isLoading" class="text-center pa-4" style="color: var(--text-secondary);">
              No utilities with hosting capacity data for this ISO.
            </div>
          </div>
        </template>
      </div>

      <!-- Layer Controls -->
      <v-divider style="border-color: var(--border-subtle);" />
      <div class="pa-2">
        <div
          class="d-flex align-center justify-space-between"
          style="cursor: pointer;"
          @click="showLayers = !showLayers"
        >
          <span class="text-caption font-weight-bold" style="color: var(--text-secondary);">
            <v-icon size="14" class="mr-1">mdi-layers</v-icon>
            LAYERS
          </span>
          <v-icon size="16">{{ showLayers ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
        </div>

        <div v-show="showLayers" class="mt-1">
          <v-checkbox
            v-model="mapStore.showZones"
            label="Zones"
            density="compact"
            hide-details
            color="primary"
          />
          <div v-if="mapStore.showZones" class="ml-6 mb-1">
            <v-btn-toggle
              v-model="mapStore.zoneColorMode"
              mandatory
              density="compact"
              color="primary"
              variant="outlined"
              divided
            >
              <v-btn value="severity" size="x-small">Severity</v-btn>
              <v-btn value="classification" size="x-small">Type</v-btn>
              <v-btn value="value" size="x-small">Value</v-btn>
            </v-btn-toggle>
          </div>
          <v-checkbox
            v-model="mapStore.showDERs"
            label="DER Locations"
            density="compact"
            hide-details
            color="secondary"
          />
          <v-checkbox
            v-model="mapStore.showDataCenters"
            label="Data Centers"
            density="compact"
            hide-details
            color="info"
          />
          <v-checkbox
            v-model="mapStore.showTransmissionLines"
            label="Transmission Lines"
            density="compact"
            hide-details
            color="red"
          />
          <v-checkbox
            v-model="mapStore.showFeeders"
            label="Feeders"
            density="compact"
            hide-details
            color="blue-grey"
          />
          <v-checkbox
            v-model="mapStore.showAssets"
            label="DER Profiles"
            density="compact"
            hide-details
            color="purple"
          />
          <v-checkbox
            v-model="mapStore.showInterconnectionQueue"
            label="Interconnection Queue"
            density="compact"
            hide-details
            color="deep-orange"
          />
          <v-checkbox
            v-model="mapStore.showBAMarkers"
            label="BA Markers"
            density="compact"
            hide-details
            color="cyan"
          />
          <v-divider class="my-1" style="border-color: var(--border-subtle);" />
          <div class="text-caption mb-1" style="color: var(--text-secondary);">Infrastructure (OSM)</div>
          <v-checkbox
            v-model="mapStore.showInfraLines"
            label="Power Lines"
            density="compact"
            hide-details
            color="deep-purple"
          />
          <v-checkbox
            v-model="mapStore.showInfraSubstations"
            label="Substations"
            density="compact"
            hide-details
            color="amber"
          />
          <v-checkbox
            v-model="mapStore.showInfraPowerPlants"
            label="Power Plants"
            density="compact"
            hide-details
            color="green"
          />
        </div>
      </div>
    </template>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import { useMapStore } from '@/stores/mapStore'
import TierChip from '@/components/shared/TierChip.vue'
import type { ZoneConstraintSummary } from '@/types/constraints'

const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()
const enrichmentStore = useEnrichmentStore()
const mapStore = useMapStore()

const isCollapsed = ref(false)
const activeTab = ref(0)
const showLayers = ref(false)

// Sync with selectionStore tab
watch(() => selectionStore.selectedISOTab, (val) => {
  activeTab.value = val
})
watch(activeTab, (val) => {
  selectionStore.selectedISOTab = val
})

// Zone/BA/Utility data (ported from ISODetailPanel)
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

function expandTo(tab: number) {
  isCollapsed.value = false
  activeTab.value = tab
}

onMounted(() => {
  if (gridStore.bas.length === 0) {
    gridStore.loadCongestionData()
  }
  if (enrichmentStore.hcUtilities.length === 0) {
    enrichmentStore.loadUtilities()
  }
})
</script>

<style scoped>
.border-primary {
  border-color: rgb(var(--v-theme-primary)) !important;
  border-width: 2px !important;
}
</style>
