<template>
  <div v-if="selectionStore.clickedPoint">
    <h3 class="text-h6 mb-3">Location Detail</h3>

    <div v-if="gridStore.isLoading" class="text-center pa-4">
      <v-progress-circular indeterminate size="24" />
      <div class="text-caption mt-2">Resolving location...</div>
    </div>

    <GeoResolutionCard :resolution="gridStore.resolvedLocation" />

    <NearbyContext
      v-if="selectionStore.clickedPoint"
      :lat="selectionStore.clickedPoint.lat"
      :lon="selectionStore.clickedPoint.lng"
    />
  </div>
  <div v-else class="text-center text-medium-emphasis pa-4">
    Click the map to select a location
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useSelectionStore } from '@/stores/selectionStore'
import { useGridDataStore } from '@/stores/gridDataStore'
import GeoResolutionCard from './GeoResolutionCard.vue'
import NearbyContext from './NearbyContext.vue'

const selectionStore = useSelectionStore()
const gridStore = useGridDataStore()

watch(
  () => selectionStore.clickedPoint,
  (pt) => {
    if (pt) {
      gridStore.resolveLocation(pt.lat, pt.lng)
    }
  },
)
</script>
