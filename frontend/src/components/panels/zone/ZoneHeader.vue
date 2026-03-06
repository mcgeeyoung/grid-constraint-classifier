<template>
  <div v-if="zone">
    <h3 class="text-h6 mb-1">{{ zone.zone_code }}</h3>
    <p v-if="zone.zone_name" class="text-body-2 text-medium-emphasis mb-2">
      {{ zone.zone_name }}
    </p>

    <!-- Severity badge -->
    <div class="d-flex align-center ga-2 mb-3">
      <TierChip :tier="zone.severity_tier ?? 'low'" />
      <span v-if="zone.severity_score != null" class="text-caption text-medium-emphasis">
        Score: {{ zone.severity_score.toFixed(2) }}
      </span>
    </div>

    <!-- Deferral opportunity banner -->
    <v-alert
      v-if="deferralCount > 0"
      type="success"
      variant="tonal"
      density="compact"
      class="mb-3"
    >
      {{ deferralCount }} deferral {{ deferralCount === 1 ? 'opportunity' : 'opportunities' }} identified
      <span v-if="totalDeferralValue"> (est. ${{ totalDeferralValue.toLocaleString() }})</span>
    </v-alert>

    <!-- Quick stats -->
    <v-table density="compact" class="mb-3">
      <tbody>
        <tr v-if="zone.primary_constraint_type">
          <td class="text-medium-emphasis">Primary Constraint</td>
          <td class="text-right text-capitalize">{{ zone.primary_constraint_type }}</td>
        </tr>
        <tr v-if="zone.peak_month">
          <td class="text-medium-emphasis">Peak Month/Hour</td>
          <td class="text-right">{{ monthName(zone.peak_month) }} @ {{ zone.peak_hour }}:00</td>
        </tr>
        <tr v-if="zone.constrained_hours_pct != null">
          <td class="text-medium-emphasis">Constrained Hours</td>
          <td class="text-right">{{ (zone.constrained_hours_pct * 100).toFixed(1) }}%</td>
        </tr>
        <tr v-if="zone.best_der_type">
          <td class="text-medium-emphasis">Best DER</td>
          <td class="text-right">
            {{ derLabel(zone.best_der_type) }}
            <span v-if="zone.best_der_value_per_kw_year" class="text-medium-emphasis">
              (${{ zone.best_der_value_per_kw_year.toFixed(0) }}/kW-yr)
            </span>
          </td>
        </tr>
        <tr v-if="zone.annotation_count > 0">
          <td class="text-medium-emphasis">Annotations</td>
          <td class="text-right">{{ zone.annotation_count }}</td>
        </tr>
      </tbody>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ZoneConstraintSummary, Annotation } from '@/types/constraints'
import TierChip from '@/components/shared/TierChip.vue'
import { monthName } from '@/utils/monthNames'
import { derLabel } from '@/utils/derLabels'

const props = defineProps<{
  zone: ZoneConstraintSummary
  annotations: Annotation[]
}>()

const deferralCount = computed(() =>
  props.annotations.filter(a => a.annotation_type === 'deferral_opportunity').length,
)

const totalDeferralValue = computed(() => {
  const deferrals = props.annotations.filter(a => a.annotation_type === 'deferral_opportunity')
  const total = deferrals.reduce((sum, a) => sum + (a.deferral_value_estimate ?? 0), 0)
  return total > 0 ? total : null
})
</script>
