<template>
  <div v-if="hierarchyStore.selectedSubstation">
    <h3 class="text-h6 mb-2">{{ hierarchyStore.selectedSubstation.substation_name }}</h3>
    <p v-if="hierarchyStore.selectedSubstation.bank_name" class="text-body-2 text-medium-emphasis mb-3">
      Bank: {{ hierarchyStore.selectedSubstation.bank_name }}
    </p>

    <v-chip
      :color="loadingColor"
      size="small"
      class="mb-3"
    >
      {{ loadingLabel }}
    </v-chip>

    <v-table density="compact">
      <tbody>
        <tr>
          <td class="text-medium-emphasis">Rating</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.facility_rating_mw?.toFixed(1) ?? '-' }} MW</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Loading</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.facility_loading_mw?.toFixed(1) ?? '-' }} MW</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Peak Loading</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.peak_loading_pct?.toFixed(1) ?? '-' }}%</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Type</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.facility_type ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Zone</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.zone_code ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Feeders</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.feeder_count }}</td>
        </tr>
      </tbody>
    </v-table>

    <div v-if="hierarchyStore.feeders.length > 0" class="mt-4">
      <h4 class="text-subtitle-2 mb-2">Feeders</h4>
      <v-list density="compact">
        <v-list-item
          v-for="feeder in hierarchyStore.feeders"
          :key="feeder.id"
          :subtitle="`${feeder.capacity_mw?.toFixed(1) ?? '?'} MW cap, ${feeder.peak_loading_pct?.toFixed(0) ?? '?'}% loaded`"
        >
          <template v-slot:title>
            <span class="text-body-2">{{ feeder.feeder_id_external ?? `Feeder #${feeder.id}` }}</span>
          </template>
        </v-list-item>
      </v-list>
    </div>
  </div>
  <div v-else class="text-center text-medium-emphasis pa-4">
    Click a substation marker to see details
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useHierarchyStore } from '@/stores/hierarchyStore'

const hierarchyStore = useHierarchyStore()

const loadingPct = computed(() => hierarchyStore.selectedSubstation?.peak_loading_pct ?? 0)

const loadingColor = computed(() => {
  if (loadingPct.value > 100) return '#e74c3c'
  if (loadingPct.value >= 80) return '#e67e22'
  if (loadingPct.value >= 60) return '#f1c40f'
  return '#2ecc71'
})

const loadingLabel = computed(() => {
  if (loadingPct.value > 100) return 'Overloaded'
  if (loadingPct.value >= 80) return 'Near Capacity'
  if (loadingPct.value >= 60) return 'Moderate'
  return 'Normal'
})
</script>
