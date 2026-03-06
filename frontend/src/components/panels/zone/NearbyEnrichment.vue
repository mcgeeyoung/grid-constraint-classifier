<template>
  <div v-if="lat != null && lon != null" class="mb-3">
    <v-divider class="mb-2" />
    <h4 class="text-subtitle-2 mb-2">Nearby Context</h4>

    <div v-if="enrichmentStore.isNearbyLoading" class="text-center pa-2">
      <v-progress-circular indeterminate size="20" />
    </div>

    <!-- Hosting Capacity -->
    <div v-if="enrichmentStore.nearbyFeeders.length > 0" class="mb-2">
      <div class="text-caption font-weight-medium mb-1">Hosting Capacity</div>
      <v-table density="compact">
        <thead>
          <tr>
            <th class="text-caption pa-1">Feeder</th>
            <th class="text-caption text-right pa-1">Remaining MW</th>
            <th class="text-caption pa-1">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(f, i) in enrichmentStore.nearbyFeeders.slice(0, 5)" :key="i">
            <td class="text-caption pa-1">{{ f.feeder_name || f.substation_name || '-' }}</td>
            <td class="text-caption text-right pa-1">{{ f.remaining_capacity_mw?.toFixed(1) ?? '-' }}</td>
            <td class="text-caption pa-1">
              <v-chip
                v-if="f.constraining_metric"
                size="x-small"
                variant="flat"
              >
                {{ f.constraining_metric }}
              </v-chip>
              <v-chip
                v-else-if="f.capacity_status"
                size="x-small"
                :color="capacityStatusColor(f.capacity_status)"
                variant="flat"
              >
                {{ shortStatus(f.capacity_status) }}
              </v-chip>
              <span v-else>-</span>
            </td>
          </tr>
        </tbody>
      </v-table>

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
          size="standard"
        />
        <p class="text-caption text-medium-emphasis mt-1" style="line-height: 1.3;">
          Estimated HC availability based on the ISO's historical load shape. Brighter cells
          indicate hours and months when feeder load is typically below peak, meaning more
          hosting capacity headroom is likely available. This is an estimate derived from
          {{ enrichmentStore.selectedHCProfile.iso_code }} aggregate demand patterns in
          {{ enrichmentStore.selectedHCProfile.year }}, not measured per-feeder data. Actual
          hosting capacity varies by feeder topology, voltage regulation, and protection settings.
        </p>
      </div>
      <div v-else-if="enrichmentStore.isHCProfileLoading" class="text-center pa-2">
        <v-progress-circular indeterminate size="16" />
      </div>
    </div>

    <!-- Interconnection Queue -->
    <div v-if="enrichmentStore.nearbyQueueProjects.length > 0" class="mb-2">
      <div class="text-caption font-weight-medium mb-1">Interconnection Queue</div>
      <div
        v-for="(p, i) in enrichmentStore.nearbyQueueProjects.slice(0, 5)"
        :key="i"
        class="d-flex align-center justify-space-between mb-1 pa-1 rounded"
        style="border: 1px solid var(--border-subtle);"
      >
        <div>
          <div class="text-caption">{{ p.project_name || 'Unnamed' }}</div>
          <div class="text-caption text-medium-emphasis">{{ p.generation_type }} | {{ p.capacity_mw }} MW</div>
        </div>
        <v-chip
          :color="queueStatusColor(p.queue_status)"
          size="x-small"
          variant="flat"
        >
          {{ p.queue_status || 'unknown' }}
        </v-chip>
      </div>
    </div>

    <div v-if="!enrichmentStore.isNearbyLoading && enrichmentStore.nearbyFeeders.length === 0 && enrichmentStore.nearbyQueueProjects.length === 0" class="text-caption text-medium-emphasis">
      No nearby enrichment data available
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'

const props = defineProps<{
  lat: number | undefined
  lon: number | undefined
}>()

const enrichmentStore = useEnrichmentStore()

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

function queueStatusColor(status: string | null): string {
  switch (status) {
    case 'active': return 'green'
    case 'completed': return 'blue'
    case 'withdrawn': return 'grey'
    default: return 'grey'
  }
}
</script>
