<template>
  <div>
    <div v-if="gridStore.isLoading" class="text-center pa-4">
      <v-progress-circular indeterminate size="24" />
    </div>

    <template v-if="detail">
      <h3 class="text-h6 mb-1">{{ detail.substation_name || `Substation #${detail.id}` }}</h3>

      <div v-if="detail.bank_name" class="text-caption text-medium-emphasis mb-1">
        {{ detail.bank_name }}
      </div>

      <!-- Key stats -->
      <div class="d-flex flex-wrap ga-3 mb-4 mt-3">
        <div v-if="detail.facility_rating_mw != null" class="stat-box">
          <div class="stat-value">{{ detail.facility_rating_mw.toLocaleString() }}</div>
          <div class="stat-label">Rating MW</div>
        </div>
        <div v-if="detail.facility_loading_mw != null" class="stat-box">
          <div class="stat-value">{{ detail.facility_loading_mw.toLocaleString() }}</div>
          <div class="stat-label">Loading MW</div>
        </div>
        <div v-if="detail.peak_loading_pct != null" class="stat-box">
          <div class="stat-value" :style="{ color: loadingColor }">
            {{ Math.round(detail.peak_loading_pct) }}%
          </div>
          <div class="stat-label">Peak Loading</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">{{ detail.feeder_count }}</div>
          <div class="stat-label">Feeders</div>
        </div>
      </div>

      <!-- Metadata -->
      <div class="text-caption text-medium-emphasis mb-4">
        <div v-if="detail.facility_type">Type: {{ detail.facility_type }}</div>
        <div v-if="detail.division">Division: {{ detail.division }}</div>
        <div v-if="detail.zone_code">Zone: {{ detail.zone_code }}</div>
        <div v-if="detail.nearest_pnode_name">Nearest P-node: {{ detail.nearest_pnode_name }}</div>
      </div>

      <!-- 12x24 Load Profile Heatmap -->
      <div v-if="gridStore.isSubstationProfileLoading" class="text-center pa-2">
        <v-progress-circular indeterminate size="20" />
      </div>
      <div v-else-if="gridStore.substationProfile">
        <div class="text-subtitle-2 mb-2">Load Profile (12x24)</div>
        <ProfileHeatmap
          :constraint-profile="gridStore.substationProfile.profile_12x24"
          size="large"
          :show-labels="true"
          :show-legend="false"
          :highlight-peak="true"
          :peak-month="gridStore.substationProfile.peak_month"
          :peak-hour="gridStore.substationProfile.peak_hour"
          constraint-label="Load"
        />
        <div class="text-caption text-medium-emphasis mt-2" style="line-height: 1.5;">
          Peak load: Month {{ gridStore.substationProfile.peak_month }},
          Hour {{ gridStore.substationProfile.peak_hour }}.
          Brighter red cells indicate higher average load (kW).
        </div>
      </div>
      <div v-else class="text-caption text-medium-emphasis pa-2">
        No load profile data available.
      </div>

      <!-- DER Profiles button -->
      <v-btn
        v-if="detail.lat != null && detail.lon != null"
        variant="tonal"
        color="info"
        size="small"
        block
        class="mt-3 mb-3"
        prepend-icon="mdi-white-balance-sunny"
        @click="openDERViewer"
      >
        View DER Profiles
      </v-btn>

      <!-- Feeders list -->
      <div v-if="gridStore.substationFeeders.length" class="mt-4">
        <div class="text-subtitle-2 mb-2">
          Feeders ({{ gridStore.substationFeeders.length }})
        </div>
        <v-card
          v-for="feeder in gridStore.substationFeeders"
          :key="feeder.id"
          variant="outlined"
          density="compact"
          class="pa-2 mb-1"
        >
          <div class="d-flex align-center justify-space-between">
            <span class="text-body-2 font-weight-medium text-truncate">
              {{ feeder.feeder_id_external || `Feeder #${feeder.id}` }}
            </span>
            <v-chip
              v-if="feeder.peak_loading_pct != null"
              size="x-small"
              :color="feederLoadingColor(feeder.peak_loading_pct)"
              variant="flat"
            >
              {{ Math.round(feeder.peak_loading_pct) }}%
            </v-chip>
          </div>
          <div class="d-flex ga-3 text-caption" style="color: var(--text-secondary);">
            <span v-if="feeder.capacity_mw != null">{{ feeder.capacity_mw }} MW</span>
            <span v-if="feeder.voltage_kv != null">{{ feeder.voltage_kv }} kV</span>
          </div>
        </v-card>
      </div>
    </template>

    <div v-if="!gridStore.isLoading && !detail" class="text-center text-medium-emphasis pa-4">
      Substation not found.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'

const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()
const enrichmentStore = useEnrichmentStore()

function openDERViewer() {
  if (detail.value?.lat != null && detail.value?.lon != null) {
    enrichmentStore.loadDERGridScores(detail.value.lat, detail.value.lon, 'solar')
    selectionStore.showDERViewer()
  }
}

const detail = computed(() => gridStore.selectedSubstationDetail)

const loadingColor = computed(() => {
  const pct = detail.value?.peak_loading_pct
  if (pct == null) return 'inherit'
  if (pct >= 90) return '#ef4444'
  if (pct >= 75) return '#f59e0b'
  return '#22c55e'
})

function feederLoadingColor(pct: number): string {
  if (pct >= 90) return 'error'
  if (pct >= 75) return 'warning'
  return 'success'
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
