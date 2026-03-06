<template>
  <div>
    <div v-if="gridStore.selectedBA">
      <h3 class="text-h6 mb-2">{{ gridStore.selectedBA.ba_name || gridStore.selectedBA.ba_code }}</h3>

      <div v-if="gridStore.selectedBA.region" class="text-caption text-medium-emphasis mb-3">
        {{ gridStore.selectedBA.region }}
      </div>

      <div v-if="gridStore.isDetailLoading" class="text-center pa-4">
        <v-progress-circular indeterminate size="24" />
      </div>

      <ProfileHeatmap
        v-if="gridStore.selectedBAProfile"
        :constraint-profile="gridStore.selectedBAProfile.profile_12x24"
        size="large"
        :show-labels="true"
        :show-legend="false"
        :highlight-peak="true"
        :peak-month="gridStore.selectedBAProfile.peak_month"
        :peak-hour="gridStore.selectedBAProfile.peak_hour"
      />

      <!-- DER Profiles button -->
      <v-btn
        v-if="baLatLon"
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

      <div v-if="gridStore.selectedBAProfile" class="mt-3">
        <div class="text-caption text-medium-emphasis mb-1">
          Peak: Month {{ gridStore.selectedBAProfile.peak_month }}, Hour {{ gridStore.selectedBAProfile.peak_hour }}
        </div>
        <div class="text-caption text-medium-emphasis" style="line-height: 1.5;">
          Color intensity represents average import utilization: net imports as a percentage of the BA's estimated transfer limit.
          Brighter red cells indicate hours and months where the BA consistently imports a higher share of its capacity.
          Values are averaged across all days in {{ gridStore.selectedBAProfile.year }} for each (month, hour) combination, clamped to 0-100%.
          The white-bordered cell marks the peak average utilization.
        </div>
      </div>
    </div>
    <div v-else class="text-center text-medium-emphasis pa-4">
      Select a BA from the dropdown to see its 12x24 import utilization
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

const baLatLon = computed(() => {
  const ba = gridStore.selectedBA
  if (ba?.latitude != null && ba?.longitude != null) {
    return { lat: ba.latitude, lon: ba.longitude }
  }
  return null
})

function openDERViewer() {
  if (baLatLon.value) {
    enrichmentStore.loadDERGridScores(baLatLon.value.lat, baLatLon.value.lon, 'solar')
    selectionStore.showDERViewer()
  }
}
</script>
