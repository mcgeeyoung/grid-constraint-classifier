<template>
  <v-card variant="outlined" class="pa-3 mb-3">
    <div class="text-subtitle-2 mb-2">Congestion Metrics</div>
    <div class="d-flex align-center ga-3 mb-2">
      <span class="text-h5 font-weight-bold">
        {{ (score?.congestion_opportunity_score ?? 0).toFixed(2) }}
      </span>
      <span class="text-caption text-medium-emphasis">opportunity score</span>
    </div>

    <v-table density="compact">
      <tbody>
        <tr>
          <td class="text-caption pa-1">Hours importing</td>
          <td class="text-body-2 text-right pa-1">
            {{ formatPct(score?.pct_hours_importing) }}
          </td>
        </tr>
        <tr>
          <td class="text-caption pa-1">Avg import % of load</td>
          <td class="text-body-2 text-right pa-1">
            {{ formatPct(score?.avg_import_pct_of_load) }}
          </td>
        </tr>
        <tr>
          <td class="text-caption pa-1">Max import % of load</td>
          <td class="text-body-2 text-right pa-1">
            {{ formatPct(score?.max_import_pct_of_load) }}
          </td>
        </tr>
        <tr v-if="score?.hours_above_80">
          <td class="text-caption pa-1">Hours &gt; 80% utilization</td>
          <td class="text-body-2 text-right pa-1">{{ score.hours_above_80 }}</td>
        </tr>
        <tr v-if="score?.hours_above_90">
          <td class="text-caption pa-1">Hours &gt; 90% utilization</td>
          <td class="text-body-2 text-right pa-1">{{ score.hours_above_90 }}</td>
        </tr>
        <tr v-if="score?.hours_above_95">
          <td class="text-caption pa-1">Hours &gt; 95% utilization</td>
          <td class="text-body-2 text-right pa-1">{{ score.hours_above_95 }}</td>
        </tr>
        <tr v-if="ba.transfer_limit_mw">
          <td class="text-caption pa-1">Transfer limit</td>
          <td class="text-body-2 text-right pa-1">{{ ba.transfer_limit_mw }} MW</td>
        </tr>
      </tbody>
    </v-table>
  </v-card>
</template>

<script setup lang="ts">
import type { BA, CongestionScore } from '@/api/congestion'

defineProps<{
  ba: BA
  score: CongestionScore | null
}>()

function formatPct(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toFixed(1) + '%'
}
</script>
