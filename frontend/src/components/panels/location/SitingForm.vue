<template>
  <v-card variant="outlined" class="pa-3">
    <h4 class="text-subtitle-2 mb-2">Evaluate DER at this location</h4>
    <v-select
      v-model="derType"
      :items="derTypes"
      label="DER Type"
      density="compact"
      variant="outlined"
      hide-details
      class="mb-2"
    />
    <v-text-field
      v-model.number="capacityMw"
      label="Capacity (MW)"
      type="number"
      density="compact"
      variant="outlined"
      hide-details
      class="mb-2"
    />
    <v-btn
      color="primary"
      block
      :loading="valuationStore.isComputing"
      @click="evaluate"
    >
      Evaluate
    </v-btn>
  </v-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useValuationStore } from '@/stores/valuationStore'
import { useSelectionStore } from '@/stores/selectionStore'

const props = defineProps<{
  lat: number
  lon: number
}>()

const valuationStore = useValuationStore()
const selectionStore = useSelectionStore()

const derType = ref('solar')
const capacityMw = ref(1.0)

const derTypes = [
  { title: 'Solar', value: 'solar' },
  { title: 'Wind', value: 'wind' },
  { title: 'Storage', value: 'storage' },
  { title: 'Demand Response', value: 'demand_response' },
  { title: 'Energy Efficiency', value: 'energy_efficiency' },
  { title: 'CHP', value: 'combined_heat_power' },
  { title: 'Fuel Cell', value: 'fuel_cell' },
]

onMounted(() => {
  valuationStore.loadAllDERProfiles()
})

function evaluate() {
  valuationStore.computeProspective(props.lat, props.lon, derType.value, capacityMw.value)
  selectionStore.showValuation()
}
</script>
