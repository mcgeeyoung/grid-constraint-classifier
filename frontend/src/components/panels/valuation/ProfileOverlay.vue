<template>
  <div v-if="hasProfile" class="mb-3">
    <h4 class="text-subtitle-2 mb-2">Constraint/DER Profile Overlay</h4>

    <div v-if="valuationStore.isProfileLoading" class="text-center pa-2">
      <v-progress-circular indeterminate size="20" />
    </div>

    <ProfileHeatmap
      v-else-if="constraintProfile12x24"
      :constraint-profile="constraintProfile12x24"
      :der-profile="derProfile12x24"
      :overlap-profile="overlapProfile12x24"
      size="large"
    />

    <!-- Metrics -->
    <div v-if="valuationStore.intersection" class="d-flex ga-4 mt-2 text-caption">
      <span>
        Coincidence: {{ (valuationStore.intersection.coincidence_factor * 100).toFixed(1) }}%
      </span>
      <span>
        Overlap hours: {{ valuationStore.intersection.overlap_hours }}
      </span>
      <TierChip :tier="valuationStore.intersection.value_tier" type="value" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useValuationStore } from '@/stores/valuationStore'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'
import TierChip from '@/components/shared/TierChip.vue'

const valuationStore = useValuationStore()

const hasProfile = computed(() => {
  const stack = valuationStore.valueStack
  return stack && stack.constraint_layers.length > 0
})

const constraintProfile12x24 = computed(() =>
  valuationStore.constraintProfile?.profile_12x24 ?? null,
)

const derProfile12x24 = computed(() =>
  valuationStore.derProfile?.profile_12x24 ?? null,
)

const overlapProfile12x24 = computed(() =>
  valuationStore.intersection?.overlap_12x24 ?? null,
)

// Load profiles when the value stack changes
watch(
  () => valuationStore.valueStack,
  async (stack) => {
    if (!stack || stack.constraint_layers.length === 0) return
    // Load the first constraint profile
    const layer = stack.constraint_layers[0]
    if (layer && stack.geo_resolution?.zone_code) {
      // Load DER profile for the selected DER type
      await valuationStore.loadDERProfile(valuationStore.selectedDERType)
    }
  },
  { immediate: true },
)
</script>
