<template>
  <div>
    <v-card
      v-for="(entry, i) in entries"
      :key="i"
      variant="outlined"
      density="compact"
      class="pa-2 mb-1"
      style="cursor: pointer;"
      @click="$emit('select', i)"
    >
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-body-2">{{ derLabel(entry.derType) }}</div>
          <div class="text-caption text-medium-emphasis">
            {{ entry.lat.toFixed(3) }}, {{ entry.lon.toFixed(3) }}
          </div>
        </div>
        <div class="d-flex align-center ga-2">
          <!-- Mini value bar -->
          <div style="width: 60px; height: 8px; border-radius: 4px; overflow: hidden; display: flex;">
            <div :style="{ width: congPct(entry) + '%', background: '#38bdf8' }" />
            <div :style="{ width: loadPct(entry) + '%', background: '#fb923c' }" />
            <div :style="{ width: capPct(entry) + '%', background: '#4ade80' }" />
            <div :style="{ width: impPct(entry) + '%', background: '#c084fc' }" />
          </div>
          <TierChip :tier="entry.result.value_tier" type="value" />
          <span class="text-body-2 font-weight-medium">${{ entry.result.total_value_per_kw_year.toFixed(0) }}</span>
          <v-btn icon size="x-small" variant="text" @click.stop="$emit('remove', i)">
            <v-icon size="14">mdi-close</v-icon>
          </v-btn>
        </div>
      </div>
    </v-card>

    <!-- Summary -->
    <v-card v-if="entries.length >= 2" variant="tonal" class="pa-3 mt-3">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-caption text-medium-emphasis">Best site</div>
          <div class="text-body-2 font-weight-medium">
            {{ derLabel(best.derType) }} at {{ best.lat.toFixed(3) }}, {{ best.lon.toFixed(3) }}
          </div>
        </div>
        <span class="text-h6 font-weight-bold">${{ best.result.total_value_per_kw_year.toFixed(0) }}/kW-yr</span>
      </div>
      <div class="text-caption text-medium-emphasis mt-1">
        Average: ${{ avgValue.toFixed(0) }}/kW-yr across {{ entries.length }} sites
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ComparisonEntry } from '@/stores/valuationStore'
import TierChip from '@/components/shared/TierChip.vue'
import { derLabel } from '@/utils/derLabels'

const props = defineProps<{
  entries: ComparisonEntry[]
}>()

defineEmits<{
  select: [index: number]
  remove: [index: number]
}>()

const best = computed(() =>
  [...props.entries].sort((a, b) => b.result.total_value_per_kw_year - a.result.total_value_per_kw_year)[0],
)

const avgValue = computed(() => {
  const sum = props.entries.reduce((s, e) => s + e.result.total_value_per_kw_year, 0)
  return sum / (props.entries.length || 1)
})

function pctOf(entry: ComparisonEntry, val: number): number {
  const total = entry.result.total_value_per_kw_year || 1
  return (val / total) * 100
}

function congPct(e: ComparisonEntry) { return pctOf(e, e.result.congestion_value_per_kw_year) }
function loadPct(e: ComparisonEntry) { return pctOf(e, e.result.loading_value_per_kw_year) }
function capPct(e: ComparisonEntry) { return pctOf(e, e.result.capacity_value_per_kw_year) }
function impPct(e: ComparisonEntry) { return pctOf(e, e.result.import_stress_value_per_kw_year) }
</script>
