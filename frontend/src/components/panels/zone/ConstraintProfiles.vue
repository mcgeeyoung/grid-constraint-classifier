<template>
  <div class="mb-3">
    <h4 class="text-subtitle-2 mb-2">Constraint Profiles</h4>

    <div v-if="isLoading" class="text-center pa-2">
      <v-progress-circular indeterminate size="20" color="primary" />
    </div>
    <div v-else-if="profiles.length === 0" class="text-caption text-medium-emphasis">
      No constraint profiles available
    </div>
    <div v-else>
      <div
        v-for="cp in profiles"
        :key="cp.id"
        class="mb-3 pa-2 rounded"
        style="border: 1px solid var(--border-default);"
      >
        <div class="d-flex align-center ga-2 mb-1">
          <TierChip :tier="cp.constraint_type" type="constraint" />
          <TierChip :tier="cp.severity_tier" variant="outlined" />
        </div>

        <div class="text-caption text-medium-emphasis mb-1">
          Peak: {{ monthName(cp.peak_month) }} @ {{ cp.peak_hour }}:00
          | Severity: {{ cp.severity_score.toFixed(2) }}
          | Constrained: {{ (cp.constrained_hours_pct * 100).toFixed(1) }}%
        </div>

        <ProfileHeatmap
          v-if="cp.profile_12x24"
          :constraint-profile="cp.profile_12x24"
          size="standard"
          :highlight-peak="true"
          :peak-month="cp.peak_month"
          :peak-hour="cp.peak_hour"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ConstraintProfile } from '@/types/constraints'
import TierChip from '@/components/shared/TierChip.vue'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'
import { monthName } from '@/utils/monthNames'

defineProps<{
  profiles: ConstraintProfile[]
  isLoading: boolean
}>()
</script>
