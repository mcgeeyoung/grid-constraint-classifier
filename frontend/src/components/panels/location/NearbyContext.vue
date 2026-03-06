<template>
  <div>
    <h4 class="text-subtitle-2 mb-2">Nearby</h4>

    <div v-if="enrichmentStore.isNearbyLoading" class="text-center pa-2">
      <v-progress-circular indeterminate size="20" />
    </div>

    <!-- Hosting Capacity -->
    <div v-if="enrichmentStore.nearbyFeeders.length > 0" class="mb-2">
      <div class="text-caption font-weight-medium mb-1">Hosting Capacity Feeders</div>
      <div
        v-for="(f, i) in enrichmentStore.nearbyFeeders.slice(0, 5)"
        :key="i"
        class="d-flex align-center justify-space-between mb-1 text-caption"
      >
        <span class="text-truncate mr-2">{{ f.feeder_name || f.substation_name || '-' }}</span>
        <span v-if="f.remaining_capacity_mw != null" class="text-medium-emphasis text-no-wrap">
          {{ f.remaining_capacity_mw.toFixed(1) }} MW
        </span>
        <v-chip
          v-else-if="f.capacity_status"
          size="x-small"
          :color="capacityStatusColor(f.capacity_status)"
          variant="flat"
          class="text-no-wrap"
        >
          {{ shortStatus(f.capacity_status) }}
        </v-chip>
        <span v-else class="text-medium-emphasis">-</span>
      </div>

      <!-- HC Availability Heatmap -->
      <div v-if="enrichmentStore.selectedHCProfile" class="mt-3">
        <div class="text-caption font-weight-medium mb-1">Estimated HC Availability</div>
        <ProfileHeatmap
          :constraint-profile="enrichmentStore.selectedHCProfile.profile_12x24"
          :constraint-base-color="[34, 197, 94]"
          constraint-label="HC Availability"
          :highlight-peak="true"
          :peak-month="enrichmentStore.selectedHCProfile.peak_month"
          :peak-hour="enrichmentStore.selectedHCProfile.peak_hour"
          size="mini"
        />
        <p class="text-caption text-medium-emphasis mt-1" style="line-height: 1.3; font-size: 0.65rem;">
          Estimated from {{ enrichmentStore.selectedHCProfile.iso_code }} load shape
          ({{ enrichmentStore.selectedHCProfile.year }}). Brighter = more HC headroom.
        </p>
      </div>
      <div v-else-if="enrichmentStore.isHCProfileLoading" class="text-center pa-1">
        <v-progress-circular indeterminate size="14" />
      </div>
    </div>

    <!-- Interconnection Queue -->
    <div v-if="enrichmentStore.nearbyQueueProjects.length > 0" class="mb-2">
      <div class="text-caption font-weight-medium mb-1">Interconnection Queue</div>
      <div
        v-for="(p, i) in enrichmentStore.nearbyQueueProjects.slice(0, 3)"
        :key="i"
        class="d-flex align-center justify-space-between mb-1 text-caption"
      >
        <span>{{ p.project_name || 'Unnamed' }}</span>
        <span class="text-medium-emphasis">{{ p.capacity_mw }} MW {{ p.generation_type }}</span>
      </div>
    </div>

    <!-- Link to zone -->
    <v-btn
      v-if="resolvedZone"
      variant="text"
      size="small"
      block
      class="mt-2"
      @click="goToZone"
    >
      View full zone detail: {{ resolvedZone }}
    </v-btn>

    <div
      v-if="!enrichmentStore.isNearbyLoading && enrichmentStore.nearbyFeeders.length === 0 && enrichmentStore.nearbyQueueProjects.length === 0"
      class="text-caption text-medium-emphasis"
    >
      No nearby data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'

const props = defineProps<{
  lat: number
  lon: number
}>()

const enrichmentStore = useEnrichmentStore()
const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()

const resolvedZone = computed(() => gridStore.resolvedLocation?.zone_code ?? null)

watch(
  () => [props.lat, props.lon],
  ([lat, lon]) => {
    if (lat != null && lon != null) {
      enrichmentStore.loadNearbyHC(lat, lon)
      enrichmentStore.loadNearbyQueue(lat, lon)
    }
  },
  { immediate: true },
)

// Load HC profile when nearby feeders arrive (use first feeder's utility)
watch(
  () => enrichmentStore.nearbyFeeders,
  (feeders) => {
    const utilityCode = feeders[0]?.utility_code
    if (utilityCode) {
      enrichmentStore.loadHCProfile(utilityCode)
    }
  },
)

function shortStatus(status: string): string {
  const lower = status.toLowerCase()
  if (lower.includes('likely') || lower.includes('available') || lower.includes('high capacity')) return 'Available'
  if (lower.includes('no expected') || lower.includes('no capacity')) return 'No Capacity'
  if (lower.includes('engineering') || lower.includes('assessment')) return 'Needs Review'
  if (lower.includes('low capacity')) return 'Low'
  return status.length > 16 ? status.slice(0, 14) + '...' : status
}

function capacityStatusColor(status: string): string {
  const lower = status.toLowerCase()
  if (lower.includes('likely') || lower.includes('available') || lower.includes('high capacity')) return 'success'
  if (lower.includes('no expected') || lower.includes('no capacity')) return 'error'
  if (lower.includes('low capacity')) return 'warning'
  return 'grey'
}

function goToZone() {
  if (resolvedZone.value) {
    selectionStore.selectZone(resolvedZone.value)
    if (selectionStore.selectedISO) {
      gridStore.loadZoneConstraints(selectionStore.selectedISO, resolvedZone.value)
    }
  }
}
</script>
