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
      <div v-if="mapStore.showSubstations">
        <div class="text-caption font-weight-bold mb-1">Substation Loading</div>
        <div v-for="item in loadingLegend" :key="item.label" class="d-flex align-center ga-1 mb-px">
          <span :style="{ width: '10px', height: '10px', borderRadius: '50%', background: item.color, display: 'inline-block' }" />
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
</script>
