<template>
  <l-marker
    v-if="mapStore.clickedPoint && mapStore.showSitingPopup"
    :lat-lng="[mapStore.clickedPoint.lat, mapStore.clickedPoint.lng]"
  >
    <l-popup :options="{ minWidth: 240, maxWidth: 300 }">
      <div style="font-size: 13px;">
        <div class="text-caption mb-1" style="color: #999;">
          {{ mapStore.clickedPoint.lat.toFixed(5) }}, {{ mapStore.clickedPoint.lng.toFixed(5) }}
        </div>

        <div style="margin-bottom: 8px;">
          <label style="display: block; font-weight: 500; margin-bottom: 2px;">DER Type</label>
          <select v-model="derType" style="width: 100%; padding: 4px; border: 1px solid #555; border-radius: 4px; background: #2a2a3e; color: #fff;">
            <option value="solar">Solar</option>
            <option value="wind">Wind</option>
            <option value="storage">Storage</option>
            <option value="demand_response">Demand Response</option>
            <option value="energy_efficiency_eemetered">Energy Efficiency</option>
            <option value="combined_heat_power">CHP</option>
            <option value="fuel_cell">Fuel Cell</option>
          </select>
        </div>

        <div style="margin-bottom: 8px;">
          <label style="display: block; font-weight: 500; margin-bottom: 2px;">Capacity (MW)</label>
          <input
            v-model.number="capacityMw"
            type="number"
            min="0.01"
            step="0.1"
            style="width: 100%; padding: 4px; border: 1px solid #555; border-radius: 4px; background: #2a2a3e; color: #fff;"
          />
        </div>

        <button
          @click="evaluate"
          :disabled="valuationStore.isLoading"
          style="width: 100%; padding: 6px; background: #3498db; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: 500;"
        >
          {{ valuationStore.isLoading ? 'Evaluating...' : 'Evaluate' }}
        </button>
      </div>
    </l-popup>
  </l-marker>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { LMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useMapStore } from '@/stores/mapStore'
import { useValuationStore } from '@/stores/valuationStore'

const mapStore = useMapStore()
const valuationStore = useValuationStore()

const derType = ref('solar')
const capacityMw = ref(1.0)

async function evaluate() {
  if (!mapStore.clickedPoint) return
  await valuationStore.runSitingValuation(
    mapStore.clickedPoint.lat,
    mapStore.clickedPoint.lng,
    derType.value,
    capacityMw.value,
  )
}
</script>
