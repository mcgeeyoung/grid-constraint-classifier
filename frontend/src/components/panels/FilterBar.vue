<template>
  <v-card density="compact" class="pa-2 mb-2" variant="outlined">
    <div
      class="d-flex align-center justify-space-between"
      style="cursor: pointer;"
      @click="expanded = !expanded"
    >
      <span class="text-caption font-weight-bold">
        <v-icon size="14" class="mr-1">mdi-filter</v-icon>
        Filters
        <v-chip v-if="activeFilterCount > 0" size="x-small" color="primary" class="ml-1">
          {{ activeFilterCount }}
        </v-chip>
      </span>
      <v-icon size="16">{{ expanded ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
    </div>

    <div v-if="expanded" class="mt-2">
      <!-- Classification filter -->
      <div class="mb-2">
        <div class="text-caption text-medium-emphasis mb-1">Zone Classification</div>
        <v-chip-group
          v-model="mapStore.filterClassifications"
          multiple
          column
        >
          <v-chip
            v-for="cls in classifications"
            :key="cls.value"
            :color="cls.color"
            size="x-small"
            filter
            variant="outlined"
            :value="cls.value"
          >
            {{ cls.label }}
          </v-chip>
        </v-chip-group>
      </div>

      <!-- Value tier filter -->
      <div class="mb-2">
        <div class="text-caption text-medium-emphasis mb-1">DER Value Tier</div>
        <v-chip-group
          v-model="mapStore.filterTiers"
          multiple
          column
        >
          <v-chip
            v-for="tier in tiers"
            :key="tier.value"
            :color="tier.color"
            size="x-small"
            filter
            variant="outlined"
            :value="tier.value"
          >
            {{ tier.label }}
          </v-chip>
        </v-chip-group>
      </div>

      <!-- DER type filter -->
      <div class="mb-2">
        <v-select
          v-model="mapStore.filterDerType"
          :items="derTypes"
          label="DER Type"
          density="compact"
          variant="outlined"
          clearable
          hide-details
        />
      </div>

      <!-- Loading threshold -->
      <div class="mb-1">
        <div class="text-caption text-medium-emphasis mb-1">
          Min Substation Loading: {{ mapStore.filterMinLoading }}%
        </div>
        <v-slider
          v-model="mapStore.filterMinLoading"
          :min="0"
          :max="100"
          :step="5"
          density="compact"
          hide-details
          color="warning"
          thumb-label
        />
      </div>

      <!-- Clear all -->
      <v-btn
        v-if="activeFilterCount > 0"
        size="x-small"
        variant="text"
        color="error"
        block
        @click="clearFilters"
      >
        Clear All Filters
      </v-btn>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useMapStore } from '@/stores/mapStore'

const mapStore = useMapStore()
const expanded = ref(false)

const classifications = [
  { value: 'transmission', label: 'Transmission', color: '#e74c3c' },
  { value: 'generation', label: 'Generation', color: '#3498db' },
  { value: 'both', label: 'Both', color: '#9b59b6' },
  { value: 'unconstrained', label: 'Unconstrained', color: '#2ecc71' },
]

const tiers = [
  { value: 'premium', label: 'Premium', color: '#c0392b' },
  { value: 'high', label: 'High', color: '#e67e22' },
  { value: 'moderate', label: 'Moderate', color: '#f1c40f' },
  { value: 'low', label: 'Low', color: '#27ae60' },
]

const derTypes = ['solar', 'storage', 'wind', 'demand_response', 'ev_charger']

const activeFilterCount = computed(() => {
  let count = 0
  if (mapStore.filterClassifications.length > 0) count++
  if (mapStore.filterTiers.length > 0) count++
  if (mapStore.filterDerType) count++
  if (mapStore.filterMinLoading > 0) count++
  return count
})

function clearFilters() {
  mapStore.filterClassifications = []
  mapStore.filterTiers = []
  mapStore.filterDerType = null
  mapStore.filterMinLoading = 0
}
</script>
