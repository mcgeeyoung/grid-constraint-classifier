<template>
  <v-card variant="outlined" class="pa-3 mb-3">
    <div class="text-subtitle-2 mb-2">Value Stack</div>

    <!-- Stacked horizontal bar -->
    <div class="d-flex mb-2" style="height: 24px; border-radius: 4px; overflow: hidden;">
      <div
        v-for="seg in segments"
        :key="seg.label"
        :style="{ width: seg.pct + '%', background: seg.color, minWidth: seg.value > 0 ? '4px' : '0' }"
        :title="`${seg.label}: $${seg.value.toFixed(1)}/kW-yr`"
      />
    </div>

    <!-- Legend -->
    <div class="d-flex flex-wrap ga-3 mb-2">
      <span v-for="seg in segments" :key="seg.label" class="d-flex align-center ga-1 text-caption">
        <span :style="{ width: '8px', height: '8px', borderRadius: '2px', background: seg.color, display: 'inline-block' }" />
        {{ seg.label }}: ${{ seg.value.toFixed(1) }}
      </span>
    </div>

    <!-- Total and coincidence -->
    <div class="d-flex align-center justify-space-between">
      <span class="text-body-2 font-weight-bold">
        Total: ${{ stack.total_value_per_kw_year.toFixed(1) }}/kW-yr
      </span>
      <span class="text-caption text-medium-emphasis">
        Coincidence: {{ (stack.composite_coincidence_factor * 100).toFixed(1) }}%
      </span>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ValueStack } from '@/types/constraints'

const props = defineProps<{
  stack: ValueStack
}>()

const segments = computed(() => {
  const total = props.stack.total_value_per_kw_year || 1
  return [
    { label: 'Congestion', value: props.stack.congestion_value_per_kw_year, color: '#38bdf8', pct: (props.stack.congestion_value_per_kw_year / total) * 100 },
    { label: 'Loading', value: props.stack.loading_value_per_kw_year, color: '#fb923c', pct: (props.stack.loading_value_per_kw_year / total) * 100 },
    { label: 'Capacity', value: props.stack.capacity_value_per_kw_year, color: '#4ade80', pct: (props.stack.capacity_value_per_kw_year / total) * 100 },
    { label: 'Import Stress', value: props.stack.import_stress_value_per_kw_year, color: '#c084fc', pct: (props.stack.import_stress_value_per_kw_year / total) * 100 },
  ]
})
</script>
