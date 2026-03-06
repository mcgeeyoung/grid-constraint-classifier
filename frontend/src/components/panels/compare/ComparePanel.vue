<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-3">
      <h3 class="text-h6">Site Comparison</h3>
      <v-btn
        v-if="valuationStore.comparisonList.length > 0"
        size="x-small"
        variant="text"
        @click="valuationStore.clearComparison()"
      >
        Clear All
      </v-btn>
    </div>

    <CompareSummary
      v-if="valuationStore.comparisonList.length > 0"
      :entries="valuationStore.comparisonList"
      @select="onSelect"
      @remove="valuationStore.removeFromComparison"
    />

    <div v-else class="text-center text-medium-emphasis pa-4">
      Evaluate sites and add them to compare
    </div>
  </div>
</template>

<script setup lang="ts">
import { useValuationStore } from '@/stores/valuationStore'
import { useSelectionStore } from '@/stores/selectionStore'
import CompareSummary from './CompareSummary.vue'

const valuationStore = useValuationStore()
const selectionStore = useSelectionStore()

function onSelect(index: number) {
  valuationStore.selectComparison(index)
  selectionStore.showValuation()
}
</script>
