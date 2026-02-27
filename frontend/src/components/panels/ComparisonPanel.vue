<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-3">
      <h3 class="text-subtitle-1">Site Comparison</h3>
      <v-btn
        v-if="valuationStore.comparisonList.length > 0"
        size="x-small"
        variant="text"
        color="error"
        @click="valuationStore.clearComparison()"
      >
        Clear All
      </v-btn>
    </div>

    <div v-if="sortedEntries.length === 0" class="text-body-2 text-medium-emphasis text-center pa-4">
      No sites saved for comparison yet. Evaluate a site and click "Add to Comparison".
    </div>

    <div v-else>
      <v-card
        v-for="(entry, idx) in sortedEntries"
        :key="entry.originalIndex"
        :variant="entry.originalIndex === valuationStore.selectedComparisonIndex ? 'tonal' : 'outlined'"
        :class="{ 'border-primary': idx === 0 }"
        class="mb-2 pa-3"
        style="cursor: pointer;"
        @click="onSelect(entry.originalIndex)"
      >
        <div class="d-flex align-center justify-space-between">
          <div class="d-flex align-center ga-2">
            <v-avatar size="24" :color="tierColor(entry.result.value_tier)" class="text-caption font-weight-bold">
              {{ entry.originalIndex + 1 }}
            </v-avatar>
            <div>
              <div class="text-body-2 font-weight-medium">
                {{ entry.result.geo_resolution?.zone_code ?? 'Unknown' }}
                <v-chip v-if="idx === 0" size="x-small" color="success" variant="flat" class="ml-1">Best</v-chip>
              </div>
              <div class="text-caption text-medium-emphasis">
                {{ entry.lat.toFixed(4) }}, {{ entry.lon.toFixed(4) }}
              </div>
            </div>
          </div>
          <div class="text-right">
            <div class="text-body-2 font-weight-bold">
              ${{ entry.result.value_per_kw_year.toFixed(0) }}/kW-yr
            </div>
            <v-chip :color="tierColor(entry.result.value_tier)" size="x-small" variant="flat">
              {{ entry.result.value_tier }}
            </v-chip>
          </div>
        </div>

        <div class="d-flex align-center justify-space-between mt-2">
          <div class="text-caption text-medium-emphasis">
            {{ entry.derType }} &middot; {{ entry.capacityMw }} MW
          </div>
          <v-btn
            icon
            size="x-small"
            variant="text"
            color="error"
            @click.stop="valuationStore.removeFromComparison(entry.originalIndex)"
          >
            <v-icon size="14">mdi-close</v-icon>
          </v-btn>
        </div>

        <!-- Mini value bar -->
        <div class="mt-1" style="height: 6px; border-radius: 3px; overflow: hidden; background: rgba(255,255,255,0.08);">
          <div
            :style="{
              width: (entry.result.total_constraint_relief_value / maxValue * 100) + '%',
              height: '100%',
              background: tierColor(entry.result.value_tier),
              borderRadius: '3px',
            }"
          />
        </div>
      </v-card>

      <!-- Summary -->
      <v-card variant="outlined" class="pa-3 mt-3">
        <div class="text-caption text-medium-emphasis mb-1">Comparison Summary</div>
        <div class="d-flex justify-space-between text-body-2">
          <span>Sites</span>
          <span class="font-weight-medium">{{ sortedEntries.length }}</span>
        </div>
        <div class="d-flex justify-space-between text-body-2">
          <span>Best $/kW-yr</span>
          <span class="font-weight-medium" style="color: #2ecc71;">
            ${{ sortedEntries[0]?.result.value_per_kw_year.toFixed(0) ?? '-' }}
          </span>
        </div>
        <div class="d-flex justify-space-between text-body-2">
          <span>Avg $/kW-yr</span>
          <span class="font-weight-medium">
            ${{ avgValuePerKw.toFixed(0) }}
          </span>
        </div>
      </v-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useValuationStore, type ComparisonEntry } from '@/stores/valuationStore'

const valuationStore = useValuationStore()

const emit = defineEmits<{
  (e: 'select-site', index: number): void
}>()

interface SortedEntry extends ComparisonEntry {
  originalIndex: number
}

const sortedEntries = computed<SortedEntry[]>(() => {
  return valuationStore.comparisonList
    .map((entry, idx) => ({ ...entry, originalIndex: idx }))
    .sort((a, b) => b.result.total_constraint_relief_value - a.result.total_constraint_relief_value)
})

const maxValue = computed(() => {
  if (sortedEntries.value.length === 0) return 1
  return Math.max(...sortedEntries.value.map(e => e.result.total_constraint_relief_value), 1)
})

const avgValuePerKw = computed(() => {
  if (sortedEntries.value.length === 0) return 0
  const sum = sortedEntries.value.reduce((s, e) => s + e.result.value_per_kw_year, 0)
  return sum / sortedEntries.value.length
})

function tierColor(tier: string): string {
  switch (tier) {
    case 'premium': return '#c0392b'
    case 'high': return '#e67e22'
    case 'moderate': return '#f1c40f'
    case 'low': return '#27ae60'
    default: return '#666'
  }
}

function onSelect(index: number) {
  valuationStore.selectComparison(index)
  emit('select-site', index)
}
</script>
