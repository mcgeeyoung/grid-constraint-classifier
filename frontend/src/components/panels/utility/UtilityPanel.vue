<template>
  <div>
    <div v-if="isLoading" class="text-center pa-4">
      <v-progress-circular indeterminate size="24" />
    </div>

    <template v-if="utility">
      <h3 class="text-h6 mb-1">{{ utility.utility_name }}</h3>
      <div class="d-flex flex-wrap ga-2 text-caption mb-3" style="color: var(--text-secondary);">
        <span v-if="utility.parent_company">{{ utility.parent_company }}</span>
        <span v-if="utility.states?.length">{{ utility.states.join(', ') }}</span>
        <span>{{ utility.data_source_type }}</span>
      </div>

      <!-- HC Summary Stats -->
      <div v-if="summary" class="mb-4">
        <div class="text-subtitle-2 mb-2">Hosting Capacity Summary</div>
        <div class="d-flex flex-wrap ga-3">
          <div class="stat-box">
            <div class="stat-value">{{ summary.total_feeders.toLocaleString() }}</div>
            <div class="stat-label">Feeders</div>
          </div>
          <div class="stat-box">
            <div class="stat-value">{{ Math.round(summary.total_hosting_capacity_mw).toLocaleString() }}</div>
            <div class="stat-label">Total MW</div>
          </div>
          <div class="stat-box">
            <div class="stat-value">{{ Math.round(summary.total_remaining_capacity_mw).toLocaleString() }}</div>
            <div class="stat-label">Remaining MW</div>
          </div>
          <div v-if="summary.avg_utilization_pct != null" class="stat-box">
            <div class="stat-value">{{ Math.round(summary.avg_utilization_pct) }}%</div>
            <div class="stat-label">Avg Utilization</div>
          </div>
          <div class="stat-box">
            <div class="stat-value">{{ summary.constrained_feeders_count.toLocaleString() }}</div>
            <div class="stat-label">Constrained</div>
          </div>
        </div>
      </div>

      <!-- HC 12x24 Profile Heatmap -->
      <div v-if="enrichmentStore.isHCProfileLoading" class="text-center pa-2">
        <v-progress-circular indeterminate size="20" />
      </div>
      <div v-else-if="enrichmentStore.selectedHCProfile">
        <div class="text-subtitle-2 mb-2">Hosting Capacity 12x24 Profile</div>
        <ProfileHeatmap
          :constraint-profile="invertedProfile"
          size="large"
          :show-labels="true"
          :show-legend="false"
          :highlight-peak="true"
          :peak-month="invertedPeak.month"
          :peak-hour="invertedPeak.hour"
          constraint-label="HC Constraint"
        />
        <div class="text-caption text-medium-emphasis mt-2" style="line-height: 1.5;">
          Peak constraint: Month {{ invertedPeak.month }},
          Hour {{ invertedPeak.hour }}.
          Brighter red cells indicate hours with less available hosting capacity.
        </div>
      </div>

      <!-- View feeders on map -->
      <v-btn
        v-if="utility"
        variant="outlined"
        size="small"
        block
        class="mt-4"
        @click="onViewFeeders"
      >
        <v-icon start size="16">mdi-map-marker-multiple</v-icon>
        View Feeders on Map
      </v-btn>
    </template>

    <div v-if="!isLoading && !utility" class="text-center text-medium-emphasis pa-4">
      Utility not found.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { useSelectionStore } from '@/stores/selectionStore'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import { useMapStore } from '@/stores/mapStore'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'

const selectionStore = useSelectionStore()
const enrichmentStore = useEnrichmentStore()
const mapStore = useMapStore()

const isLoading = computed(() => enrichmentStore.isLoading)

const utility = computed(() => {
  const code = selectionStore.selectedUtilityCode
  if (!code) return null
  return enrichmentStore.hcUtilities.find(u => u.utility_code === code) ?? null
})

const summary = computed(() => enrichmentStore.hcSummary)

// Invert the profile so less capacity = brighter red
const invertedProfile = computed<Record<string, number[]> | null>(() => {
  const raw = enrichmentStore.selectedHCProfile?.profile_12x24
  if (!raw) return null
  let max = 0
  for (let m = 1; m <= 12; m++) {
    for (const v of raw[String(m)] ?? []) {
      if (v > max) max = v
    }
  }
  if (max === 0) return raw
  const result: Record<string, number[]> = {}
  for (let m = 1; m <= 12; m++) {
    result[String(m)] = (raw[String(m)] ?? []).map(v => max - v)
  }
  return result
})

// Find peak of the inverted profile (minimum raw capacity = maximum constraint)
const invertedPeak = computed<{ month: number; hour: number }>(() => {
  const profile = invertedProfile.value
  if (!profile) {
    const hc = enrichmentStore.selectedHCProfile
    return { month: hc?.peak_month ?? 1, hour: hc?.peak_hour ?? 0 }
  }
  let peakMonth = 1
  let peakHour = 0
  let peakVal = -1
  for (let m = 1; m <= 12; m++) {
    const row = profile[String(m)] ?? []
    for (let h = 0; h < row.length; h++) {
      if (row[h] > peakVal) {
        peakVal = row[h]
        peakMonth = m
        peakHour = h
      }
    }
  }
  return { month: peakMonth, hour: peakHour }
})

// Load summary + profile when utility changes
watchEffect(() => {
  const code = selectionStore.selectedUtilityCode
  if (!code) return
  enrichmentStore.loadFeeders(code)
  enrichmentStore.loadHCProfile(code)
})

function onViewFeeders() {
  if (!utility.value) return
  mapStore.showFeeders = true
  mapStore.showHostingCapacity = true
}
</script>

<style scoped>
.stat-box {
  flex: 1;
  min-width: 70px;
  padding: 8px;
  border-radius: 6px;
  background: var(--bg-surface-2, rgba(255,255,255,0.05));
  text-align: center;
}
.stat-value {
  font-size: 1.1rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.stat-label {
  font-size: 0.7rem;
  color: var(--text-secondary, rgba(255,255,255,0.5));
  margin-top: 2px;
}
</style>
