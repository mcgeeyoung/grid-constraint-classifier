<template>
  <div class="mb-3">
    <h4 class="text-subtitle-2 mb-2">DER Type Comparison</h4>

    <v-card
      v-for="item in comparisons"
      :key="item.der_type"
      variant="outlined"
      density="compact"
      class="pa-2 mb-1"
      style="cursor: pointer;"
      @click="$emit('selectDer', item.der_type)"
    >
      <div class="d-flex align-center justify-space-between">
        <div class="d-flex align-center ga-2">
          <DERLabel :der-type="item.der_type" :show-icon="true" />
          <v-chip v-if="item.is_dispatchable" size="x-small" variant="tonal" color="info">
            dispatchable
          </v-chip>
        </div>
        <div class="d-flex align-center ga-2">
          <TierChip :tier="item.value_tier" type="value" />
          <span class="text-body-2 font-weight-medium">${{ item.total_value_per_kw_year.toFixed(0) }}</span>
        </div>
      </div>
      <div class="text-caption text-medium-emphasis mt-1">
        Coincidence: {{ (item.coincidence_factor * 100).toFixed(1) }}%
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import type { DERComparisonItem } from '@/types/constraints'
import TierChip from '@/components/shared/TierChip.vue'
import DERLabel from '@/components/shared/DERLabel.vue'

defineProps<{
  comparisons: DERComparisonItem[]
}>()

defineEmits<{
  selectDer: [derType: string]
}>()
</script>
