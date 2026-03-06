<template>
  <v-card v-if="resolution" variant="outlined" class="pa-3 mb-3">
    <div class="text-subtitle-2 mb-2">Geo Resolution</div>
    <v-table density="compact">
      <tbody>
        <tr v-if="resolution.iso_code">
          <td class="text-caption text-medium-emphasis pa-1">ISO</td>
          <td class="text-body-2 pa-1">{{ resolution.iso_code.toUpperCase() }}</td>
        </tr>
        <tr v-if="resolution.zone_code">
          <td class="text-caption text-medium-emphasis pa-1">Zone</td>
          <td class="text-body-2 pa-1">{{ resolution.zone_code }}</td>
        </tr>
        <tr v-if="resolution.substation_name">
          <td class="text-caption text-medium-emphasis pa-1">Substation</td>
          <td class="text-body-2 pa-1">{{ resolution.substation_name }}</td>
        </tr>
        <tr v-if="resolution.nearest_pnode_name">
          <td class="text-caption text-medium-emphasis pa-1">Nearest Pnode</td>
          <td class="text-body-2 pa-1">{{ resolution.nearest_pnode_name }}</td>
        </tr>
        <tr>
          <td class="text-caption text-medium-emphasis pa-1">Resolution</td>
          <td class="text-body-2 pa-1">{{ resolution.resolution_depth }}</td>
        </tr>
      </tbody>
    </v-table>

    <!-- Constraint layers -->
    <div v-if="resolution.constraints.length > 0" class="mt-2">
      <div class="text-caption font-weight-medium mb-1">Constraints at this location</div>
      <div
        v-for="cl in resolution.constraints"
        :key="cl.constraint_type"
        class="d-flex align-center justify-space-between mb-1"
      >
        <span class="text-caption text-capitalize">{{ cl.constraint_type }}</span>
        <div class="d-flex align-center ga-1">
          <TierChip :tier="cl.severity_tier" />
          <span class="text-caption text-medium-emphasis">({{ cl.severity_score.toFixed(2) }})</span>
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import type { GeoResolution } from '@/types/constraints'
import TierChip from '@/components/shared/TierChip.vue'

defineProps<{
  resolution: GeoResolution | null
}>()
</script>
