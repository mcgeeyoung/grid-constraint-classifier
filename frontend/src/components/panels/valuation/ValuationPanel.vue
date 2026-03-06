<template>
  <div>
    <div v-if="valuationStore.isComputing" class="text-center pa-4">
      <v-progress-circular indeterminate />
      <p class="mt-2 text-body-2">Computing valuation...</p>
    </div>
    <div v-else-if="valuationStore.error">
      <v-alert type="error" variant="tonal">{{ valuationStore.error }}</v-alert>
    </div>
    <div v-else-if="valuationStore.valueStack">
      <h3 class="text-h6 mb-2">DER Valuation</h3>
      <div class="d-flex align-center ga-2 mb-3">
        <TierChip :tier="valuationStore.valueStack.value_tier" type="value" />
        <span class="text-h6">${{ valuationStore.valueStack.total_value_per_kw_year.toFixed(0) }}/kW-yr</span>
      </div>

      <ValueStackChart :stack="valuationStore.valueStack" />
      <ProfileOverlay />

      <!-- Annotations from valuation -->
      <div v-if="valuationStore.valueStack.annotations.length > 0" class="mb-3">
        <div class="text-subtitle-2 mb-1">Regulatory Context</div>
        <AnnotationCard
          v-for="ann in valuationStore.valueStack.annotations"
          :key="ann.id"
          :annotation="ann"
          class="mb-1"
        />
      </div>

      <!-- Actions -->
      <v-btn
        color="primary"
        variant="outlined"
        size="small"
        block
        class="mb-2"
        :loading="isLoadingComparison"
        @click="loadComparison"
      >
        Compare All DER Types
      </v-btn>

      <DERComparison
        v-if="valuationStore.derComparison.length > 0"
        :comparisons="valuationStore.derComparison"
        @select-der="selectDER"
      />

      <v-btn
        color="secondary"
        variant="outlined"
        size="small"
        block
        class="mt-2"
        :disabled="valuationStore.isInComparison()"
        @click="valuationStore.addToComparison()"
      >
        Add to Comparison ({{ valuationStore.comparisonList.length }})
      </v-btn>
    </div>
    <div v-else class="text-center text-medium-emphasis pa-4">
      Click the map and evaluate a DER to see results
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useValuationStore } from '@/stores/valuationStore'
import TierChip from '@/components/shared/TierChip.vue'
import AnnotationCard from '@/components/panels/AnnotationCard.vue'
import ValueStackChart from './ValueStackChart.vue'
import ProfileOverlay from './ProfileOverlay.vue'
import DERComparison from './DERComparison.vue'

const valuationStore = useValuationStore()
const isLoadingComparison = ref(false)

async function loadComparison() {
  const geo = valuationStore.valueStack?.geo_resolution
  if (!geo) return
  isLoadingComparison.value = true
  try {
    await valuationStore.loadDERComparison(geo.lat, geo.lon)
  } finally {
    isLoadingComparison.value = false
  }
}

function selectDER(derType: string) {
  const geo = valuationStore.valueStack?.geo_resolution
  if (!geo) return
  valuationStore.computeProspective(geo.lat, geo.lon, derType)
}
</script>
