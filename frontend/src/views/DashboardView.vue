<template>
  <div style="height: calc(100vh - 48px); display: flex;">
    <!-- Map -->
    <div style="flex: 1; position: relative;">
      <GridMapGL v-if="mapStore.mapEngine === 'maplibre'" />
      <GridMap v-else />

      <!-- Layer controls (floating) -->
      <div style="position: absolute; top: 12px; left: 12px; z-index: 1000;">
        <v-card density="compact" class="pa-2" style="background: rgba(255,255,255,0.92);">
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
            v-model="mapStore.showSubstations"
            label="Substations"
            density="compact"
            hide-details
            color="warning"
            @update:model-value="(v: any) => onSubstationToggle(!!v)"
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
            label="WattCarbon Assets"
            density="compact"
            hide-details
            color="purple"
          />
          <v-divider class="my-1" />
          <v-btn-toggle
            :model-value="mapStore.mapEngine"
            @update:model-value="(v: any) => { if (v) mapStore.mapEngine = v }"
            mandatory
            density="compact"
            color="primary"
            variant="outlined"
            divided
          >
            <v-btn value="maplibre" size="x-small">WebGL</v-btn>
            <v-btn value="leaflet" size="x-small">Leaflet</v-btn>
          </v-btn-toggle>
        </v-card>
      </div>

      <!-- Loading indicator -->
      <v-progress-linear
        v-if="isoStore.isLoading"
        indeterminate
        color="primary"
        style="position: absolute; top: 0; left: 0; right: 0; z-index: 1000;"
      />
    </div>

    <!-- Right panel -->
    <div
      v-if="showPanel"
      style="width: 400px; border-left: 1px solid #ddd; overflow-y: auto; background: #ffffff;"
    >
      <div class="pa-2 pb-0">
        <FilterBar />
      </div>
      <v-tabs v-model="activeTab" density="compact" bg-color="surface">
        <v-tab value="valuation">Valuation</v-tab>
        <v-tab value="zone">Zone</v-tab>
        <v-tab value="substation">Substation</v-tab>
        <v-tab value="compare">
          Compare
          <v-badge
            v-if="valuationStore.comparisonList.length > 0"
            :content="valuationStore.comparisonList.length"
            color="secondary"
            inline
          />
        </v-tab>
        <v-tab value="asset">Asset</v-tab>
        <v-tab value="hierarchy">Hierarchy</v-tab>
      </v-tabs>

      <div class="pa-4">
        <ValuationResult v-if="activeTab === 'valuation'" />
        <ZoneDetail v-else-if="activeTab === 'zone'" />
        <SubstationDetail v-else-if="activeTab === 'substation'" />
        <ComparisonPanel v-else-if="activeTab === 'compare'" @select-site="activeTab = 'valuation'" />
        <AssetDetail v-else-if="activeTab === 'asset'" />
        <HierarchyTree v-else-if="activeTab === 'hierarchy'" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import GridMap from '@/components/map/GridMap.vue'
import GridMapGL from '@/components/map/GridMapGL.vue'
import ValuationResult from '@/components/panels/ValuationResult.vue'
import ZoneDetail from '@/components/panels/ZoneDetail.vue'
import SubstationDetail from '@/components/panels/SubstationDetail.vue'
import FilterBar from '@/components/panels/FilterBar.vue'
import ComparisonPanel from '@/components/panels/ComparisonPanel.vue'
import AssetDetail from '@/components/panels/AssetDetail.vue'
import HierarchyTree from '@/components/panels/HierarchyTree.vue'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'
import { useHierarchyStore } from '@/stores/hierarchyStore'
import { useValuationStore } from '@/stores/valuationStore'

const isoStore = useIsoStore()
const mapStore = useMapStore()
const hierarchyStore = useHierarchyStore()
const valuationStore = useValuationStore()

const showPanel = ref(true)
const activeTab = ref('valuation')

// Switch to zone tab when a zone is selected
watch(() => mapStore.selectedZoneCode, (code) => {
  if (code) activeTab.value = 'zone'
})

// Switch to substation tab when a substation is selected
watch(() => mapStore.selectedSubstationId, (id) => {
  if (id) activeTab.value = 'substation'
})

// Switch to asset tab when an asset is selected
watch(() => mapStore.selectedAssetId, (id) => {
  if (id) activeTab.value = 'asset'
})

// Switch to valuation tab when a valuation completes
watch(() => valuationStore.sitingResult, (result) => {
  if (result) activeTab.value = 'valuation'
})

// Load substations when layer toggled on
function onSubstationToggle(val: boolean) {
  if (val && isoStore.selectedISO && hierarchyStore.substations.length === 0) {
    hierarchyStore.loadSubstations(isoStore.selectedISO)
  }
}

// Load substations when ISO changes (if layer is active)
watch(() => isoStore.selectedISO, (iso) => {
  if (iso && mapStore.showSubstations) {
    hierarchyStore.loadSubstations(iso)
  }
})
</script>
