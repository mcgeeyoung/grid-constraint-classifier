<template>
  <div v-if="valuationStore.isLoading" class="text-center pa-4">
    <v-progress-circular indeterminate color="primary" />
    <p class="mt-2 text-body-2">Computing valuation...</p>
  </div>

  <div v-else-if="valuationStore.error" class="pa-4">
    <v-alert type="error" density="compact">{{ valuationStore.error }}</v-alert>
  </div>

  <div v-else-if="result">
    <h3 class="text-h6 mb-2">Siting Valuation</h3>

    <!-- Geo resolution chain -->
    <div class="text-body-2 text-medium-emphasis mb-3">
      <span v-if="geo?.iso_code">{{ geo.iso_code.toUpperCase() }}</span>
      <span v-if="geo?.zone_code"> &rsaquo; {{ geo.zone_code }}</span>
      <span v-if="geo?.substation_name"> &rsaquo; {{ geo.substation_name }}</span>
    </div>

    <!-- Total value -->
    <div class="text-center mb-4">
      <div class="text-h4 font-weight-bold">
        ${{ result.total_constraint_relief_value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
      </div>
      <div class="text-body-2 text-medium-emphasis">
        ${{ result.value_per_kw_year.toFixed(2) }}/kW-yr
      </div>
      <v-chip :color="tierColor" size="small" class="mt-1">
        {{ result.value_tier }}
      </v-chip>
    </div>

    <!-- Value breakdown -->
    <v-table density="compact">
      <tbody>
        <tr>
          <td class="text-medium-emphasis">Zone Congestion</td>
          <td class="text-right">${{ result.zone_congestion_value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Pnode Multiplier</td>
          <td class="text-right">{{ result.pnode_multiplier.toFixed(2) }}x</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Substation Loading</td>
          <td class="text-right">${{ result.substation_loading_value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Feeder Capacity</td>
          <td class="text-right">${{ result.feeder_capacity_value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Coincidence Factor</td>
          <td class="text-right">{{ (result.coincidence_factor * 100).toFixed(0) }}%</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Effective Capacity</td>
          <td class="text-right">{{ result.effective_capacity_mw.toFixed(2) }} MW</td>
        </tr>
      </tbody>
    </v-table>

    <!-- Stacked bar -->
    <div class="mt-4">
      <h4 class="text-subtitle-2 mb-1">Value Composition</h4>
      <div class="d-flex rounded overflow-hidden" style="height: 24px;">
        <div
          v-if="zonePct > 0"
          :style="{ width: zonePct + '%', backgroundColor: '#3498db' }"
          :title="`Zone: ${zonePct.toFixed(0)}%`"
        />
        <div
          v-if="subPct > 0"
          :style="{ width: subPct + '%', backgroundColor: '#e67e22' }"
          :title="`Substation: ${subPct.toFixed(0)}%`"
        />
        <div
          v-if="feederPct > 0"
          :style="{ width: feederPct + '%', backgroundColor: '#2ecc71' }"
          :title="`Feeder: ${feederPct.toFixed(0)}%`"
        />
      </div>
      <div class="d-flex ga-3 mt-1 text-caption">
        <span><span style="color:#3498db">&#9632;</span> Zone</span>
        <span><span style="color:#e67e22">&#9632;</span> Substation</span>
        <span><span style="color:#2ecc71">&#9632;</span> Feeder</span>
      </div>
    </div>

    <v-btn
      color="primary"
      variant="outlined"
      size="small"
      block
      class="mt-4"
      @click="saveDER"
      :loading="isSaving"
    >
      Save as DER Location
    </v-btn>
  </div>

  <div v-else class="text-center text-medium-emphasis pa-4">
    Click the map and submit a DER evaluation to see results
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useValuationStore } from '@/stores/valuationStore'
import { useIsoStore } from '@/stores/isoStore'

const valuationStore = useValuationStore()
const isoStore = useIsoStore()
const isSaving = ref(false)

const result = computed(() => valuationStore.sitingResult)
const geo = computed(() => result.value?.geo_resolution)

const tierColor = computed(() => {
  switch (result.value?.value_tier) {
    case 'premium': return '#c0392b'
    case 'high': return '#e67e22'
    case 'moderate': return '#f1c40f'
    case 'low': return '#27ae60'
    default: return 'grey'
  }
})

const total = computed(() => result.value?.total_constraint_relief_value || 1)
const zoneVal = computed(() => (result.value?.zone_congestion_value ?? 0) * (result.value?.pnode_multiplier ?? 1))
const zonePct = computed(() => (zoneVal.value / total.value) * 100)
const subPct = computed(() => ((result.value?.substation_loading_value ?? 0) / total.value) * 100)
const feederPct = computed(() => ((result.value?.feeder_capacity_value ?? 0) / total.value) * 100)

async function saveDER() {
  if (!geo.value) return
  isSaving.value = true
  const ok = await valuationStore.saveDERLocation(
    geo.value.lat,
    geo.value.lon,
    valuationStore.lastDerType,
    valuationStore.lastCapacityMw,
  )
  isSaving.value = false
  if (ok && isoStore.selectedISO) {
    isoStore.selectISO(isoStore.selectedISO) // refresh DERs
  }
}
</script>
