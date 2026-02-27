<template>
  <div style="position: absolute; bottom: 16px; left: 12px; z-index: 1000;">
    <v-card density="compact" class="pa-2" style="background: rgba(30,30,46,0.92); min-width: 150px;">
      <!-- Zone legend -->
      <div v-if="mapStore.showZones" class="mb-2">
        <div class="text-caption font-weight-bold mb-1">
          Zones: {{ mapStore.zoneColorMode === 'value' ? 'Congestion Value' : 'Classification' }}
        </div>
        <template v-if="mapStore.zoneColorMode === 'classification'">
          <div v-for="item in classificationLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
            <span :style="{ width: '12px', height: '12px', borderRadius: '2px', background: item.color, display: 'inline-block' }" />
            <span class="text-caption">{{ item.label }}</span>
          </div>
        </template>
        <template v-else>
          <div class="d-flex align-center ga-1">
            <div style="height: 10px; width: 100px; border-radius: 2px; background: linear-gradient(to right, #2ecc71, #f1c40f, #e74c3c);" />
          </div>
          <div class="d-flex justify-space-between text-caption text-medium-emphasis" style="width: 100px;">
            <span>Low</span><span>High</span>
          </div>
        </template>
      </div>

      <!-- DER tier legend -->
      <div v-if="mapStore.showDERs" class="mb-2">
        <div class="text-caption font-weight-bold mb-1">DER Value Tier</div>
        <div v-for="item in tierLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
          <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: item.color, display: 'inline-block' }" />
          <span class="text-caption">{{ item.label }}</span>
        </div>
      </div>

      <!-- Substation loading legend -->
      <div v-if="mapStore.showSubstations" class="mb-2">
        <div class="text-caption font-weight-bold mb-1">Substation Loading</div>
        <div v-for="item in loadingLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
          <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: item.color, display: 'inline-block' }" />
          <span class="text-caption">{{ item.label }}</span>
        </div>
      </div>

      <!-- Data center legend -->
      <div v-if="mapStore.showDataCenters" class="mb-2">
        <div class="text-caption font-weight-bold mb-1">Data Centers</div>
        <div v-for="item in dcLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
          <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: item.color, display: 'inline-block' }" />
          <span class="text-caption">{{ item.label }}</span>
        </div>
      </div>

      <!-- Pnode severity legend -->
      <div v-if="mapStore.selectedZoneCode && mapStore.zoom >= 8" class="mb-2">
        <div class="text-caption font-weight-bold mb-1">Pnode Severity</div>
        <div v-for="item in pnodeLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
          <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: item.color, display: 'inline-block' }" />
          <span class="text-caption">{{ item.label }}</span>
        </div>
      </div>

      <!-- WattCarbon assets legend -->
      <div v-if="mapStore.showAssets">
        <div class="text-caption font-weight-bold mb-1">WattCarbon Assets</div>
        <div v-for="item in assetLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
          <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: item.color, border: '1.5px solid #fff', display: 'inline-block' }" />
          <span class="text-caption">{{ item.label }}</span>
        </div>
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { useMapStore } from '@/stores/mapStore'

const mapStore = useMapStore()

const classificationLegend = [
  { label: 'Transmission', color: '#e74c3c' },
  { label: 'Generation', color: '#3498db' },
  { label: 'Both', color: '#9b59b6' },
  { label: 'Unconstrained', color: '#2ecc71' },
]

const tierLegend = [
  { label: 'Premium', color: '#c0392b' },
  { label: 'High', color: '#e67e22' },
  { label: 'Moderate', color: '#f1c40f' },
  { label: 'Low', color: '#27ae60' },
]

const loadingLegend = [
  { label: '> 100%', color: '#e74c3c' },
  { label: '80-100%', color: '#e67e22' },
  { label: '60-80%', color: '#f1c40f' },
  { label: '< 60%', color: '#2ecc71' },
]

const dcLegend = [
  { label: 'Operational', color: '#3498db' },
  { label: 'Planned', color: '#e67e22' },
  { label: 'Under Construction', color: '#f1c40f' },
  { label: 'Proposed', color: '#9b59b6' },
]

const pnodeLegend = [
  { label: 'Critical', color: '#e74c3c' },
  { label: 'Severe', color: '#e67e22' },
  { label: 'Moderate', color: '#f1c40f' },
  { label: 'Low', color: '#2ecc71' },
]

const assetLegend = [
  { label: 'Solar', color: '#f39c12' },
  { label: 'Storage', color: '#8e44ad' },
  { label: 'Demand Response', color: '#2980b9' },
  { label: 'Wind', color: '#1abc9c' },
  { label: 'EV Charger', color: '#e74c3c' },
]
</script>
