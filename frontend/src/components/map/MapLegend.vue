<template>
  <div style="position: absolute; bottom: 16px; left: 12px; z-index: 1000;">
    <div class="glass-panel pa-2" style="min-width: 150px;">
      <!-- Zone legend -->
      <div v-if="mapStore.showZones" class="mb-2">
        <div class="text-caption font-weight-bold mb-1">
          Zones: {{ zoneLegendTitle }}
        </div>
        <template v-if="mapStore.zoneColorMode === 'classification'">
          <div v-for="item in classificationLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
            <span :style="{ width: '12px', height: '12px', borderRadius: '2px', background: item.color, display: 'inline-block' }" />
            <span class="text-caption">{{ item.label }}</span>
          </div>
        </template>
        <template v-else-if="mapStore.zoneColorMode === 'severity'">
          <div v-for="item in severityLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
            <span :style="{ width: '12px', height: '12px', borderRadius: '2px', background: item.color, display: 'inline-block' }" />
            <span class="text-caption">{{ item.label }}</span>
          </div>
        </template>
        <template v-else>
          <div class="d-flex align-center ga-1">
            <div style="height: 10px; width: 100px; border-radius: 2px; background: linear-gradient(to right, #22c55e, #facc15, #ef4444);" />
          </div>
          <div class="d-flex justify-space-between text-caption" style="width: 100px; color: var(--text-secondary);">
            <span>Low</span><span>High</span>
          </div>
        </template>
      </div>

      <!-- DER value tier legend -->
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

      <!-- Hosting capacity legend -->
      <div v-if="mapStore.showHostingCapacity" class="mb-2">
        <div class="text-caption font-weight-bold mb-1">Remaining Capacity</div>
        <div class="d-flex align-center ga-1">
          <div style="height: 10px; width: 100px; border-radius: 2px; background: linear-gradient(to right, #ef4444, #fb923c, #facc15, #22c55e);" />
        </div>
        <div class="d-flex justify-space-between text-caption" style="width: 100px; color: var(--text-secondary);">
          <span>0 MW</span><span>5+ MW</span>
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
          <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: item.color, border: '1.5px solid var(--border-strong)', display: 'inline-block' }" />
          <span class="text-caption">{{ item.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMapStore } from '@/stores/mapStore'

const mapStore = useMapStore()

const zoneLegendTitle = computed(() => {
  switch (mapStore.zoneColorMode) {
    case 'severity': return 'Constraint Severity'
    case 'value': return 'Congestion Value'
    default: return 'Classification'
  }
})

const classificationLegend = [
  { label: 'Transmission', color: '#ef4444' },
  { label: 'Generation', color: '#38bdf8' },
  { label: 'Both', color: '#c084fc' },
  { label: 'Unconstrained', color: '#4ade80' },
]

const severityLegend = [
  { label: 'Critical (>= 0.75)', color: '#ef4444' },
  { label: 'Elevated (>= 0.50)', color: '#f59e0b' },
  { label: 'Moderate (>= 0.25)', color: '#eab308' },
  { label: 'Low (< 0.25)', color: '#22c55e' },
]

const tierLegend = [
  { label: 'Premium', color: '#ef4444' },
  { label: 'High', color: '#f59e0b' },
  { label: 'Moderate', color: '#facc15' },
  { label: 'Low', color: '#22c55e' },
]

const loadingLegend = [
  { label: '> 100%', color: '#ef4444' },
  { label: '80-100%', color: '#f59e0b' },
  { label: '60-80%', color: '#eab308' },
  { label: '< 60%', color: '#22c55e' },
]

const dcLegend = [
  { label: 'Operational', color: '#38bdf8' },
  { label: 'Planned', color: '#fb923c' },
  { label: 'Under Construction', color: '#facc15' },
  { label: 'Proposed', color: '#c084fc' },
]

const pnodeLegend = [
  { label: 'Critical', color: '#ef4444' },
  { label: 'Severe', color: '#f59e0b' },
  { label: 'Moderate', color: '#eab308' },
  { label: 'Low', color: '#22c55e' },
]

const assetLegend = [
  { label: 'Solar', color: '#facc15' },
  { label: 'Storage', color: '#c084fc' },
  { label: 'Demand Response', color: '#38bdf8' },
  { label: 'Wind', color: '#22d3ee' },
  { label: 'EV Charger', color: '#ef4444' },
]
</script>
